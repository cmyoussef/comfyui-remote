"""Workflow loader (robust, schema-agnostic)."""
from __future__ import annotations
import json
from typing import Any, Dict, Optional, Union

from ..templates.model import WorkflowTemplate
from ...nodes.core.node_core_api import NodeCoreAPI
from ...nodes.base.node_base import NodeBase, NodeMetadata


class _GenericNode(NodeBase):
    """Generic node storing raw editor spec + IDs; params can be set later."""
    pass


def _build_link_index(editor: Dict[str, Any]) -> Dict[int, tuple[str, int]]:
    """
    Map link_id -> (src_node_id_str, src_slot_index)
    Editor JSON 'links' are: [id, src_id, src_slot, dst_id, dst_slot, label]
    """
    out: Dict[int, tuple[str, int]] = {}
    for link in editor.get("links", []) or []:
        if not isinstance(link, (list, tuple)) or len(link) < 5:
            continue
        link_id = int(link[0])
        src_node_id = str(link[1])
        src_slot_idx = int(link[2])
        out[link_id] = (src_node_id, src_slot_idx)
    return out


def _extract_title(n: Dict[str, Any]) -> Optional[str]:
    return (
        n.get("title")
        or (n.get("properties") or {}).get("title")
        or (n.get("properties") or {}).get("Node name for S&R")
        or None
    )


def _as_prompt_spec_from_editor_node(n: Dict[str, Any], link_idx: Dict[int, tuple[str, int]]) -> Dict[str, Any]:
    """
    Build a minimal prompt spec for a single editor node:
    {
      "class_type": "...",
      "inputs": { "<input_name>": ["<src_id>", <src_slot>], ... }
      // widgets are NOT mapped here; we keep them raw on the node for the compiler
    }
    """
    class_type = n.get("type", "Unknown")
    # Connections (only ones that are wired)
    inputs: Dict[str, Any] = {}
    for inp in n.get("inputs", []) or []:
        link_id = inp.get("link")
        if link_id is None:
            continue
        src = link_idx.get(int(link_id))
        if not src:
            continue
        src_id, src_slot = src
        inputs[inp.get("name")] = [str(src_id), int(src_slot)]

    return {
        "class_type": class_type,
        "inputs": inputs,
    }


def load_from_json_file(path: str, api: NodeCoreAPI) -> None:
    """
    Supports:
      - Editor JSON: {"nodes":[...], "links":[...], ...}
      - Prompt JSON: {"<id>": {"class_type":..., "inputs": {...}}, ...}
    We store enough on each node for a schema-aware compiler to finish the job later.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # ----- Case A: prompt JSON (already compiled) -----
    if isinstance(data, dict) and "nodes" not in data and "links" not in data:
        for ext_id, spec in data.items():
            if not isinstance(spec, dict):
                continue
            class_type = spec.get("class_type", "Unknown")
            node = _GenericNode(NodeMetadata(type=class_type, label=str(ext_id)))
            node._wm_ext_id = str(ext_id)
            node._wm_class_type = class_type
            # Keep original prompt spec as raw (no mutation)
            node._wm_raw_spec = {
                "class_type": class_type,
                "inputs": dict(spec.get("inputs", {})),
                "_meta": dict(spec.get("_meta", {})) if isinstance(spec.get("_meta"), dict) else {},
            }
            node._wm_title = node._wm_raw_spec.get("_meta", {}).get("title")
            node._wm_widgets = []  # prompt JSON has no widgets
            # Allow params to be overridden at runtime
            api.graph_ref().add_node(node)
        return

    # ----- Case B: editor JSON -----
    nodes = data.get("nodes", []) or []
    link_idx = _build_link_index(data)

    for n in nodes:
        ext_id = str(n.get("id"))
        class_type = n.get("type", "Unknown")
        raw_spec = _as_prompt_spec_from_editor_node(n, link_idx)

        node = _GenericNode(NodeMetadata(type=class_type, label=ext_id))
        node.id = ext_id
        node._wm_class_type = class_type
        node._wm_raw_spec = raw_spec
        node._wm_title = _extract_title(n)
        node._wm_widgets = list(n.get("widgets_values", []) or [])
        api.graph_ref().add_node(node)

    # Note: we do not need to synthesize edges in the graph for compilation since
    # raw_spec.inputs already records the wired connections per node.


def load_from_template(template: WorkflowTemplate, api: NodeCoreAPI) -> None:
    return load_from_json_file(template.path, api)


class WorkflowLoader:
    def __init__(self, api: NodeCoreAPI) -> None:
        self._api = api

    def load_from_json(self, path: str) -> None:
        load_from_json_file(path, self._api)

    def load_from_template(self, tpl: WorkflowTemplate) -> None:
        load_from_template(tpl, self._api)
