# src/comfyui_remote/nodes/base/node_base.py
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class NodeMetadata:
    """Lightweight metadata carried with a node."""
    type: str
    label: str = ""
    title: Optional[str] = None


class NodeBase:
    """
    Canonical node representation used across loader/graph/compiler.

    Key design points:
    - `id`:     external, stable identifier suitable for prompt keys (e.g., editor "id" as string).
    - `uid`:    internal unique id (uuid4 hex) used if you ever need a non-colliding handle.
    - `ctype`:  class type (e.g., "KSampler", "CLIPTextEncode") — always available.
    - `title`:  human-friendly label if present (e.g., editor JSON "title").
    - `params`: explicit runtime overrides ONLY; loader does not pre-populate this.
    - `raw_inputs`: "connection" inputs (e.g., {"images": ["8", 0]}). Built by loader/graph.connect().
    - `widgets_values`: UI positional values kept verbatim; compiler may map them to named inputs using /object_info.
    - `connector_inputs`: names of connector ports as seen in editor JSON (used to exclude them from widget mapping).
    - `out_slot_map`: mapping from UI output port name -> slot index (used when connecting programmatically).
    """

    def __init__(self, meta: NodeMetadata, node_id: Optional[str] = None) -> None:
        self.meta = meta
        self._uid: str = uuid.uuid4().hex
        self._id: Optional[str] = str(node_id) if node_id is not None else None

        self._ctype: str = meta.type or "Unknown"
        self._title: Optional[str] = meta.title or (meta.label or None)

        # Explicit runtime overrides ONLY
        self._params: Dict[str, Any] = {}

        # Connections set by loader/graph.connect()
        self._raw_inputs: Dict[str, Any] = {}

        # UI-related fields used by the compiler
        self._widgets_values: List[Any] = []
        self._connector_inputs: List[str] = []
        self._out_slot_map: Dict[str, int] = {}

    # ---------- Identity ----------

    @property
    def uid(self) -> str:
        """Internal unique id (never used in the prompt mapping)."""
        return self._uid

    @property
    def id(self) -> str:
        """
        External, stable identifier used as the key in /prompt payload.
        - If not explicitly set, falls back to any legacy _wm_ext_id
          and then to uid (to avoid None).
        """
        if self._id:
            return self._id
        # Back-compat shim: allow old _wm_ext_id to define the id
        wm_ext = getattr(self, "_wm_ext_id", None)
        if wm_ext:
            self._id = str(wm_ext)
            return self._id
        self._id = self._uid
        return self._id

    def set_id(self, node_id: str) -> None:
        self._id = str(node_id)

    def get_id(self) -> str:
        """Compatibility method — returns the external id used in prompt keys."""
        return self.id

    # ---------- Classification & labels ----------

    @property
    def ctype(self) -> str:
        """Node class type (e.g., 'KSampler', 'CLIPTextEncode')."""
        if self._ctype and isinstance(self._ctype, str):
            return self._ctype
        # Back-compat shim
        wm_ct = getattr(self, "_wm_class_type", None)
        if wm_ct:
            return str(wm_ct)
        t = getattr(self.meta, "type", None)
        return str(t or "Unknown")

    @ctype.setter
    def ctype(self, value: str) -> None:
        self._ctype = str(value)

    # Friendly alias to make code ergonomic (n.type == "KSampler")
    @property
    def type(self) -> str:
        return self.ctype

    @property
    def title(self) -> Optional[str]:
        if self._title:
            return self._title
        # Back-compat shim from legacy raw spec
        wm_raw = getattr(self, "_wm_raw_spec", None)
        if isinstance(wm_raw, dict):
            meta = wm_raw.get("_meta", {})
            if isinstance(meta, dict):
                t = meta.get("title")
                if t:
                    return str(t)
        return None

    def set_title(self, title: Optional[str]) -> None:
        self._title = str(title) if title else None

    # ---------- Params (runtime overrides only) ----------

    def params(self) -> Dict[str, Any]:
        """Return explicit overrides only (does not include loader/UI defaults)."""
        return self._params

    def has_param(self, name: str) -> bool:
        return name in self._params

    def set_param(self, name: str, value: Any) -> None:
        """
        Set a runtime override. Special cases handled:
        - class_type / type: updates ctype, not stored in params.
        - title: sets human-friendly title.
        - _ui_out_name_to_index: injects UI output slot map used for connect().
        """
        if name in ("class_type", "type"):
            self.ctype = str(value)
            return
        if name == "title":
            self.set_title(value)
            return
        if name == "_ui_out_name_to_index":
            if isinstance(value, dict):
                # Ensure int indices
                self._out_slot_map = {str(k): int(v) for k, v in value.items()}
            return
        self._params[name] = value

    # ---------- Raw inputs / connections ----------

    @property
    def raw_inputs(self) -> Dict[str, Any]:
        """Connections-only inputs (dest input name -> [source_id, output_slot_index])."""
        if self._raw_inputs is None:
            self._raw_inputs = {}
        return self._raw_inputs

    def set_raw_inputs(self, mapping: Dict[str, Any]) -> None:
        self._raw_inputs = dict(mapping or {})

    def link_input(self, input_name: str, src_node_id: str, src_output_index: int) -> None:
        """Record a connection: dst[input_name] = [src_id, src_output_index]."""
        self.raw_inputs[str(input_name)] = [str(src_node_id), int(src_output_index)]

    # ---------- UI helpers used by compiler or graph.connect ----------

    @property
    def widgets_values(self) -> List[Any]:
        return self._widgets_values

    def set_widgets_values(self, values: List[Any]) -> None:
        self._widgets_values = list(values or [])

    @property
    def connector_inputs(self) -> List[str]:
        """Names of connector ports on the node (from editor JSON)."""
        return self._connector_inputs

    def set_connector_inputs(self, names: List[str]) -> None:
        self._connector_inputs = [str(n) for n in (names or [])]

    def set_output_slot_map(self, mapping: Dict[str, int]) -> None:
        """Map UI output port names to slot indices (used when connecting by port name)."""
        self._out_slot_map = {str(k): int(v) for k, v in (mapping or {}).items()}

    def get_output_slot_index(self, output_name: str, default: int = 0) -> int:
        if self._out_slot_map and output_name in self._out_slot_map:
            return int(self._out_slot_map[output_name])
        return int(default)

    # ---------- Back-compat shims for legacy code that used _wm_* ----------

    @property
    def _wm_ext_id(self) -> str:
        return self.id

    @property
    def _wm_class_type(self) -> str:
        return self.ctype

    @property
    def _wm_raw_spec(self) -> Dict[str, Any]:
        """Return a normalized spec for old code expecting _wm_raw_spec."""
        spec: Dict[str, Any] = {
            "class_type": self.ctype,
            "inputs": dict(self.raw_inputs),
        }
        if self.title:
            spec["_meta"] = {"title": self.title}
        return spec

    def __repr__(self) -> str:
        return f"<NodeBase id={self.id!r} ctype={self.ctype!r} title={self.title!r}>"
