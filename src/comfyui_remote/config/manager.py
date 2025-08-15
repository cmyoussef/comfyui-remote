# src/comfyui_remote/config/manager.py
from __future__ import annotations

import os
import json
import socket
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional

from .types import ComfyConfig, ServerConfig, IOConfig, PathsConfig


# ----------------------- path & misc helpers -----------------------

def _expand_vars(path: str) -> str:
    """
    Expand ${ENV_VARS}, %WINVAR%, and ~ in a path string.
    """
    if not path:
        return path
    # First expand env vars, then ~
    expanded = os.path.expandvars(path)
    expanded = os.path.expanduser(expanded)
    return expanded


def _norm_path(path: str) -> str:
    """
    Normalize a path and prefer forward slashes (Comfy tolerates both on Windows).
    """
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
                # All categories live under "<root>/models/<category>"
                candidate = f"{root}/models/{cat}"
                out.setdefault(cat, []).append(candidate)

    # Normalize + de-duplicate
    for k, v in out.items():
        out[k] = _dedup_keep_order([_norm_path(x) for x in v if x])

    return out


# ----------------------- YAML emitter (Comfy shape) -----------------------

def _render_extra_yaml(models_map: Dict[str, List[str]], custom_nodes: List[str]) -> str:
    """
    Compose a Comfy-shaped YAML file:

    comfyui:
      checkpoints: <string or block scalar>
      diffusion_models: |
        path1
        path2
      custom_nodes: |
        E:/comfyui/comfyui/custom_nodes
        ${LOCALAPPDATA}/Programs/@comfyorgcomfyui-electron/resources/ComfyUI/custom_nodes
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

    # top-level group
    lines: List[str] = ["comfyui:"]
    for cat in _CATEGORY_KEYS_ORDER:
        _emit_key(lines, cat, models_map.get(cat, []))

    if custom_nodes:
        # treat custom_nodes like any other multi-path category
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
    YAML-first configuration loader & builder.

    - Reads path from COMFY_CONFIG (YAML strongly recommended; JSON supported)
    - Expands ${ENV} and ~ in paths
    - Allows a single 'models_root'; fills missing categories from it
    - Writes a Comfy-shaped extra_model_paths.yaml
    - Builds argv/env for launching ComfyUI
    - Provides both:
        * finalize() -> ComfyConfig   (resolved snapshot)
        * build_runtime(cfg) -> RuntimeConfig (argv/env + temp YAML path)
      plus a write_extra_paths_yaml_strings(cfg) for backward compatibility.
    """

    def __init__(self, env_var: str = "COMFY_CONFIG"):
        self._env_var = env_var

    # -------- core load & merge --------

    def load(self) -> ComfyConfig:
        """
        Load raw config from COMFY_CONFIG. Missing file => defaults.
        YAML is preferred. JSON supported.
        """
        cfg = ComfyConfig()  # defaults

        path = os.getenv(self._env_var, "")
        if not path:
            return cfg

        p = Path(path)
        if not p.exists():
            return cfg

        text = p.read_text(encoding="utf-8")
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
        cfg.server.port = int(s.get("port", cfg.server.port))
        cfg.server.disable_cuda_malloc = bool(s.get("disable_cuda_malloc", cfg.server.disable_cuda_malloc))
        cfg.server.dont_print_server = bool(s.get("dont_print_server", cfg.server.dont_print_server))
        cfg.server.extra_args = list(s.get("extra_args", cfg.server.extra_args or [])) or []

        # io
        io = data.get("io", {})
        cfg.io.input_dir  = io.get("input_dir",  cfg.io.input_dir)
        cfg.io.output_dir = io.get("output_dir", cfg.io.output_dir)
        cfg.io.temp_dir   = io.get("temp_dir",   cfg.io.temp_dir)
        cfg.io.user_dir   = io.get("user_dir",   cfg.io.user_dir)

        # paths
        pths = data.get("paths", {})
        cfg.paths.home = pths.get("home", cfg.paths.home)
        cfg.paths.models_root = pths.get("models_root", cfg.paths.models_root)

        # explicit per-category model paths
        explicit_models = {}
        models = pths.get("models", {})
        if isinstance(models, dict):
            for k, v in models.items():
                explicit_models[k] = [_norm_path(x) for x in _ensure_list(v)]
        cfg.paths.models = explicit_models

        # custom_nodes
        cfg.paths.custom_nodes = _dedup_keep_order([_norm_path(x) for x in _ensure_list(pths.get("custom_nodes", []))])

        # env
        env = data.get("env", {})
        for k, v in env.items():
            cfg.env[k] = str(v)

        return cfg

    def _resolve(self, cfg: ComfyConfig) -> ComfyConfig:
        """
        Resolve env vars and paths; choose port if needed; expand models map.
        """
        # host & port
        if not cfg.server.host:
            cfg.server.host = "127.0.0.1"
        if not cfg.server.port or cfg.server.port == 0:
            cfg.server.port = _find_free_port()

        # IO dirs
        cfg.io.input_dir  = _norm_path(cfg.io.input_dir)
        cfg.io.output_dir = _norm_path(cfg.io.output_dir)
        cfg.io.temp_dir   = _norm_path(cfg.io.temp_dir)
        cfg.io.user_dir   = _norm_path(cfg.io.user_dir)

        # paths
        cfg.paths.home = _norm_path(cfg.paths.home)
        cfg.paths.models_root = _norm_path(cfg.paths.models_root)

        explicit = {}
        for k, v in (cfg.paths.models or {}).items():
            explicit[k] = [_norm_path(x) for x in v]
        cfg.paths.models = explicit

        cfg.paths.custom_nodes = _dedup_keep_order([_norm_path(x) for x in cfg.paths.custom_nodes])

        # expand models map with root
        cfg.paths.models = _expand_models_with_root(cfg.paths.models_root, cfg.paths.models)

        # simple env var expansion in values (no recursion)
        expanded_env: Dict[str, str] = {}
        for k, v in (cfg.env or {}).items():
            expanded_env[k] = os.path.expandvars(os.path.expanduser(str(v)))
        cfg.env = expanded_env

        return cfg

    # -------- public surface --------

    def finalize(self) -> ComfyConfig:
        """
        Load and return a fully-resolved configuration snapshot.
        """
        raw = self.load()
        return self._resolve(raw)

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
