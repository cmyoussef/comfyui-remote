"""Workflow loader: robust normalization + rich node metadata.

This loader accepts either:
  1) Comfy Editor JSON: {"nodes":[...], "links":[...], ...}
  2) Compiled Prompt JSON: {"6": {"class_type": "...", "inputs": {...}}, ...}

Strategy:
  - If Editor JSON: normalize to a Prompt JSON mapping so we have a single, consistent shape.
  - Create _GenericNode for each prompt entry:
      * node._wm_raw_spec   -> the normalized prompt spec for this node
      * node._wm_ext_id     -> external id (string)
      * node._wm_class_type -> class type (string)
      * node._wm_title      -> title from editor/meta when available
      * node.params()       -> only primitive inputs (exclude connections)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..templates.model import WorkflowTemplate
from ...nodes.core.node_core_api import NodeCoreAPI
from ...nodes.base.node_base import NodeBase, NodeMetadata


# --------------------------
# Helpers: typing + checks
# --------------------------

def _is_primitive(v: Any) -> bool:
    return isinstance(v, (str, int, float, bool)) or v is None


def _is_connection_value(v: Any) -> bool:
    """Comfy connection: ["other_id", int_index] or [int_id, int_index]."""
    if isinstance(v, list) and len(v) == 2:
        a, b = v
        if isinstance(b, int) and (isinstance(a, (str, int))):
            return True
    return False


def _as_str_id(x: Any) -> str:
    """Normalize external id to string (accepts numeric)."""
    return str(x)


# --------------------------
# Editor → Prompt normalize
# --------------------------

def _derive_editor_value_params(node: Dict[str, Any]) -> Dict[str, Any]:
    """
    Derive "value" inputs from Editor JSON widgets_values (not connections).
    This is heuristic, keyed by common Comfy core nodes.
    """
    t = node.get("type") or ""
    w = node.get("widgets_values") or []
    params: Dict[str, Any] = {}

    # Common node patterns
    if t == "CLIPTextEncode":
        # widgets: [text]
        if len(w) >= 1:
            params["text"] = w[0]

    elif t == "EmptyLatentImage":
        # widgets: [width, height, batch_size]
        if len(w) >= 1: params["width"] = w[0]
        if len(w) >= 2: params["height"] = w[1]
        if len(w) >= 3: params["batch_size"] = w[2]

    elif t == "KSampler":
        # widgets: [seed, <seed_mode>, steps, cfg, sampler_name, scheduler, denoise]
        # ignore the second 'randomize' string; not part of server input
        if len(w) >= 1: params["seed"] = w[0]
        if len(w) >= 3: params["steps"] = w[2]
        if len(w) >= 4: params["cfg"] = w[3]
        if len(w) >= 5: params["sampler_name"] = w[4]
        if len(w) >= 6: params["scheduler"] = w[5]
        if len(w) >= 7: params["denoise"] = w[6]

    elif t == "SaveImage":
        # widgets: [filename_prefix]
        if len(w) >= 1:
            params["filename_prefix"] = w[0]

    elif t == "CheckpointLoaderSimple":
        # widgets: [ckpt_name]
        if len(w) >= 1:
            params["ckpt_name"] = w[0]

    elif t == "LoadImage":
        # widgets: [image_name, mode?]
        if len(w) >= 1:
            params["image"] = w[0]

    # Extend with more node heuristics as needed

    return params


def _build_input_name_index(editor_nodes: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    For each node, map node_id -> list of its input 'name's ordered by index,
    so we can resolve link dest_slot_index -> input name.
    """
    idx: Dict[str, List[str]] = {}
    for n in editor_nodes:
        nid = _as_str_id(n.get("id"))
        names: List[str] = []
        for inp in n.get("inputs", []) or []:
            # Some editor JSONs don't have names; guard accordingly
            names.append(inp.get("name") or "")
        idx[nid] = names
    return idx


