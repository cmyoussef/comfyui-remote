# src/comfyui_remote/config/layering.py
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - YAML is optional for import-time
    yaml = None


# -----------------------------------------------------------------------------
# Token expansion
# -----------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\$\{([^}]+)\}")

def _expand_token(tok: str) -> str:
    """
    Expand a single ${...} token:
      - ${ENV:VAR}  -> os.environ.get("VAR", "")
      - ${PKG}      -> os.environ.get("PKG", "")
      - ${OS}       -> os.environ.get("OS", "")
      - ${HOME}     -> os.environ.get("HOME") or Path.home()
      - ${USERPROFILE} (windows friendliness) -> env value
      - ${VAR}      -> os.environ.get("VAR", "")
    Unknown tokens expand to "" (empty) so higher layers can be optional.
    """
    if tok.startswith("ENV:"):
        return os.environ.get(tok[4:], "") or ""
    if tok in ("PKG", "OS", "HOME", "USERPROFILE"):
        if tok == "HOME":
            return os.environ.get("HOME") or str(Path.home())
        return os.environ.get(tok, "") or ""
    # generic env fallback
    return os.environ.get(tok, "") or ""


def _expand_string_templates(s: str) -> str:
    """
    Replace ${...} tokens in a string. If an expansion yields a broken path
    with doubled separators (e.g., //something) we leave it as-is here and let
    resolver validate/skip it safely.
    """
    if not s or not isinstance(s, str):
        return s
    return _TOKEN_RE.sub(lambda m: _expand_token(m.group(1)), s)


def _expand_controller_paths(obj: Any) -> Any:
    """
    Walk the controller dict and expand ${...} only inside 'path' fields for
    layers/yaml_layers and a few well-known keys under server_management.
    We leave other values alone.
    """
    if not isinstance(obj, dict):
        return obj

    out = dict(obj)

    def _norm_layers(key: str) -> None:
        layers = out.get(key)
        if not isinstance(layers, list):
            return
        new_layers: List[Dict[str, Any]] = []
        for ent in layers:
            if isinstance(ent, dict):
                ent2 = dict(ent)
                if "path" in ent2 and ent2["path"] is not None:
                    ent2["path"] = _expand_string_templates(str(ent2["path"]))
                new_layers.append(ent2)
            else:
                new_layers.append(ent)
        out[key] = new_layers

    _norm_layers("layers")
    _norm_layers("yaml_layers")

    sm = out.get("server_management")
    if isinstance(sm, dict) and "registry_path" in sm and sm["registry_path"] is not None:
        sm = dict(sm)
        sm["registry_path"] = _expand_string_templates(str(sm["registry_path"]))
        out["server_management"] = sm

    return out


# -----------------------------------------------------------------------------
# Controller load / normalization
# -----------------------------------------------------------------------------

def load_controller(controller_path: str | os.PathLike[str]) -> Dict[str, Any]:
    """
    Load the JSON controller (default.json) and return a dict with ${...}
    expanded in the layer 'path' fields and server_management.registry_path.
    """
    p = Path(controller_path)
    data: Dict[str, Any] = {}
    try:
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        data = {}
    return _expand_controller_paths(data)


def normalize_layer_entries(entries: Any) -> List[str]:
    """
    Normalize a 'layers' / 'yaml_layers' array into a simple list of path
    *patterns* (may be extensionless). We skip null/empty paths; resolution is
    done later.
    """
    out: List[str] = []
    if not isinstance(entries, list):
        return out
    for ent in entries:
        if isinstance(ent, dict):
            path = ent.get("path")
            if isinstance(path, str) and path.strip():
                out.append(path.strip())
        elif isinstance(ent, str) and ent.strip():
            out.append(ent.strip())
    return out


# -----------------------------------------------------------------------------
# Path resolution (robust against empty-name UNC, missing tokens, etc.)
# -----------------------------------------------------------------------------

def _safe_path_from_pattern(pattern: str) -> Optional[Path]:
    """
    Turn a controller path pattern into a Path safely:
      - If after expansion/basename check there's no file name (e.g. '//' UNC),
        return None.
      - We do *not* require existence here.
    """
    if not pattern or not isinstance(pattern, str):
        return None

    s = pattern.strip()
    if not s:
        return None

    # Early reject bare UNC / drive anchors that have no name component
    # Windows UNC like '//' or '//server' may still yield empty name cases.
    # Pathlib with_suffix() requires a non-empty name.
    p = Path(s)
    try:
        name = p.name
    except Exception:
        return None

    if name == "":  # e.g., '//' or '//server' (empty tail), or trailing slash-only
        return None

    return p


def resolve_layer_path(pattern: str, expect: str) -> Optional[Path]:
    """
    Resolve a controller 'path' entry to a concrete file path:
      - If pattern already has '.json', '.yaml', or '.yml' -> return it if exists else None
      - If extensionless -> try '<pattern>.json' OR '<pattern>.yaml'/'<pattern>.yml'
      - Return None for paths with empty file name (e.g., '//config_remote_config')
    'expect' is a hint: 'json' or 'yaml'
    """
    p = _safe_path_from_pattern(pattern)
    if p is None:
        return None

    # Already has an explicit suffix
    suf = p.suffix.lower()
    if suf in (".json", ".yaml", ".yml"):
        return p if p.exists() else None

    # Extensionless → try candidates
    candidates: List[Path] = []
    try:
        if expect == "json":
            candidates.append(p.with_suffix(".json"))
        elif expect == "yaml":
            candidates.append(p.with_suffix(".yaml"))
            candidates.append(p.with_suffix(".yml"))
        else:
            # Try both families when hint is unknown
            candidates.append(p.with_suffix(".json"))
            candidates.append(p.with_suffix(".yaml"))
            candidates.append(p.with_suffix(".yml"))
    except ValueError:
        # Happens if p has no name (e.g., UNC with empty tail) — treat as missing
        return None

    for c in candidates:
        if c.exists():
            return c
    return None


# -----------------------------------------------------------------------------
# Merging helpers
# -----------------------------------------------------------------------------

def _deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """
    Shallow types: last wins.
    Mappings: deep merge.
    Lists: last wins (controller layering is typically override, not append).
    """
    out = dict(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def merge_json_layers(paths: Iterable[str]) -> Dict[str, Any]:
    """
    Merge JSON layer files in order. Missing/unreadable files are skipped.
    """
    merged: Dict[str, Any] = {}
    for p in paths:
        try:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
            if isinstance(data, dict):
                merged = _deep_merge(merged, data)
        except Exception:
            continue
    return merged


def merge_yaml_layers(paths: Iterable[str]) -> Dict[str, Any]:
    """
    Merge YAML layer files in order (requires PyYAML). Missing/unreadable files are skipped.
    """
    merged: Dict[str, Any] = {}
    if yaml is None:
        return merged
    for p in paths:
        try:
            data = yaml.safe_load(Path(p).read_text(encoding="utf-8")) or {}
            if isinstance(data, dict):
                merged = _deep_merge(merged, data)
        except Exception:
            continue
    return merged
