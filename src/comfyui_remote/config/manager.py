# src/comfyui_remote/config/manager.py
from __future__ import annotations

import json
import os
import re
import socket
import tempfile
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional

from .layering import (
    load_controller,
    resolve_layer_path,
    merge_json_layers,
    merge_yaml_layers,
)
from .types import ComfyConfig

# ----------------------- path & misc helpers -----------------------

_ENV_TOKEN_RE = re.compile(r"\$\{ENV:([A-Za-z0-9_]+)\}")


def _pick(k: str, *vals: str) -> Optional[str]:
    """
    Return the first non-empty value among vals, else None.
    Convenience for 'prefer config, else computed'.
    """
    for v in vals:
        if v:
            return v
    return None


def _join(*parts: str) -> str:
    return _norm_path(str(Path(parts[0]).joinpath(*parts[1:])))


def _expand_env_token_style(text: str, env: Optional[Dict[str, str]] = None) -> str:
    """Replace ${ENV:VAR} with os.environ['VAR'] (or empty string if unset)."""
    if not isinstance(text, str):
        return text
    env = env or os.environ

    def _sub(m: re.Match) -> str:
        name = m.group(1)
        return env.get(name, "")

    return _ENV_TOKEN_RE.sub(_sub, text)


def _expand_all_tokens(text: str, env: Optional[Dict[str, str]] = None) -> str:
    """
    For DEBUG views ONLY:
      - Expand ${ENV:VAR} (our style)
      - Expand $VAR / ${VAR} (shell style)
      - Expand ~ (home)
    """
    if not isinstance(text, str):
        return text
    s = _expand_env_token_style(text, env)
    s = os.path.expandvars(s)
    s = os.path.expanduser(s)
    return s


def _deep_expand_debug(obj: Any, env: Optional[Dict[str, str]] = None) -> Any:
    """Recursively expand strings in dict/list/scalars for debug printing."""
    if isinstance(obj, str):
        return _expand_all_tokens(obj, env)
    if isinstance(obj, list):
        return [_deep_expand_debug(x, env) for x in obj]
    if isinstance(obj, dict):
        return {k: _deep_expand_debug(v, env) for k, v in obj.items()}
    return obj


def _expand_vars(path: str) -> str:
    """Expand ${ENV_VARS}, %WINVAR%, and ~ in a path string."""
    if not path:
        return path
    expanded = os.path.expandvars(path)
    expanded = os.path.expanduser(expanded)
    return expanded


def _norm_path(path: str) -> str:
    """Normalize a path and prefer forward slashes (Comfy tolerates both on Windows)."""
    if not path:
        return path
    return str(Path(_expand_vars(path))).replace("\\", "/")


def _dedup_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        if not x:
            continue
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