def _normalize_editor_to_prompt(editor: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Turn Comfy Editor JSON into a Prompt JSON mapping:
      { "6": { "class_type": "...", "inputs": {...}, "_meta": {"title": "..."} }, ... }
    """
    nodes: List[Dict[str, Any]] = editor.get("nodes") or []
    links: List[List[Any]] = editor.get("links") or []

    # Build direct node lookup by id and input name index
    by_id: Dict[str, Dict[str, Any]] = { _as_str_id(n.get("id")): n for n in nodes }
    input_names = _build_input_name_index(nodes)

    # Start with value inputs derived from widgets_values
    prompt: Dict[str, Dict[str, Any]] = {}
    for n in nodes:
        ext_id = _as_str_id(n.get("id"))
        class_type = n.get("type") or ""
        title = n.get("title")  # may be None

        spec_inputs: Dict[str, Any] = _derive_editor_value_params(n)

        # include _meta.title
        prompt[ext_id] = {
            "class_type": class_type,
            "inputs": spec_inputs,
            "_meta": {"title": title} if title is not None else {}
        }

    # Wire connections from links array
    # Link format (LiteGraph): [link_id, origin_node_id, origin_slot_idx, dest_node_id, dest_slot_idx, "TYPE"]
    for link in links:
        if not (isinstance(link, list) and len(link) >= 5):
            continue
        _link_id, origin_id, origin_slot, dest_id, dest_slot = link[:5]
        dest_id_s = _as_str_id(dest_id)
        origin_id_s = _as_str_id(origin_id)

        dest_names = input_names.get(dest_id_s) or []
        # Map slot index to an input name if possible
        in_name: Optional[str] = None
        if isinstance(dest_slot, int) and 0 <= dest_slot < len(dest_names):
            maybe_name = dest_names[dest_slot] or None
            in_name = maybe_name

        # If name missing, we can't add it. Skip gracefully.
        if not in_name:
            continue

        spec = prompt.get(dest_id_s)
        if not spec:
            continue

        # Connection is ["origin_id", origin_slot]
        spec["inputs"][in_name] = [origin_id_s, int(origin_slot) if isinstance(origin_slot, int) else 0]

    return prompt


# --------------------------
# Generic node implementation
# --------------------------

class _GenericNode(NodeBase):
    """
    Node that carries the *raw normalized prompt spec* and exposes only value inputs as params.
    Connections (["id", idx]) are intentionally not included in params.
    """
    def __init__(self, meta: NodeMetadata, raw_prompt_spec: Dict[str, Any]):
        # Build kwargs of "value" inputs only
        params: Dict[str, Any] = {}
        ins = (raw_prompt_spec.get("inputs") or {}) if isinstance(raw_prompt_spec, dict) else {}
        for k, v in ins.items():
            if _is_primitive(v):
                params[k] = v

        super().__init__(meta, **params)

        # Attach rich metadata for later compilation/indexing
        self._wm_raw_spec = raw_prompt_spec
        self._wm_ext_id = meta.label or ""
        self._wm_class_type = meta.type or ""
        # Try meta title from raw_prompt_spec
        m = raw_prompt_spec.get("_meta") if isinstance(raw_prompt_spec, dict) else None
        self._wm_title = (m or {}).get("title") if isinstance(m, dict) else None


# --------------------------
# Loader public API
# --------------------------

def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _to_prompt_map(data: Any) -> Dict[str, Dict[str, Any]]:
    """
    Ensure we return a normalized Prompt JSON mapping:
      { "id": {"class_type": str, "inputs": dict, "_meta": {...}} }
    """
    # Editor JSON
    if isinstance(data, dict) and "nodes" in data and isinstance(data["nodes"], list):
        return _normalize_editor_to_prompt(data)

    # Already Prompt JSON
    if isinstance(data, dict):
        # Add safe defaults for _meta/title if missing
        out: Dict[str, Dict[str, Any]] = {}
        for k, spec in data.items():
            if not isinstance(spec, dict):
                continue
            ctype = spec.get("class_type") or ""
            ins = spec.get("inputs") or {}
            meta = spec.get("_meta") or {}
            if not isinstance(meta, dict):
                meta = {}
            out[_as_str_id(k)] = {"class_type": ctype, "inputs": ins, "_meta": meta}
        return out

    # Unknown shape
    raise ValueError("Unsupported workflow JSON format")


def load_from_json_file(path: str, api: NodeCoreAPI) -> None:
    """
    Load a workflow JSON (Editor or Prompt), normalize to Prompt JSON,
    create nodes with full metadata, and add them to the graph in file order.
    """
    data = _load_json(path)
    prompt_map = _to_prompt_map(data)

    # Insert nodes in the same file order we got (dict in modern Python preserves insertion order)
    for ext_id, spec in prompt_map.items():
        class_type = spec.get("class_type") or "Unknown"
        meta = NodeMetadata(type=class_type, label=ext_id)
        node = _GenericNode(meta, raw_prompt_spec=spec)
        api.graph_ref().add_node(node)


def load_from_template(template: WorkflowTemplate, api: NodeCoreAPI) -> None:
    return load_from_json_file(template.path, api)


class WorkflowLoader:
    def __init__(self, api: NodeCoreAPI) -> None:
        self._api = api

    def load_from_json(self, path: str) -> None:
        load_from_json_file(path, self._api)

    def load_from_template(self, tpl: WorkflowTemplate) -> None:
        load_from_template(tpl, self._api)
