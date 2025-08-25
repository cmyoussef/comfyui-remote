# src/comfyui_remote/config/config_helpers.py
from __future__ import annotations

import json
import os
import re
import socket
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ----------------------- token & path helpers -----------------------

_TOKEN_RE = re.compile(r"\$\{([^}]+)\}")

def _os_tag() -> str:
    s = os.name.lower()
    if s == "nt": return "windows"
    # sys.platform would be even more precise, but this is good enough here
    if s == "posix":
        # rough split: darwin vs linux
        try:
            import sys
            return "darwin" if sys.platform == "darwin" else "linux"
        except Exception:
            return "linux"
    return "linux"

def _default_pkg_root() -> str:
    # config_helpers.py -> config/ -> comfyui_remote/
    return str(Path(__file__).resolve().parent.parent)

def expand_token_value(tok: str, env: Optional[Dict[str, str]] = None) -> str:
    """
    Expand a single ${...} token with sensible defaults:
      - ${ENV:VAR}      -> env['VAR'] or ""
      - ${PKG}          -> env['PKG'] or package root (…/src/comfyui_remote)
      - ${OS}           -> env['OS'] or 'windows|linux|darwin' (auto)
      - ${HOME}         -> env['HOME'] or Path.home()
      - ${USERPROFILE}  -> env['USERPROFILE'] or ""
      - ${VAR}          -> env['VAR'] or ""
    """
    env = env or os.environ
    if tok.startswith("ENV:"):
        return env.get(tok[4:], "") or ""
    if tok == "PKG":
        return env.get("PKG") or _default_pkg_root()
    if tok == "OS":
        return env.get("OS") or _os_tag()
    if tok == "HOME":
        return env.get("HOME") or str(Path.home())
    if tok == "USERPROFILE":
        return env.get("USERPROFILE", "") or ""
    return env.get(tok, "") or ""

def expand_string_templates(s: str, env: Optional[Dict[str, str]] = None) -> str:
    """Replace ${...} tokens; does not validate paths."""
    if not isinstance(s, str): return s
    return _TOKEN_RE.sub(lambda m: expand_token_value(m.group(1), env), s)

def expand_all_tokens(s: str, env: Optional[Dict[str, str]] = None) -> str:
    """
    Expand:
      - our style ${ENV:FOO} / ${PKG} / ${OS} …
      - shell vars $FOO / ${FOO}
      - ~ (home)
    """
    if not isinstance(s, str): return s
    s = expand_string_templates(s, env)
    s = os.path.expandvars(s)
    s = os.path.expanduser(s)
    return s

def norm_path(path: str, env: Optional[Dict[str, str]] = None) -> str:
    if not path: return path
    p = expand_all_tokens(path, env)
    return str(Path(p)).replace("\\", "/")

def dedup_keep_order(items: Iterable[str]) -> List[str]:
    seen, out = set(), []
    for x in items or []:
        if not x: continue
        if x not in seen:
            out.append(x); seen.add(x)
    return out

def ensure_list(v: Any) -> List[str]:
    if v is None: return []
    if isinstance(v, str): return [v]
    if isinstance(v, (list, tuple)): return [str(x) for x in v]
    return [str(v)]

def find_free_port(host: str = "127.0.0.1") -> int:
    import socket as _s
    with _s.socket(_s.AF_INET, _s.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]

# ----------------------- controller + layering helpers -----------------------

def _expand_controller_paths(obj: Any, env: Optional[Dict[str, str]] = None) -> Any:
    if not isinstance(obj, dict): return obj
    out = dict(obj)

    def _norm_layers(key: str) -> None:
        layers = out.get(key)
        if not isinstance(layers, list): return
        new_layers: List[Dict[str, Any]] = []
        for ent in layers:
            if isinstance(ent, dict):
                ent2 = dict(ent)
                if "path" in ent2 and ent2["path"] is not None:
                    ent2["path"] = expand_string_templates(str(ent2["path"]), env)
                new_layers.append(ent2)
            else:
                new_layers.append(ent)
        out[key] = new_layers

    _norm_layers("layers")
    _norm_layers("yaml_layers")

    sm = out.get("server_management")
    if isinstance(sm, dict) and sm.get("registry_path") is not None:
        sm2 = dict(sm)
        sm2["registry_path"] = expand_string_templates(str(sm2["registry_path"]), env)
        out["server_management"] = sm2

    return out

