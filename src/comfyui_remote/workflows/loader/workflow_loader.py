# src/comfyui_remote/workflows/loader/workflow_loader.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ...nodes.base.node_base import NodeBase, NodeMetadata


def _is_prompt_json(obj: Dict[str, Any]) -> bool:
    """
    Heuristic: prompt JSON is a {id -> {class_type, inputs}} mapping (all string keys).
    Editor JSON has top-level keys like 'nodes', 'links', 'version', etc.
    """
    if not isinstance(obj, dict):
        return False
    if "nodes" in obj or "links" in obj:
        return False
    # prompt json typically: every key is a string and maps to dict with 'class_type'/'inputs'
    sample = next(iter(obj.values()), None)
    return isinstance(sample, dict) and "class_type" in sample and "inputs" in sample


class WorkflowLoader:
    """
    Robust loader that:
      - supports editor JSON (v0.4): rebuild nodes, connections, widgets, titles
      - supports prompt JSON: imports nodes with class_type + inputs directly
      - builds helpful indices: by id, by class_type, by title
    """

    def __init__(self, api) -> None:
        self._api = api
        self._index_by_id: Dict[str, NodeBase] = {}
        self._index_by_type: Dict[str, List[NodeBase]] = {}
        self._index_by_title: Dict[str, List[NodeBase]] = {}

    # ---------- Public API ----------

    def load_from_json(self, path_or_json: str | Path | Dict[str, Any]) -> None:
        if isinstance(path_or_json, (str, Path)):
            data = json.loads(Path(path_or_json).read_text(encoding="utf-8"))
        else:
            data = dict(path_or_json)

        if _is_prompt_json(data):
            self._load_prompt_json(data)
        else:
            self._load_editor_json(data)

    def find_by_id(self, node_id: str) -> Optional[NodeBase]:
        return self._index_by_id.get(str(node_id))

    def find_by_title(self, title: str) -> List[NodeBase]:
        return list(self._index_by_title.get(title.strip().lower(), []))

    def find_by_type(self, ctype: str) -> List[NodeBase]:
        return list(self._index_by_type.get(ctype, []))

    # ---------- Internal: editor JSON ----------

    def _load_editor_json(self, data: Dict[str, Any]) -> None:
        graph = self._api.graph_ref()
        self._index_by_id.clear()
        self._index_by_title.clear()
        self._index_by_type.clear()

        # First pass: create nodes with identity/labels/widgets/connector names/out-slot map
        raw_by_id: Dict[int, Dict[str, Any]] = {}

        for nd in data.get("nodes", []):
            if not isinstance(nd, dict):
                continue

            ext_id = str(nd.get("id"))
            ctype = str(nd.get("type", "Unknown"))
            title = nd.get("title")
            label = nd.get("properties", {}).get("Node name for S&R", ctype)

            nb = NodeBase(NodeMetadata(type=ctype, label=label, title=title), node_id=ext_id)

            # Preserve widgets (positional UI values)
            nb.set_widgets_values(nd.get("widgets_values", []))

            # Names of connector inputs (those that can accept a link)
            connector_names: List[str] = []
            for i in nd.get("inputs", []):
                if isinstance(i, dict) and "name" in i:
                    connector_names.append(str(i["name"]))
            nb.set_connector_inputs(connector_names)

            # Output port name->slot index map (fallback to sequential)
            outs = nd.get("outputs", [])
            out_map: Dict[str, int] = {}
            for idx, o in enumerate(outs):
                if isinstance(o, dict) and "name" in o:
                    out_map[str(o["name"])] = int(o.get("slot_index", idx))
            if out_map:
                nb.set_output_slot_map(out_map)

            graph.add_node(nb)
            self._index_node(nb)
            raw_by_id[int(nd["id"])] = nd

        # Second pass: rebuild connections from "links"
        for lk in data.get("links", []):
            if not isinstance(lk, (list, tuple)) or len(lk) < 5:
                continue
            # schema: [link_id, src_id, src_slot, dst_id, dst_slot, <type>]
            _, src_id, src_slot, dst_id, dst_slot, *_ = lk

            src_node = self._index_by_id.get(str(src_id))
            dst_node = self._index_by_id.get(str(dst_id))
            if not (src_node and dst_node):
                continue

            src_raw = raw_by_id.get(int(src_id), {})
            dst_raw = raw_by_id.get(int(dst_id), {})

            # destination input name from its inputs array slot
            inp_name = None
            dst_inputs = dst_raw.get("inputs", [])
            if isinstance(dst_slot, int) and 0 <= dst_slot < len(dst_inputs):
                try:
                    ent = dst_inputs[dst_slot]
                    if isinstance(ent, dict):
                        inp_name = ent.get("name")
                except Exception:
                    inp_name = None
            if not inp_name:
                # cannot resolve input name — skip
                continue

            # source output slot index — prefer explicit slot_index, else use provided index
            out_index = 0
            src_outs = src_raw.get("outputs", [])
            if isinstance(src_slot, int) and 0 <= src_slot < len(src_outs):
                try:
                    out_index = int(src_outs[src_slot].get("slot_index", src_slot))
                except Exception:
                    out_index = int(src_slot)
            else:
                try:
                    out_index = int(src_slot)
                except Exception:
                    out_index = 0

            dst_node.link_input(inp_name, src_node.get_id(), out_index)

    # ---------- Internal: prompt JSON ----------

    def _load_prompt_json(self, data: Dict[str, Any]) -> None:
        """
        Import a prompt mapping (id -> {class_type, inputs}), preserving keys and connections.
        """
        graph = self._api.graph_ref()
        self._index_by_id.clear()
        self._index_by_title.clear()
        self._index_by_type.clear()

        # First pass: create nodes
        for k, entry in data.items():
            if not isinstance(entry, dict):
                continue
            ctype = str(entry.get("class_type", "Unknown"))
            title = None
            meta = entry.get("_meta", {})
            if isinstance(meta, dict):
                title = meta.get("title")

            nb = NodeBase(NodeMetadata(type=ctype, label=ctype, title=title), node_id=str(k))
            # No widgets in prompt JSON; inputs contain both connections and literals
            # We split connections later when needed; for now, keep only connections in raw_inputs.
            graph.add_node(nb)
            self._index_node(nb)

        # Second pass: assign raw_inputs (connections only) and copy literal defaults into params
        for k, entry in data.items():
            node = self._index_by_id.get(str(k))
            if not node or not isinstance(entry, dict):
                continue
            ins = entry.get("inputs", {}) or {}
            if not isinstance(ins, dict):
                continue

            # Split connections vs literals
            connections: Dict[str, Any] = {}
            literals: Dict[str, Any] = {}

            for name, val in ins.items():
                if isinstance(val, list) and len(val) == 2 and all(isinstance(x, (str, int)) for x in val):
                    # likely a connection [id, slot]
                    src_id, slot = val
                    connections[str(name)] = [str(src_id), int(slot)]
                else:
                    literals[str(name)] = val

            node.set_raw_inputs(connections)
            # Keep literals as runtime overrides; this lets the compiler re-emit them.
            for pname, pval in literals.items():
                node.set_param(pname, pval)

    # ---------- Index maintenance ----------

    def _index_node(self, n: NodeBase) -> None:
        self._index_by_id[n.get_id()] = n
        self._index_by_type.setdefault(n.ctype, []).append(n)
        if n.title:
            self._index_by_title.setdefault(n.title.strip().lower(), []).append(n)
