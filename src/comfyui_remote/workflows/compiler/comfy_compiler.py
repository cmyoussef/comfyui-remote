"""Graph -> ComfyUI prompt compiler (editor graph aware)."""
from __future__ import annotations

from typing import Dict, Any


class ComfyCompiler:
    """Compile our in-memory Graph into a Comfy /prompt payload."""

    _INTERNAL_KEYS = ("_ui_", "_prompt_key", "class_type")

    def _is_internal(self, k: str) -> bool:
        return any(k.startswith(pfx) for pfx in self._INTERNAL_KEYS)

    def _node_key(self, node, idx: int) -> str:
        pk = node.get_param("_prompt_key")
        if pk:
            return str(pk)
        ui_id = node.get_param("_ui_orig_id")
        if ui_id is not None:
            return f"n{ui_id}"
        return f"n{idx}"

    def _base_inputs_from_params(self, node) -> Dict[str, Any]:
        d = {}
        for k, v in (node.params() or {}).items():
            if isinstance(k, str) and not self._is_internal(k):
                d[k] = v
        return d

    def _out_index_for(self, node, out_port_name: str) -> int:
        m = node.get_param("_ui_out_name_to_index") or {}
        return int(m.get(out_port_name, 0))

    def compile(self, graph, ctx=None) -> Dict[str, Any]:
        nodes = list(graph.iter_nodes())
        key_by_id: Dict[str, str] = {}
        compiled: Dict[str, Dict[str, Any]] = {}

        # Assign stable prompt keys
        for i, node in enumerate(nodes, start=1):
            key = self._node_key(node, i)
            while key in key_by_id.values():
                key = f"{key}_{i}"
            key_by_id[node.get_id()] = key

            class_type = getattr(getattr(node, "metadata", None), "type", None) or node.get_param("class_type") or "Unknown"
            compiled[key] = {
                "class_type": str(class_type),
                "inputs": self._base_inputs_from_params(node),
            }

        # Wire connections
        for c in (graph.iter_connections() or []):
            src_id = getattr(c, "out_node_id", None)
            dst_id = getattr(c, "in_node_id", None)
            src_port = getattr(c, "out_port", None)
            dst_port = getattr(c, "in_port", None)
            if not (src_id and dst_id and src_port and dst_port):
                continue

            src_node = graph.get_node(src_id)
            if not src_node:
                continue
            src_key = key_by_id[src_id]
            dst_key = key_by_id[dst_id]
            out_idx = self._out_index_for(src_node, str(src_port))
            compiled[dst_key]["inputs"][str(dst_port)] = [src_key, out_idx]

        return compiled