def load_controller(controller_path: str | os.PathLike[str],
                    env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    p = Path(controller_path)
    try:
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        data = {}
    return _expand_controller_paths(data, env=env)

def _safe_path_from_pattern(pattern: str) -> Optional[Path]:
    if not pattern or not isinstance(pattern, str): return None
    s = pattern.strip()
    if not s: return None
    try:
        p = Path(s)
        _ = p.name
    except Exception:
        return None
    if p.name == "": return None
    return p

def resolve_layer_path(pattern: str, expect: str) -> Optional[Path]:
    p = _safe_path_from_pattern(pattern)
    if p is None: return None

    suf = p.suffix.lower()
    if suf in (".json", ".yaml", ".yml"):
        return p if p.exists() else None

    candidates: List[Path] = []
    try:
        if expect == "json":
            candidates.append(p.with_suffix(".json"))
        elif expect == "yaml":
            candidates += [p.with_suffix(".yaml"), p.with_suffix(".yml")]
        else:
            candidates += [p.with_suffix(".json"), p.with_suffix(".yaml"), p.with_suffix(".yml")]
    except ValueError:
        return None

    for c in candidates:
        if c.exists(): return c
    return None

def deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out

def merge_json_layers(paths: Iterable[str]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for p in paths or []:
        try:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
            if isinstance(data, dict):
                merged = deep_merge(merged, data)
        except Exception:
            continue
    return merged

def merge_yaml_layers(paths: Iterable[str]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    try:
        import yaml  # type: ignore
    except Exception:
        return merged
    for p in paths or []:
        try:
            data = yaml.safe_load(Path(p).read_text(encoding="utf-8")) or {}
            if isinstance(data, dict):
                merged = deep_merge(merged, data)
        except Exception:
            continue
    return merged

# ----------------------- models & extra YAML -----------------------

CATEGORY_KEYS_ORDER = [
    "checkpoints", "vae", "clip", "clip_vision",
    "diffusion_models", "unet",
    "loras", "embeddings", "controlnet",
    "upscale_models", "configs",
]

def expand_models_with_root(models_root: str, explicit: Dict[str, List[str]],
                            env: Optional[Dict[str, str]] = None) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {k: list(v) for k, v in (explicit or {}).items()}

    root = norm_path(models_root, env) if models_root else ""
    if root:
        for cat in CATEGORY_KEYS_ORDER:
            if cat not in out or not out[cat]:
                out.setdefault(cat, []).append(f"{root}/models/{cat}")

    for k, v in out.items():
        out[k] = dedup_keep_order(norm_path(x, env) for x in v if x)
    return out

def render_extra_yaml(models_map: Dict[str, List[str]], custom_nodes: List[str]) -> str:
    def _emit_key(lines: List[str], key: str, vals: List[str]) -> None:
        vals = [v for v in vals if v]
        if not vals: return
        if len(vals) == 1:
            lines.append(f"  {key}: {vals[0]}")
        else:
            lines.append(f"  {key}: |")
            for v in vals:
                lines.append(f"    {v}")

    lines: List[str] = ["comfyui:"]
    for cat in CATEGORY_KEYS_ORDER:
        _emit_key(lines, cat, models_map.get(cat, []))

    if custom_nodes:
        _emit_key(lines, "custom_nodes", custom_nodes)
    return "\n".join(lines) + "\n"

def write_temp(text: str, prefix: str, suffix: str) -> str:
    fd, tmp = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    os.close(fd)
    Path(tmp).write_text(text, encoding="utf-8")
    return tmp
