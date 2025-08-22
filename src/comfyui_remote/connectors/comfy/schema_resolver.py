# src/comfyui_remote/connectors/comfy/schema_resolver.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .rest_client import ComfyRestClient


_PRIMITIVES = {"INT", "FLOAT", "STRING", "BOOL", "BOOLEAN"}


def is_primitive_tag(tag: Optional[str]) -> bool:
    if not tag:
        # None => often “choice” widgets which are still strings at runtime
        return True
    tag = tag.upper()
    if tag == "BOOLEAN":
        return True
    return tag in _PRIMITIVES


def _normalize_nodes_dict(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Comfy variants put node specs under 'nodes' or at the top level."""
    if not isinstance(obj, Dict):
        return {}
    nodes = obj.get("nodes", obj)
    return nodes if isinstance(nodes, Dict) else {}


def _extract_input_buckets(info: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Returns (required, optional) dicts from a node class entry in /object_info.
    Compatible with variants that use 'input' or 'inputs'.
    """
    inputs_block = (
        info.get("input")
        or info.get("inputs")
        or info.get("Input")
        or {}
    )
    if not isinstance(inputs_block, Dict):
        return {}, {}
    required = inputs_block.get("required", {}) or {}
    optional = inputs_block.get("optional", {}) or {}
    return (required if isinstance(required, Dict) else {}), (optional if isinstance(optional, Dict) else {})


def _type_meta_from_spec(spec: Any) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Convert a per-input spec into (type_tag, meta_dict).
    Examples we see in the wild:
    - ["INT", {"default": 20, "min": 1, "max": 10000}]
    - {"type": "INT", "default": ...}
    - ["MODEL"]                         (connectors)
    - [["choice1","choice2"], {...}]    (choices as list; no explicit string tag)
    """
    if isinstance(spec, (list, tuple)) and spec:
        first = spec[0]
        ty = str(first).upper() if isinstance(first, str) else None
        meta = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
        # choices may be provided as a list in 'first'; leave ty=None => treat as STRING
        return ty, dict(meta)
    if isinstance(spec, dict):
        ty = spec.get("type")
        if isinstance(ty, str):
            ty = ty.upper()
        return ty, dict(spec)
    return None, {}


class SchemaResolver:
    """
    Fetches and caches Comfy's /object_info schema to derive the ordered input
    argument names + types (+ meta) for each node class.

    get_arg_specs("KSampler")
      -> [("seed","INT",{}),("steps","INT",{}),("cfg","FLOAT",{}), ...]
    """

    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._nodes: Optional[Dict[str, Any]] = None

    def _ensure_loaded(self) -> Dict[str, Any]:
        if self._nodes is not None:
            return self._nodes
        cli = ComfyRestClient(self._base, timeout=self._timeout)
        obj = cli.get("/object_info")
        self._nodes = _normalize_nodes_dict(obj if isinstance(obj, dict) else {})
        return self._nodes

    def _find_class_info(self, class_type: str) -> Dict[str, Any]:
        """
        Tolerant lookup by exact, case-insensitive, or normalized key.
        Falls back to matching 'name'/'class_name' field when present.
        """
        nodes = self._ensure_loaded()
        if not class_type or not nodes:
            return {}
        # 1) exact
        hit = nodes.get(class_type)
        if isinstance(hit, dict):
            return hit
        # 2) case-insensitive
        lower = class_type.lower()
        for k, v in nodes.items():
            if isinstance(k, str) and k.lower() == lower and isinstance(v, dict):
                return v
        # 3) normalized
        def _norm(s: str) -> str:
            return "".join(ch for ch in s.lower() if ch.isalnum())
        norm = _norm(class_type)
        for k, v in nodes.items():
            if isinstance(k, str) and _norm(k) == norm and isinstance(v, dict):
                return v
        # 4) check names/class_name fields
        for _, v in nodes.items():
            if isinstance(v, dict):
                nm = v.get("name") or v.get("class_name")
                if isinstance(nm, str):
                    if nm == class_type or nm.lower() == lower or _norm(nm) == norm:
                        return v
        return {}

    def get_arg_specs(self, class_type: str) -> List[Tuple[str, Optional[str], Dict[str, Any]]]:
        """
        Ordered list of (name, type_tag|None, meta) for required + optional inputs.
        We preserve the server order; that aligns with the editor widget order.
        """
        info = self._find_class_info(class_type)
        req, opt = _extract_input_buckets(info)

        def _pairs(d: Dict[str, Any]) -> List[Tuple[str, Optional[str], Dict[str, Any]]]:
            out: List[Tuple[str, Optional[str], Dict[str, Any]]] = []
            for name, spec in d.items():
                ty, meta = _type_meta_from_spec(spec)
                # Normalize 'BOOLEAN' to 'BOOL'
                if ty and ty.upper() == "BOOLEAN":
                    ty = "BOOL"
                out.append((name, ty, meta))
            return out

        # Prefer input_order if present
        order = info.get("input_order")
        if isinstance(order, list) and order:
            # Build a map and then order it
            joined = {**req, **opt}
            ordered: List[Tuple[str, Optional[str], Dict[str, Any]]] = []
            for nm in order:
                if isinstance(nm, str) and nm in joined:
                    ty, meta = _type_meta_from_spec(joined[nm])
                    if ty and ty.upper() == "BOOLEAN":
                        ty = "BOOL"
                    ordered.append((nm, ty, meta))
            # include any leftovers
            seen = {nm for nm, _, _ in ordered}
            for nm, spec in joined.items():
                if nm not in seen:
                    ty, meta = _type_meta_from_spec(spec)
                    if ty and ty.upper() == "BOOLEAN":
                        ty = "BOOL"
                    ordered.append((nm, ty, meta))
            return ordered

        # Default: required then optional in dict order
        return _pairs(req) + _pairs(opt)


class SchemaResolverRegistry:
    """
    Small registry to reuse a resolver per base_url.
    """
    _cache: Dict[str, SchemaResolver] = {}

    @classmethod
    def get(cls, base_url: str, timeout: float = 5.0) -> SchemaResolver:
        key = base_url.rstrip("/")
        res = cls._cache.get(key)
        if res is None:
            res = SchemaResolver(key, timeout=timeout)
            cls._cache[key] = res
        return res