def _ensure_list(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return [str(v)]


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ----------------------- model-map expansion -----------------------

_CATEGORY_KEYS_ORDER = [
    "checkpoints", "vae", "clip", "clip_vision",
    "diffusion_models", "unet",
    "loras", "embeddings", "controlnet",
    "upscale_models", "configs",
]


def _expand_models_with_root(models_root: str, explicit: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """
    Build a complete <category -> [paths]> map.
    - Start from explicit per-category paths
    - For any missing category, add <models_root>/models/<category>
    - Normalize and dedupe
    """
    out: Dict[str, List[str]] = {k: list(v) for k, v in (explicit or {}).items()}

    root = _norm_path(models_root) if models_root else ""
    if root:
        for cat in _CATEGORY_KEYS_ORDER:
            if cat not in out or not out[cat]:
                candidate = f"{root}/models/{cat}"
                out.setdefault(cat, []).append(candidate)

    # Normalize + de-duplicate
    for k, v in out.items():
        out[k] = _dedup_keep_order([_norm_path(x) for x in v if x])

    return out


# ----------------------- YAML emitter (Comfy extra paths) -----------------------

def _render_extra_yaml(models_map: Dict[str, List[str]], custom_nodes: List[str]) -> str:
    """
    Compose a Comfy-shaped YAML file that extra_config loader accepts:

    comfyui:
      checkpoints: <string or block scalar>
      diffusion_models: |
        path1
        path2
      custom_nodes: |
        E:/.../custom_nodes
        ${LOCALAPPDATA}/.../custom_nodes
    """

    def _emit_key(lines: List[str], key: str, vals: List[str]) -> None:
        vals = [v for v in vals if v]
        if not vals:
            return
        if len(vals) == 1:
            lines.append(f"  {key}: {vals[0]}")
        else:
            lines.append(f"  {key}: |")
            for v in vals:
                lines.append(f"    {v}")

    lines: List[str] = ["comfyui:"]
    for cat in _CATEGORY_KEYS_ORDER:
        _emit_key(lines, cat, models_map.get(cat, []))

    if custom_nodes:
        _emit_key(lines, "custom_nodes", custom_nodes)

    return "\n".join(lines) + "\n"


# ----------------------- runtime wrapper -----------------------

class RuntimeConfig:
    """
    Output of ConfigManager.build_runtime().
    """

    def __init__(self, argv: List[str], env: Dict[str, str], extra_paths_file: Optional[str]):
        self.argv = argv
        self.env = env
        self.extra_paths_file = extra_paths_file


# ----------------------- ConfigManager -----------------------

class ConfigManager:
    """
    Controller-aware configuration loader & builder.

    - If COMFY_CONFIG points to a *controller* (has "layers"/"yaml_layers"):
        * merges the Remote JSON stack  → ComfyConfig (server/paths/env)
        * merges the Comfy YAML stack  → mapped into ComfyConfig (io/paths) and
          retained for debug via `debug_comfy_yaml_text()`
    - Otherwise, legacy single-file load (JSON or YAML with server/io/paths/env).
    - Expands models_root into category slots.
    - Writes a Comfy-shaped extra_model_paths.yaml from merged paths/custom_nodes.
    - Provides:
        * finalize() -> ComfyConfig
        * build_runtime(cfg) -> RuntimeConfig
        * debug_expanded_yaml_text(cfg)  (expanded ComfyConfig snapshot)
        * debug_comfy_yaml_text(expand=...) (merged Comfy-side YAML)
    """

    """
    Controller-aware configuration loader & builder.
    ...
    """

    # ---- Singleton plumbing ----
    _instance: Optional["ConfigManager"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        # Process-wide singleton
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def instance(cls) -> "ConfigManager":
        """Preferred accessor."""
        return cls()

    @classmethod
    def reset_instance(cls) -> None:
        """For tests or hard resets."""
        with cls._lock:
            cls._instance = None

    def __init__(self) -> None:
        # Avoid re-running init on repeated __new__ returns
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        # Debug/trace fields populated when controller is used
        self._last_controller_path: Optional[str] = None
        self._last_json_layer_files: List[str] = []
        self._last_yaml_layer_files: List[str] = []
        self._last_merged_remote_json: Dict[str, Any] = {}
        self._last_merged_comfy_yaml: Dict[str, Any] = {}
        self.cfg = self.finalize()

    # -------- controller helpers --------
    def _default_controller_path(self) -> Optional[Path]:
        """
        Fallback to ${PKG}/config/defaults/default.json if present.
        """
        here = Path(__file__).resolve()
        ctrl = here.parent / "defaults" / "default.json"
        return ctrl if ctrl.exists() else None

    @staticmethod
    def _is_controller_dict(obj: Any) -> bool:
        return isinstance(obj, dict) and ("layers" in obj or "yaml_layers" in obj)

    def _load_via_controller(self, controller_path: Path) -> ComfyConfig:
        """
        Use layering.py to merge Remote JSON layers and Comfy YAML layers,
        then map into ComfyConfig.
        """
        # 1) Load controller (already expands ${PKG} and ${OS} inside 'path' fields)
        ctrl = load_controller(str(controller_path))

        # 2) Resolve actual JSON/YAML files and keep only those that exist
        json_files: List[str] = []
        for ent in ctrl.get("layers", []) or []:
            p = (ent.get("path") if isinstance(ent, dict) else ent) or ""
            if not p:
                continue
            r = resolve_layer_path(p, expect="json")
            if r and r.exists():
                json_files.append(str(r))

        yaml_files: List[str] = []
        for ent in ctrl.get("yaml_layers", []) or []:
            p = (ent.get("path") if isinstance(ent, dict) else ent) or ""
            if not p:
                continue
            r = resolve_layer_path(p, expect="yaml")
            if r and r.exists():
                yaml_files.append(str(r))

        # 3) Merge both stacks
        merged_remote = merge_json_layers(json_files) if json_files else {}
        merged_comfy = merge_yaml_layers(yaml_files) if yaml_files else {}

        # 4) Stash for debug
        self._last_controller_path = str(controller_path)
        self._last_json_layer_files = list(json_files)
        self._last_yaml_layer_files = list(yaml_files)
        self._last_merged_remote_json = dict(merged_remote)
        self._last_merged_comfy_yaml = dict(merged_comfy)

        # 5) Map into ComfyConfig (Remote JSON first; YAML fills IO and complements paths/env)
        cfg = ComfyConfig()

        # server (prefer remote JSON; fallback to YAML)
        srv = (merged_remote.get("server") or merged_comfy.get("server") or {})
        if isinstance(srv, dict):
            cfg.server.host = str(srv.get("host", cfg.server.host))
            cfg.server.port = int(srv.get("port", cfg.server.port or 0) or 0)
            cfg.server.disable_cuda_malloc = bool(srv.get("disable_cuda_malloc", cfg.server.disable_cuda_malloc))
            cfg.server.dont_print_server = bool(srv.get("dont_print_server", cfg.server.dont_print_server))
            cfg.server.extra_args = list(srv.get("extra_args", cfg.server.extra_args or [])) or []

        # io (prefer YAML; that's your intent: IO belongs to Comfy side)
        io = merged_comfy.get("io") or merged_remote.get("io") or {}
        if isinstance(io, dict):
            cfg.io.input_dir = str(io.get("input_dir", cfg.io.input_dir))
            cfg.io.output_dir = str(io.get("output_dir", cfg.io.output_dir))
            cfg.io.temp_dir = str(io.get("temp_dir", cfg.io.temp_dir))
            cfg.io.user_dir = str(io.get("user_dir", cfg.io.user_dir))

        # paths (merge JSON + YAML; JSON wins on conflicts; custom_nodes union)
        jp = merged_remote.get("paths") or {}
        yp = merged_comfy.get("paths") or {}
        if isinstance(jp, dict) or isinstance(yp, dict):
            cfg.paths.home = str((jp.get("home") if isinstance(jp, dict) else None) or
                                 (yp.get("home") if isinstance(yp, dict) else "") or cfg.paths.home)
            cfg.paths.models_root = str((jp.get("models_root") if isinstance(jp, dict) else None) or
                                        (yp.get("models_root") if isinstance(yp,
                                                                             dict) else "") or cfg.paths.models_root)

            # models map — normalize and union (JSON overrides by concatenation order)
            def _norm_models(d: Any) -> Dict[str, List[str]]:
                out: Dict[str, List[str]] = {}
                if isinstance(d, dict):
                    for k, v in d.items():
                        if isinstance(v, str):
                            out[k] = [v]
                        elif isinstance(v, (list, tuple)):
                            out[k] = [str(x) for x in v]
                        else:
                            out[k] = [str(v)]
                return out

            models_y = _norm_models(yp.get("models") if isinstance(yp, dict) else {})
            models_j = _norm_models(jp.get("models") if isinstance(jp, dict) else {})
            merged_models: Dict[str, List[str]] = {}
            # YAML first, then JSON so JSON order/paths appear later (and we dedup later)
            for src in (models_y, models_j):
                for k, v in src.items():
                    merged_models.setdefault(k, [])
                    merged_models[k].extend(v)
            # De-dup while preserving order
            for k, v in list(merged_models.items()):
                merged_models[k] = _dedup_keep_order([_norm_path(x) for x in v if x])

            cfg.paths.models = merged_models

            # custom_nodes union (YAML + JSON)
            cn: List[str] = []
            if isinstance(yp, dict):
                cn.extend(_ensure_list(yp.get("custom_nodes")))
            if isinstance(jp, dict):
                cn.extend(_ensure_list(jp.get("custom_nodes")))
            cfg.paths.custom_nodes = _dedup_keep_order([_norm_path(x) for x in cn if x])

        # env (merge; JSON wins on conflicts)
        env_m: Dict[str, str] = {}
        if isinstance(merged_comfy.get("env"), dict):
            for k, v in merged_comfy["env"].items():
                env_m[k] = str(v)
        if isinstance(merged_remote.get("env"), dict):
            for k, v in merged_remote["env"].items():
                env_m[k] = str(v)
        cfg.env = env_m

        return cfg

    # -------- legacy single-file loader --------

    def _load_single_file(self, p: Path) -> ComfyConfig:
        """
        Legacy path: load a single JSON or YAML file with server/io/paths/env.
        """
        cfg = ComfyConfig()
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            return cfg

        data: Dict[str, Any] = {}
        if p.suffix.lower() in (".yaml", ".yml"):
            try:
                import yaml  # type: ignore
                data = yaml.safe_load(text) or {}
            except Exception:
                data = {}
        else:
            try:
                data = json.loads(text)
            except Exception:
                data = {}

        # server
        s = data.get("server", {})
        cfg.server.host = s.get("host", cfg.server.host)
        cfg.server.port = int(s.get("port", cfg.server.port or 0) or 0)
        cfg.server.disable_cuda_malloc = bool(s.get("disable_cuda_malloc", cfg.server.disable_cuda_malloc))
        cfg.server.dont_print_server = bool(s.get("dont_print_server", cfg.server.dont_print_server))
        cfg.server.extra_args = list(s.get("extra_args", cfg.server.extra_args or [])) or []

        # io
        io = data.get("io", {})
        cfg.io.input_dir = io.get("input_dir", cfg.io.input_dir)
        cfg.io.output_dir = io.get("output_dir", cfg.io.output_dir)
        cfg.io.temp_dir = io.get("temp_dir", cfg.io.temp_dir)
        cfg.io.user_dir = io.get("user_dir", cfg.io.user_dir)

        # paths
        pths = data.get("paths", {})
        cfg.paths.home = pths.get("home", cfg.paths.home)
        cfg.paths.models_root = pths.get("models_root", cfg.paths.models_root)

        explicit_models = {}
        models = pths.get("models", {})
        if isinstance(models, dict):
            for k, v in models.items():
                explicit_models[k] = [_norm_path(x) for x in _ensure_list(v)]
        cfg.paths.models = explicit_models

        cfg.paths.custom_nodes = _dedup_keep_order([_norm_path(x) for x in _ensure_list(pths.get("custom_nodes", []))])

        # env
        env = data.get("env", {})
        for k, v in env.items():
            cfg.env[k] = str(v)

        # not a controller; clear debug stash
        self._last_controller_path = None
        self._last_json_layer_files = []
        self._last_yaml_layer_files = []
        self._last_merged_remote_json = {}
        self._last_merged_comfy_yaml = {}

        return cfg

    # -------- core load & resolve --------

    def load(self) -> ComfyConfig:
        """
        Load config.
        Priority:
          1) COMFY_CONFIG (env var). If it is a controller (has layers/yaml_layers),
             perform layer merges. Otherwise treat as legacy single file.
          2) Fallback to ${PKG}/config/defaults/default.json controller if present.
          3) Else return defaults.
        """
        cfg_path_env = self._default_controller_path()

        if cfg_path_env:
            p = Path(cfg_path_env)
            if p.exists():
                # Try to determine if controller by content
                try:
                    txt = p.read_text(encoding="utf-8")
                    data: Dict[str, Any] = {}
                    if p.suffix.lower() == ".json":
                        data = json.loads(txt)
                    else:
                        try:
                            import yaml  # type: ignore
                            data = yaml.safe_load(txt) or {}
                        except Exception:
                            data = {}
                except Exception:
                    data = {}

                if self._is_controller_dict(data):
                    return self._load_via_controller(p)
                # legacy single-file
                return self._load_single_file(p)
        # else:
        # No COMFY_CONFIG or file missing: try default controller next
        ctrl = self._default_controller_path()
        if ctrl and ctrl.exists():
            return self._load_via_controller(ctrl)

        # Last resort: blank defaults
        return ComfyConfig()

    def _resolve(self, cfg: ComfyConfig) -> ComfyConfig:
        """
        Resolve env vars and paths; choose port if needed; expand models map.
        Expands:
          - ${ENV:VAR} (manager's token style)
          - $VAR / ${VAR} (shell style)
          - ~            (home)
        Expansion uses:  env_for_expand = os.environ + cfg.env
        """

        # Merge expansion environment: do NOT mutate os.environ
        env_for_expand = os.environ.copy()
        for k, v in (cfg.env or {}).items():
            env_for_expand[k] = str(v)

        # Local normalizer that expands tokens and normalizes slashes
        def NX(s: str) -> str:
            if not s:
                return s
            s2 = _expand_all_tokens(s, env_for_expand)
            return str(Path(s2)).replace("\\", "/")

        # ---------------- host & port ----------------
        cfg.server.host = _expand_all_tokens(cfg.server.host or "127.0.0.1", env_for_expand)
        if not cfg.server.host:
            cfg.server.host = "127.0.0.1"

        if not cfg.server.port or cfg.server.port == 0:
            cfg.server.port = _find_free_port()

        # Optional: expand any tokens in extra args
        if cfg.server.extra_args:
            cfg.server.extra_args = [_expand_all_tokens(str(a), env_for_expand) for a in cfg.server.extra_args]

        # ---------------- IO dirs (YAML side usually) ----------------
        cfg.io.input_dir = NX(cfg.io.input_dir)
        cfg.io.output_dir = NX(cfg.io.output_dir)
        cfg.io.temp_dir = NX(cfg.io.temp_dir)
        cfg.io.user_dir = NX(cfg.io.user_dir)

        # ---------------- paths ----------------
        cfg.paths.home = NX(cfg.paths.home)
        cfg.paths.models_root = NX(cfg.paths.models_root)

        # Normalize explicit per-category paths
        explicit: Dict[str, List[str]] = {}
        for k, v in (cfg.paths.models or {}).items():
            explicit[k] = [NX(x) for x in v]
        cfg.paths.models = explicit

        cfg.paths.custom_nodes = _dedup_keep_order([NX(x) for x in (cfg.paths.custom_nodes or [])])

        # Expand models map with root (fills missing categories as <root>/models/<cat>)
        cfg.paths.models = _expand_models_with_root(cfg.paths.models_root, cfg.paths.models)

        # ---------------- env values ----------------
        expanded_env: Dict[str, str] = {}
        for k, v in (cfg.env or {}).items():
            expanded_env[k] = _expand_all_tokens(str(v), env_for_expand)
        cfg.env = expanded_env

        return cfg

    # -------- public surface --------

    def finalize(self) -> ComfyConfig:
        """
        Load and return a fully-resolved configuration snapshot.
        If COMFY_CONFIG points to a controller, this performs both JSON/YAML merges.
        """
        raw = self.load()
        self.cfg = self._resolve(raw)
        self.export_env_vars()
        return self.cfg

    @classmethod
    def reload(cls) -> ComfyConfig:
        """Explicit re-merge of all layers with current environment."""
        return cls.instance().reload()

    def export_env_vars(
            self,
            *,
            override: bool = False,
            set_defaults: bool = True,
    ) -> Dict[str, str]:
        """
        Export environment variables for the ComfyUI child process.

        Precedence (low ➜ high):
          1) Computed defaults (COMFYUI_HOME, privacy toggles, optional HF caches)
             — applied only if unset in the current process, unless override=True.
          2) Existing os.environ
          3) cfg.env (your merged config) — ALWAYS wins last.

        Returns a dict of the variables this method actively set/changed.
        """
        if not getattr(self, "cfg", None):
            self.finalize()
        cfg = self.cfg

        exported: Dict[str, str] = {}

        # ---------- 1) computed defaults ----------
        defaults: Dict[str, str] = {}

        # Always provide COMFYUI_HOME so ${ENV:COMFYUI_HOME} in YAML can be resolved.
        if cfg.paths.home:
            defaults["COMFYUI_HOME"] = _norm_path(cfg.paths.home)

        # Privacy/telemetry + tokenizer parallelism (quiet & predictable by default).
        if set_defaults:
            defaults.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")  # HF hub opt-out
            defaults.setdefault("DO_NOT_TRACK", "1")
            defaults.setdefault("TOKENIZERS_PARALLELISM", "false")

        # Place HF caches under io.user_dir when available (keeps things tidy).
        if set_defaults and cfg.io.user_dir:
            hf_home = _join(cfg.io.user_dir, "hf")
            defaults.setdefault("HF_HOME", hf_home)
            defaults.setdefault("HUGGINGFACE_HUB_CACHE", _join(hf_home, "hub"))
            defaults.setdefault("TRANSFORMERS_CACHE", _join(hf_home, "transformers"))

        # ---------- 2) apply computed defaults ----------
        for k, v in defaults.items():
            if override or k not in os.environ:
                os.environ[k] = v
                exported[k] = v

        # ---------- 3) apply cfg.env (wins last) ----------
        # Note: values in cfg.env may themselves contain $VAR / ~ etc.; expand once here.
        for k, v in (cfg.env or {}).items():
            vv = os.path.expandvars(os.path.expanduser(str(v)))
            os.environ[k] = vv
            exported[k] = vv

        return exported

    def build_runtime(self, cfg: ComfyConfig) -> RuntimeConfig:
        """
        Build argv/env for launching ComfyUI (matching main.py’s CLI),
        and emit a Comfy-shaped extra_model_paths YAML if needed.
        """
        argv: List[str] = [
            "--listen", cfg.server.host,
            "--port", str(cfg.server.port or 0),
        ]
        if cfg.io.output_dir:
            argv += ["--output-directory", cfg.io.output_dir]
        if cfg.io.input_dir:
            argv += ["--input-directory", cfg.io.input_dir]
        if cfg.io.temp_dir:
            argv += ["--temp-directory", cfg.io.temp_dir]
        if cfg.io.user_dir:
            argv += ["--user-directory", cfg.io.user_dir]

        if cfg.server.disable_cuda_malloc:
            argv.append("--disable-cuda-malloc")
        if cfg.server.dont_print_server:
            argv.append("--dont-print-server")
        if cfg.server.extra_args:
            argv += [str(x) for x in cfg.server.extra_args]

        extra_yaml = self.write_extra_paths_yaml_strings(cfg)

        env = os.environ.copy()
        env.update(cfg.env)

        return RuntimeConfig(argv=argv, env=env, extra_paths_file=extra_yaml)

    # Backward-compat helper used by some code paths
    def write_extra_paths_yaml_strings(self, cfg: ComfyConfig) -> Optional[str]:
        """
        Emit a temporary YAML file that Comfy's `utils.extra_config.load_extra_path_config`
        can parse (top-level `comfyui:` with categories and optional `custom_nodes`).
        Returns the file path, or None if there is nothing to write.
        """
        models_map = cfg.paths.models or {}
        custom_nodes = cfg.paths.custom_nodes or []
        has_any = any(models_map.get(k) for k in _CATEGORY_KEYS_ORDER) or bool(custom_nodes)
        if not has_any:
            return None

        text = _render_extra_yaml(models_map, custom_nodes)
        fd, tmp = tempfile.mkstemp(prefix="extra_model_paths_", suffix=".yaml")
        os.close(fd)
        Path(tmp).write_text(text, encoding="utf-8")
        return tmp

    # -------- Debug / Introspection helpers --------

    def debug_expanded_snapshot(self, cfg: Optional["ComfyConfig"] = None) -> Dict[str, Any]:
        """
        Return a deep-expanded dict equivalent to cfg.to_dict(),
        where ${ENV:VAR}, $VAR and ~ are resolved using current os.environ.
        For printing only; does not affect runtime.
        """
        cfg = cfg or self.finalize()
        raw = cfg.to_dict()
        return _deep_expand_debug(raw, os.environ)

    def debug_expanded_yaml_text(self, cfg: Optional["ComfyConfig"] = None) -> str:
        """
        Pretty YAML (or JSON fallback) of the expanded ComfyConfig snapshot.
        """
        expanded = self.debug_expanded_snapshot(cfg)
        try:
            import yaml  # type: ignore
            return yaml.safe_dump(expanded, sort_keys=False)
        except Exception:
            return json.dumps(expanded, indent=2, ensure_ascii=False)

    # Merged Comfy YAML (controller path only). Useful for debugging.
    def debug_get_comfy_yaml(self, expand: bool = False) -> Dict[str, Any]:
        y = dict(self._last_merged_comfy_yaml or {})
        if expand:
            return _deep_expand_debug(y, os.environ)
        return y

    def debug_comfy_yaml_text(self, expand: bool = False) -> str:
        y = self.debug_get_comfy_yaml(expand=expand)
        try:
            import yaml  # type: ignore
            return yaml.safe_dump(y, sort_keys=False)
        except Exception:
            return json.dumps(y, indent=2, ensure_ascii=False)

    # Optional: expose which files were used
    def debug_controller_sources(self) -> Dict[str, Any]:
        return {
            "controller": self._last_controller_path,
            "json_layers": list(self._last_json_layer_files),
            "yaml_layers": list(self._last_yaml_layer_files),
        }
