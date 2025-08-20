"""
Comfy compiler: builds POST /prompt payloads from the in‑memory graph.

Design goals
------------
* Loader-aware: if nodes were created by the robust WorkflowLoader, we honor:
    - node._wm_raw_spec      {"class_type", "inputs", "_meta": {"title": ...}}
    - node._wm_ext_id        external id (e.g., "6", "9", or "n2")
    - node._wm_class_type    class type string (e.g., "CLIPTextEncode")
    - node._wm_title         optional human title

* Non-destructive: we never mutate node._wm_raw_spec; we copy inputs.

* Overlay semantics: we overlay only primitive node.params() values onto the
  raw "inputs" (so existing connection pairs like ["4", 0] are preserved).

* Hygiene:
    - SaveImage always has a safe filename_prefix unless already present.
    - Connections are normalized to ["node_id", OUTPUT_INDEX:int].
      If output index is a known *string* like "IMAGE"/"LATENT", coerce to 0.
    - Known scalar fields are coerced to int/float/str (e.g., seed/steps/cfg).

* Predictable keys:
    - Prefer loader-provided _wm_ext_id ("6", "9"): that keeps server validation
      messages aligned with what you see in the editor JSON.
    - Otherwise fall back to node.get_id() if available; else "n{enumeration}".

Notes
-----
* This compiler remains "thin": it does not invent edges or topology; it trusts
  the loader to populate raw inputs properly. It only sanitizes/overlays.
"""

from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional


# ------------------------- small utilities -------------------------

_PRIMITIVES = (str, int, float, bool, type(None))

def _is_primitive(v: Any) -> bool:
    return isinstance(v, _PRIMITIVES)

