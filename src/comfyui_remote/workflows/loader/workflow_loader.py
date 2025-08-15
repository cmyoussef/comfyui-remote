"""Workflow loader (Comfy editor JSON -> in-memory Graph)."""
from __future__ import annotations

import json
from typing import Dict, Any, List

from ..templates.model import WorkflowTemplate
from ...nodes.core.node_core_api import NodeCoreAPI
from ...nodes.base.node_base import NodeBase, NodeMetadata


class _GenericNode(NodeBase):
    """Node for raw JSON import."""
    pass


# Map editor "widgets_values" (by node 'type') into prompt input names.
def _widgets_to_params(type_name: str, w: List[Any]) -> Dict[str, Any]:
    t = (type_name or "").strip()
    try:
        if t == "CheckpointLoaderSimple":
            # [ckpt_name]
            return {"ckpt_name": w[0]} if len(w) >= 1 else {}
        if t == "CLIPTextEncode":
            # [text]
            return {"text": w[0] if len(w) >= 1 else ""}
        if t == "EmptyLatentImage":
            # [width, height, batch]
            return {
                "width": int(w[0]) if len(w) >= 1 else 512,
                "height": int(w[1]) if len(w) >= 2 else 512,
                "batch_size": int(w[2]) if len(w) >= 3 else 1,
            }
        if t == "KSampler":
            # [seed, "randomize", steps, cfg, sampler_name, scheduler, denoise]
            seed = int(w[0]) if len(w) >= 1 and isinstance(w[0], (int, float)) else 0
            return {
                "seed": seed,
                "steps": int(w[2]) if len(w) >= 3 else 20,
                "cfg": float(w[3]) if len(w) >= 4 else 8.0,
                "sampler_name": str(w[4]) if len(w) >= 5 else "euler",
                "scheduler": str(w[5]) if len(w) >= 6 else "normal",
                "denoise": float(w[6]) if len(w) >= 7 else 1.0,
            }
        if t == "SaveImage":
            # [filename_prefix]
            return {"filename_prefix": w[0] if len(w) >= 1 else "ComfyUI"}
        if t == "LoadImage":
            # [image, mode]
            return {"image": w[0] if len(w) >= 1 else ""}
        # Common nodes that carry no widget params:
        if t in ("VAEDecode", "VAEEncode", "ImageScaleToTotalPixels", "MarkdownNote"):
            return {}
    except Exception:
        # Best-effort: ignore malformed widget payloads
        return {}
    return {}


def _build_name_index_maps(spec: Dict[str, Any]) -> Dict[str, Dict[int, str]]:
    """Return index->name maps for inputs/outputs from editor spec."""
    out_idx_to_name: Dict[int, str] = {}
    for out in spec.get("outputs", []) or []:
        # slot_index is the "position" Comfy expects for wiring ("nX", index)
        idx = int(out.get("slot_index", len(out_idx_to_name)))
        out_idx_to_name[idx] = str(out.get("name", str(idx)))

    in_idx_to_name: Dict[int, str] = {}
    for idx, inp in enumerate(spec.get("inputs", []) or []):
        in_idx_to_name[idx] = str(inp.get("name", str(idx)))

    return {"out": out_idx_to_name, "in": in_idx_to_name}


def load_from_json_file(path: str, api: NodeCoreAPI) -> None:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes_spec: List[Dict[str, Any]] = data.get("nodes", []) or []
    links_spec: List[List[Any]] = data.get("links", []) or []

    uiid_to_nodeid: Dict[int, str] = {}

    # 1) Create nodes, transferring widget params and port maps
    for spec in nodes_spec:
        ui_id = spec.get("id")
        type_name = spec.get("type") or spec.get("class_type") or "Unknown"
        meta = NodeMetadata(type=str(type_name), label=str(type_name), category=str(spec.get("properties", {}).get("cnr_id", "")))
        node = _GenericNode(meta)

        # Store editor id and port maps for the compiler
        maps = _build_name_index_maps(spec)
        # name->index map (needed to compute output indices later)
        name_to_idx = {name: idx for idx, name in maps["out"].items()}
        node.set_param("_ui_orig_id", ui_id)
        node.set_param("_ui_out_index_to_name", maps["out"])
        node.set_param("_ui_out_name_to_index", name_to_idx)
        node.set_param("_ui_in_index_to_name", maps["in"])

        # Transfer widget values to actual prompt inputs
        wvals = spec.get("widgets_values") or []
        for k, v in _widgets_to_params(type_name, wvals).items():
            node.set_param(k, v)

        # Keep optional hint for compiler
        node.set_param("class_type", type_name)

        api.graph_ref().add_node(node)
        uiid_to_nodeid[ui_id] = node.get_id()

    # 2) Recreate connections using index->name from both ends
    g = api.graph_ref()
    for l in links_spec:
        # Editor link: [link_id, from_node_id, from_slot_index, to_node_id, to_slot_index, type]
        if not isinstance(l, (list, tuple)) or len(l) < 6:
            continue
        _, src_ui, src_slot, dst_ui, dst_slot, _ = l

        src_node_id = uiid_to_nodeid.get(src_ui)
        dst_node_id = uiid_to_nodeid.get(dst_ui)
        if not (src_node_id and dst_node_id):
            continue

        src_node = g.get_node(src_node_id)
        dst_node = g.get_node(dst_node_id)
        if not (src_node and dst_node):
            continue

        out_name = (src_node.get_param("_ui_out_index_to_name") or {}).get(int(src_slot), str(src_slot))
        in_name = (dst_node.get_param("_ui_in_index_to_name") or {}).get(int(dst_slot), str(dst_slot))
        g.connect(src_node_id, str(out_name), dst_node_id, str(in_name))


def load_from_template(template: WorkflowTemplate, api: NodeCoreAPI) -> None:
    return load_from_json_file(template.path, api)


class WorkflowLoader:
    def __init__(self, api: NodeCoreAPI) -> None:
        self._api = api

    def load_from_json(self, path: str) -> None:
        load_from_json_file(path, self._api)

    def load_from_template(self, tpl: WorkflowTemplate) -> None:
        load_from_template(tpl, self._api)
