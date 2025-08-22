from __future__ import annotations
from typing import Dict, List, Tuple, Optional, Any

from ...connectors.comfy.rest_client import ComfyRestClient


class SchemaResolver:
    """
    Fetches and caches Comfy's /object_info schema to derive the ordered
    input argument names + types (+ meta) for each node class.
    Works with core and custom nodes without any per-class hardcoding.

    get_arg_specs("KSampler")
      -> [("seed","INT",{"default":0}),("steps","INT",...),("cfg","FLOAT",...), ...]
    """

    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._cache: Optional[Dict[str, Any]] = None

    def _ensure_loaded(self) -> Dict[str, Any]:
        if self._cache is not None:
            return self._cache
        client = ComfyRestClient(self._base, timeout=self._timeout)
        obj = client.get("/object_info")
        nodes = obj.get("nodes", obj)
        if not isinstance(nodes, dict):
            nodes = {}
        self._cache = nodes
        return self._cache

    def get_arg_specs(self, class_type: str) -> List[Tuple[str, Optional[str], Dict[str, Any]]]:
        """
        Returns an ordered list of (name, type_string, meta_dict) for both
        required and optional inputs. We keep the server's original order,
        which aligns with the editor UI widget order for parameters.
        """
        nodes = self._ensure_loaded()
        info = nodes.get(class_type) or {}

        # Different Comfy variants use "input" or "inputs".
        inputs_block = (info.get("input")
                        or info.get("inputs")
                        or info.get("Input")
                        or {})

        required = inputs_block.get("required", {}) or {}
        optional = inputs_block.get("optional", {}) or {}

        def _pairs(d: Dict[str, Any]) -> List[Tuple[str, Optional[str], Dict[str, Any]]]:
            out: List[Tuple[str, Optional[str], Dict[str, Any]]] = []
            for name, spec in d.items():
                ty: Optional[str] = None
                meta: Dict[str, Any] = {}
                if isinstance(spec, (list, tuple)) and spec:
                    first = spec[0]
                    if isinstance(first, str):
                        ty = first.upper()
                    if len(spec) > 1 and isinstance(spec[1], dict):
                        meta = dict(spec[1])
                elif isinstance(spec, dict):
                    # Some builds use {"type":"INT","default":...}
                    if "type" in spec and isinstance(spec["type"], str):
                        ty = spec["type"].upper()
                    meta = dict(spec)
                out.append((name, ty, meta))
            return out

        return _pairs(required) + _pairs(optional)