def _copy_inputs_keep_connections(raw_inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Shallow copy inputs to avoid mutating loader state; copy 1-level lists/tuples."""
    out: Dict[str, Any] = {}
    for k, v in (raw_inputs or {}).items():
        if isinstance(v, list):
            out[k] = list(v)
        elif isinstance(v, tuple):
            out[k] = list(v)  # unify to list; Comfy accepts list
        else:
            out[k] = v
    return out

def _sanitize_filename_prefix(prefix: str) -> str:
    """
    Keep filename_prefix strictly a safe "name", not a path.
    Remove path separators and illegal filename chars on Windows/macOS/Linux.
    """
    if not isinstance(prefix, str):
        prefix = str(prefix)
    bad = set('\\/:*?"<>|')
    cleaned = "".join(c for c in prefix if c not in bad)
    cleaned = cleaned.strip().strip(".")
    return cleaned or "ComfyUI"

def _normalize_conn(val: Any) -> Any:
    """
    Normalize a single connection value into ["node_id", int_index].
    Accepts:
      - ["6", 0]
      - [6, 0]            -> ["6", 0]
      - ("6", "IMAGE")    -> ["6", 0]
      - ("6", "LATENT")   -> ["6", 0]
    If it doesn't look like a 2-tuple/list, return unchanged.
    """
    if isinstance(val, (list, tuple)) and len(val) == 2:
        nid, out = val[0], val[1]
        # node id as string
        try:
            nid = str(nid)
        except Exception:
            pass
        # output index: allow legacy strings
        if isinstance(out, str):
            out = 0
        try:
            out = int(out)
        except Exception:
            out = 0
        return [nid, out]
    return val

def _normalize_connections(inputs: Dict[str, Any]) -> None:
    """
    Normalize common connection inputs in-place.
    We only touch known connection fields; other keys are left untouched.
    """
    # Most common connection input names for core nodes:
    conn_keys = {
        "model", "positive", "negative", "latent_image",
        "clip", "samples", "vae", "images"
    }

    for name, val in list(inputs.items()):
        if name not in conn_keys:
            continue
        # SaveImage.images is a single connection; some nodes might return it wrapped
        # in a nested list; we accept both but normalize to a single conn list.
        if name == "images":
            if isinstance(val, list) and len(val) == 1 and isinstance(val[0], (list, tuple)):
                inputs[name] = _normalize_conn(val[0])
            else:
                inputs[name] = _normalize_conn(val)
        else:
            inputs[name] = _normalize_conn(val)

def _coerce_known_scalars(class_type: str, inputs: Dict[str, Any]) -> None:
    """
    Coerce known scalar types for popular core nodes so accidental floats/strings
    don't trip validation.
    """
    # minimal type expectations for core nodes you are using in tests
    if class_type == "KSampler":
        # integers
        for k in ("seed", "steps"):
            if k in inputs and inputs[k] is not None:
                try: inputs[k] = int(inputs[k])
                except Exception: pass
        # floats
        for k in ("cfg", "denoise"):
            if k in inputs and inputs[k] is not None:
                try: inputs[k] = float(inputs[k])
                except Exception: pass
        # strings
        for k in ("sampler_name", "scheduler"):
            if k in inputs and inputs[k] is not None:
                inputs[k] = str(inputs[k])

    elif class_type == "EmptyLatentImage":
        for k in ("width", "height", "batch_size"):
            if k in inputs and inputs[k] is not None:
                try: inputs[k] = int(inputs[k])
                except Exception: pass

    elif class_type == "SaveImage":
        if "filename_prefix" in inputs and inputs["filename_prefix"] is not None:
            inputs["filename_prefix"] = _sanitize_filename_prefix(inputs["filename_prefix"])

    elif class_type == "CheckpointLoaderSimple":
        if "ckpt_name" in inputs and inputs["ckpt_name"] is not None:
            inputs["ckpt_name"] = str(inputs["ckpt_name"])

    elif class_type == "CLIPTextEncode":
        if "text" in inputs and inputs["text"] is not None:
            inputs["text"] = str(inputs["text"])

def _resolve_key_for_node(node: Any, index: int) -> str:
    """
    Return the payload key we will use for this node.
    Preference order:
      1) node._wm_ext_id      (keeps keys aligned with editor JSON)
      2) node.get_id()        (if your NodeBase provides it)
      3) f"n{index}"          (deterministic fallback)
    """
    ext = getattr(node, "_wm_ext_id", None)
    if ext:
        return str(ext)

    # best-effort for NodeBase-like objects
    try:
        nid = node.get_id()
        if nid is not None:
            return str(nid)
    except Exception:
        pass

    return f"n{index}"

def _resolve_class_type(node: Any, raw_spec: Optional[Dict[str, Any]]) -> str:
    if isinstance(raw_spec, dict):
        ct = raw_spec.get("class_type")
        if ct: return ct

    ct = getattr(node, "_wm_class_type", None)
    if ct: return ct

    meta = getattr(node, "meta", None)
    if meta is not None:
        ct = getattr(meta, "type", None)
        if ct: return ct

    # final fallback; keeps server error message explicit
    return "Unknown"


class ComfyCompiler:
    def __init__(self,
                 strict: bool = False,
                 default_filename_prefix: str = "ComfyUI",
                 sanitize_filename_prefix: bool = True):
        """
        Args:
            strict: if True, raise ValueError when class_type is 'Unknown'
                    (default False keeps tests/dev flows tolerant).
            default_filename_prefix: used if a SaveImage node lacks one.
            sanitize_filename_prefix: clean illegal path chars from prefix.
        """
        self._strict = strict
        self._default_prefix = default_filename_prefix
        self._sanitize_prefix = sanitize_filename_prefix

    def compile(self, graph, ctx) -> Dict[str, Any]:
        """
        Build /prompt payload from the current graph.
        """
        payload: Dict[str, Any] = {}
        nodes: List[Any] = list(graph.iter_nodes())

        for i, node in enumerate(nodes, start=1):
            # --------- determine payload key ---------
            key = _resolve_key_for_node(node, i)

            # --------- gather raw spec ---------
            raw_spec = getattr(node, "_wm_raw_spec", None)
            if isinstance(raw_spec, dict):
                raw_inputs = raw_spec.get("inputs") or {}
                raw_meta = raw_spec.get("_meta") if isinstance(raw_spec.get("_meta"), dict) else {}
            else:
                raw_inputs = {}
                raw_meta = {}

            class_type = _resolve_class_type(node, raw_spec)
            if self._strict and class_type == "Unknown":
                raise ValueError(f"Cannot compile node {key}: unknown class_type")

            # --------- overlay primitive params, preserve connections ---------
            inputs = _copy_inputs_keep_connections(raw_inputs)
            try:
                params = node.params()
            except Exception:
                params = {}

            for pname, pval in (params or {}).items():
                if _is_primitive(pval):
                    inputs[pname] = pval
                # If pval is connection-shaped (list/tuple), the loader’s raw input wins.

            # --------- normalize connections & coerce scalars ---------
            _normalize_connections(inputs)
            _coerce_known_scalars(class_type, inputs)

            # --------- SaveImage niceties ---------
            if class_type == "SaveImage":
                if "filename_prefix" not in inputs or inputs["filename_prefix"] in (None, ""):
                    inputs["filename_prefix"] = self._default_prefix
                if self._sanitize_prefix and "filename_prefix" in inputs:
                    inputs["filename_prefix"] = _sanitize_filename_prefix(inputs["filename_prefix"])

            # --------- emit ---------
            out = {"class_type": class_type, "inputs": inputs}
            if raw_meta:
                out["_meta"] = raw_meta  # keep human title for downstream tooling
            payload[str(key)] = out

        return payload
