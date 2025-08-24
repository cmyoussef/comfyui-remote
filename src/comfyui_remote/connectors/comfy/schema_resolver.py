# src/comfyui_remote/connectors/comfy/schema_resolver.py
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .rest_client import ComfyRestClient

_PRIMITIVES = {"INT", "FLOAT", "STRING", "BOOL", "BOOLEAN"}


def is_primitive_tag(tag: Optional[str]) -> bool:
    if not tag:
        return True
    tag = tag.upper()
    if tag == "BOOLEAN":
        return True
    return tag in _PRIMITIVES


def _normalize_nodes_dict(obj: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(obj, Dict):
        return {}
    nodes = obj.get("nodes", obj)
    return nodes if isinstance(nodes, Dict) else {}


def _extract_input_buckets(info: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    inputs_block = info.get("input") or info.get("inputs") or info.get("Input") or {}
    if not isinstance(inputs_block, Dict):
        return {}, {}
    required = inputs_block.get("required", {}) or {}
    optional = inputs_block.get("optional", {}) or {}
    return (required if isinstance(required, Dict) else {}), (optional if isinstance(optional, Dict) else {})


def _type_meta_from_spec(spec: Any) -> Tuple[Optional[str], Dict[str, Any]]:
    if isinstance(spec, (list, tuple)) and spec:
        first = spec[0]
        ty = str(first).upper() if isinstance(first, str) else None
        meta = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
        return ty, dict(meta)
    if isinstance(spec, dict):
        ty = spec.get("type")
        if isinstance(ty, str):
            ty = ty.upper()
        return ty, dict(spec)
    return None, {}


class SchemaResolver:
    """HTTP/INLINE/FILE schema resolver; caches normalized node specs."""

    def __init__(self, base_url: str = "", timeout: float = 5.0, object_info: Optional[Dict[str, Any]] = None) -> None:
        self._base = base_url.rstrip("/") if base_url else ""
        self._timeout = timeout
        self._nodes: Optional[Dict[str, Any]] = None
        if isinstance(object_info, dict) and object_info:
            self._nodes = _normalize_nodes_dict(object_info)

    @classmethod
    def from_object_info(cls, obj: Dict[str, Any], timeout: float = 5.0) -> "SchemaResolver":
        return cls(base_url="", timeout=timeout, object_info=obj)

    def _ensure_loaded(self) -> Dict[str, Any]:
        if self._nodes is not None:
            return self._nodes
        if not self._base:
            self._nodes = {}
            return self._nodes
        cli = ComfyRestClient(self._base, timeout=self._timeout)
        obj = cli.get("/object_info")
        self._nodes = _normalize_nodes_dict(obj if isinstance(obj, dict) else {})
        return self._nodes

    def _find_class_info(self, class_type: str) -> Dict[str, Any]:
        nodes = self._ensure_loaded()
        if not class_type or not nodes:
            return {}
        hit = nodes.get(class_type)
        if isinstance(hit, dict):
            return hit
        lower = class_type.lower()

        def _norm(s: str) -> str:
            return "".join(ch for ch in s.lower() if ch.isalnum())

        norm = _norm(class_type)

        for k, v in nodes.items():
            if isinstance(k, str) and k.lower() == lower and isinstance(v, dict):
                return v
        for k, v in nodes.items():
            if isinstance(k, str) and _norm(k) == norm and isinstance(v, dict):
                return v
        for _, v in nodes.items():
            if isinstance(v, dict):
                nm = v.get("name") or v.get("class_name")
                if isinstance(nm, str):
                    if nm == class_type or nm.lower() == lower or _norm(nm) == norm:
                        return v
        return {}

    def get_arg_specs(self, class_type: str) -> List[Tuple[str, Optional[str], Dict[str, Any]]]:
        info = self._find_class_info(class_type)
        req, opt = _extract_input_buckets(info)

        def _pairs(d: Dict[str, Any]) -> List[Tuple[str, Optional[str], Dict[str, Any]]]:
            out: List[Tuple[str, Optional[str], Dict[str, Any]]] = []
            for name, spec in d.items():
                ty, meta = _type_meta_from_spec(spec)
                if ty and ty.upper() == "BOOLEAN":
                    ty = "BOOL"
                out.append((name, ty, meta))
            return out

        order = info.get("input_order")
        if isinstance(order, list) and order:
            joined = {**req, **opt}
            ordered: List[Tuple[str, Optional[str], Dict[str, Any]]] = []
            for nm in order:
                if isinstance(nm, str) and nm in joined:
                    ty, meta = _type_meta_from_spec(joined[nm])
                    if ty and ty.upper() == "BOOLEAN":
                        ty = "BOOL"
                    ordered.append((nm, ty, meta))
            seen = {nm for nm, _, _ in ordered}
            for nm, spec in joined.items():
                if nm not in seen:
                    ty, meta = _type_meta_from_spec(spec)
                    if ty and ty.upper() == "BOOLEAN":
                        ty = "BOOL"
                    ordered.append((nm, ty, meta))
            return ordered

        return _pairs(req) + _pairs(opt)


class SchemaResolverRegistry:
    """
    Resolver registry + selection logic.
    Keys:
      - "http(s)://host:port"      -> HTTP resolver
      - "/path/to/schema.json"     -> FILE resolver
      - "file:///path/schema.json" -> FILE resolver
      - "inline:<token>"           -> INLINE resolver (pre-registered)

    Added:
      - ensure(...): choose a resolver by env/arg and cache it
      - ephemeral fetch (start Comfy, GET /object_info, stop), cached in memory
        and optionally to disk (COMFY_SCHEMA_CACHE or ~/.comfyui-remote/schema.object_info.json)
    """
    _cache: Dict[str, SchemaResolver] = {}
    _cache_lock = threading.Lock()

    @classmethod
    def register_inline(cls, key: str, obj: Dict[str, Any], timeout: float = 5.0) -> str:
        rid = f"inline:{key}"
        cls._cache[rid] = SchemaResolver.from_object_info(obj, timeout=timeout)
        return rid

    @classmethod
    def register_file(cls, path: str, timeout: float = 5.0) -> str:
        p = Path(path)
        rid = f"file:{str(p.resolve())}"
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            obj = {}
        cls._cache[rid] = SchemaResolver.from_object_info(obj, timeout=timeout)
        return rid

    @classmethod
    def get(cls, base_or_key: str, timeout: float = 5.0) -> SchemaResolver:
        key = (base_or_key or "").strip()
        if not key:
            raise ValueError("SchemaResolverRegistry.get: empty key")

        if key.startswith("inline:") or key.startswith("file:"):
            res = cls._cache.get(key)
            if res is None and key.startswith("file:"):
                # lazy load file key if not present
                path = key[len("file:"):]
                return cls.get(path, timeout=timeout)
            if res is None:
                raise KeyError(f"No resolver registered for key {key!r}")
            return res

        if key.startswith("file://") or key.lower().endswith(".json"):
            path = key[7:] if key.startswith("file://") else key
            p = Path(path)
            rid = f"file:{str(p.resolve())}"
            res = cls._cache.get(rid)
            if res is None:
                try:
                    obj = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    obj = {}
                res = SchemaResolver.from_object_info(obj, timeout=timeout)
                cls._cache[rid] = res
            return res

        # HTTP default
        res = cls._cache.get(key)
        if res is None:
            res = SchemaResolver(key, timeout=timeout)
            cls._cache[key] = res
        return res

    # ------------ New: selection + ephemeral + disk cache ------------
    @classmethod
    def ensure(cls, base_url: Optional[str] = None, timeout: float = 5.0) -> str:
        """
        Return a resolver key (http URL | file:<abs> | inline:<token>) and
        populate the registry cache as needed.

        Priority:
          1) COMFY_SCHEMA_JSON           (file)
          2) base_url arg / COMFY_REMOTE_URL  (http)
          3) COMFY_SCHEMA_CACHE file if exists (file)
          4) Ephemeral fetch (if COMFYUI_HOME set and not disabled), cached to:
             - registry as inline:ephemeral
             - optional disk COMFY_SCHEMA_CACHE (or ~/.comfyui-remote/schema.object_info.json)
        """
        # 1) explicit offline schema file
        sp = (os.getenv("COMFY_SCHEMA_JSON") or "").strip()
        if sp and Path(sp).is_file():
            return cls.register_file(sp, timeout=timeout)

        # 2) remote URL
        base = (base_url or os.getenv("COMFY_REMOTE_URL") or "").strip()
        if base:
            # warm cache but return URL key as-is so compiler uses HTTP
            try:
                cls.get(base, timeout=timeout)
            except Exception:
                pass
            return base

        # 3) on-disk cache if present
        cache_path = (os.getenv("COMFY_SCHEMA_CACHE") or
                      str(Path.home() / ".comfyui-remote" / "schema.object_info.json"))
        if Path(cache_path).is_file():
            return cls.register_file(cache_path, timeout=timeout)

        # 4) ephemeral (unless disabled)
        if (os.getenv("COMFYUI_HOME") or "") and str(os.getenv("COMFY_SCHEMA_NO_EPHEMERAL", "")).lower() not in ("1","true","yes","on"):
            ep_key = "inline:ephemeral"
            with cls._cache_lock:
                if ep_key in cls._cache:
                    return ep_key
                # fetch from a temporary Comfy instance
                obj = cls._fetch_object_info_ephemeral(timeout=max(timeout, 5.0))
                if obj:
                    # write best-effort cache to disk
                    try:
                        p = Path(cache_path)
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_text(json.dumps(obj, indent=2), encoding="utf-8")
                    except Exception:
                        pass
                    return cls.register_inline("ephemeral", obj, timeout=timeout)

        raise RuntimeError("SchemaResolverRegistry.ensure: could not determine a schema source. "
                           "Provide COMFY_SCHEMA_JSON or COMFY_REMOTE_URL, or set COMFYUI_HOME for ephemeral.")

    @classmethod
    def _fetch_object_info_ephemeral(cls, timeout: float = 10.0) -> Dict[str, Any]:
        """
        Start a local Comfy server, fetch /object_info, stop it. Best-effort.
        """
        # Import locally to avoid module import cycles at import-time
        from .server_manager import ComfyServerManager
        mgr = ComfyServerManager()
        h = mgr.start({})
        try:
            base = f"http://127.0.0.1:{h.port}"
            obj = ComfyRestClient(base, timeout=timeout).get("/object_info") or {}
            return obj if isinstance(obj, dict) else {}
        finally:
            try:
                mgr.stop()
            except Exception:
                pass
