"""
Schema‑driven Comfy compiler.

We:
  • Preserve all wired connections from the editor JSON.
  • Pull the node input schema from /object_info (names, types, choices).
  • Map widgets_values to the first missing input whose schema looks compatible:
      - Primitive types: INT / FLOAT / STRING / BOOLEAN (with safe coercions).
      - "Name-like" types (e.g., SAMPLER_NAME, SCHEDULER_NAME, CKPT_NAME):
        treat as STRING (use choices/default hints when present).
  • Skip UI-only widgets (like the "randomize" toggle) because they won't match
    the expected type sequence.

No per-class hardcoding. Works with custom nodes.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple, Set

from .schema_resolver import SchemaResolver


# ---- helpers ----

def _is_primitive(v: Any) -> bool:
    return isinstance(v, (str, int, float, bool)) or v is None

def _copy_inputs_keep_connections(raw_inputs: Dict[str, Any]) -> Dict[str, Any]:
    return dict(raw_inputs or {})


# Inputs that are typically link-based (we never assign widgets to these):
_CONNECTION_TYPES: Set[str] = {
    "MODEL", "CLIP", "CONDITIONING", "LATENT", "VAE", "IMAGE", "MASK",
    "CONTROL_NET", "UNET", "GLIGEN", "TENSOR", "DEPTH", "POSE", "SEGMENTATION",
    "AUDIO", "CLIP_VISION",
}

# Simple value types we can strictly coerce
_PRIMITIVE_TYPES: Set[str] = {"INT", "FLOAT", "STRING", "BOOLEAN"}


def _type_matches(expected: Optional[str], val: Any) -> bool:
    if expected is None:
        return False
    t = expected.upper()
    if t in _CONNECTION_TYPES:
        return False
    if t == "INT":
        return isinstance(val, int) or (isinstance(val, str) and val.strip().lstrip("+-").isdigit())
    if t == "FLOAT":
        if isinstance(val, (int, float)):
            return True
        if isinstance(val, str):
            try:
                float(val.strip())
                return True
            except Exception:
                return False
        return False
    if t == "STRING":
        return isinstance(val, (str, int, float, bool))  # permissive; server will stringify as needed
    if t == "BOOLEAN":
        return isinstance(val, bool) or (isinstance(val, str) and val.strip().lower() in ("true","false","0","1"))
    # Unknown or name-like (e.g., SAMPLER_NAME/SCHEDULER_NAME/CKPT_NAME/etc) → treat as string-like
    return isinstance(val, (str, int, float, bool))


def _coerce(expected: Optional[str], val: Any) -> Any:
    if expected is None:
        return val
    t = expected.upper()
    try:
        if t == "INT":
            if isinstance(val, int): return val
            if isinstance(val, float): return int(val)
            if isinstance(val, str): return int(val.strip())
        elif t == "FLOAT":
            if isinstance(val, (int, float)): return float(val)
            if isinstance(val, str): return float(val.strip())
        elif t == "BOOLEAN":
            if isinstance(val, bool): return val
            if isinstance(val, str):
                s = val.strip().lower()
                if s in ("true","1"): return True
                if s in ("false","0"): return False
        # STRING or name-like: stringify
        return str(val) if not isinstance(val, str) else val
    except Exception:
        # leave as-is on failed coercion; the server may still accept it
        return val


class ComfyCompiler:
    def __init__(self) -> None:
        self._resolver_by_base: Dict[str, SchemaResolver] = {}

    def _get_resolver(self, base_url: Optional[str]) -> Optional[SchemaResolver]:
        if not base_url:
            return None
        base = base_url.rstrip("/")
        if base not in self._resolver_by_base:
            self._resolver_by_base[base] = SchemaResolver(base)
        return self._resolver_by_base[base]

    def _map_widgets_using_schema(
        self,
        class_type: str,
        raw_inputs: Dict[str, Any],
        widgets: List[Any],
        resolver: Optional[SchemaResolver],
    ) -> Dict[str, Any]:
        if not resolver or not widgets:
            return {}

        try:
            arg_specs: List[Tuple[str, Optional[str], Dict[str, Any]]] = resolver.get_arg_specs(class_type)
        except Exception:
            return {}

        assigned: Dict[str, Any] = {}
        w_idx = 0

        for (name, ty, meta) in arg_specs:
            # Don't overwrite already-wired connections
            if name in raw_inputs:
                continue

            # Skip known connection types entirely
            if ty and ty.upper() in _CONNECTION_TYPES:
                continue

            # Try to consume the next compatible widget
            while w_idx < len(widgets):
                cand = widgets[w_idx]
                w_idx += 1

                # Only map simple primitives (not dicts/lists)
                if not _is_primitive(cand):
                    continue

                # Primitive types: strict-ish match/coerce
                if ty and ty.upper() in _PRIMITIVE_TYPES:
                    if _type_matches(ty, cand):
                        assigned[name] = _coerce(ty, cand)
                        break
                    else:
                        # e.g. 'randomize' string when INT expected → skip
                        continue

                # Name-like / categorical types (unknown tokens that have choices/default)
                # Treat as string-like; accept string/numeric/bool and stringify
                if isinstance(meta, dict) and ("choices" in meta or "default" in meta):
                    assigned[name] = _coerce("STRING", cand)
                    break

                # Fallback: unknown non-connection → accept as string-like primitive
                # (still safe: connections and lists are not considered here)
                assigned[name] = _coerce("STRING", cand)
                break

            # If we didn't break, we leave this input missing (server default or error if required)

        return assigned

    def compile(self, graph, ctx) -> Dict[str, Any]:
        """
        Build a /prompt payload.
        If ctx.base_url is available, we enrich from the server schema; otherwise we
        still compile with connections + runtime primitive overrides only.
        """
        base_url = getattr(ctx, "base_url", None) if ctx else None
        resolver = self._get_resolver(base_url)

        payload: Dict[str, Any] = {}
        nodes = list(graph.iter_nodes())

        for i, node in enumerate(nodes, start=1):
            # Key: prefer source ID; fall back to deterministic n{i}
            key = getattr(node, "_wm_ext_id", None) or getattr(getattr(node, "meta", None), "label", None) or f"n{i}"
            key = str(key)

            # Class type
            class_type = None
            raw_spec = getattr(node, "_wm_raw_spec", None)
            if isinstance(raw_spec, dict):
                class_type = raw_spec.get("class_type")
            if not class_type:
                class_type = getattr(node, "_wm_class_type", None)
            if not class_type:
                meta = getattr(node, "meta", None)
                class_type = (getattr(meta, "type", None) if meta else None) or getattr(node, "CLASS_TYPE", None) or "Unknown"

            # Start from the editor-wired connections
            inputs = _copy_inputs_keep_connections(raw_spec.get("inputs", {}) if isinstance(raw_spec, dict) else {})

            # Map widgets → named inputs via schema (no hardcoding)
            widgets = list(getattr(node, "_wm_widgets", []) or [])
            if widgets and resolver:
                mapped = self._map_widgets_using_schema(class_type, inputs, widgets, resolver)
                for k, v in mapped.items():
                    inputs.setdefault(k, v)  # don't override connections

            # Overlay runtime param overrides (only primitives)
            try:
                params = node.params()
            except Exception:
                params = {}
            for pname, pval in (params or {}).items():
                if _is_primitive(pval):
                    inputs[pname] = pval

            # Ensure SaveImage filename_prefix exists (newer Comfy requires it)
            if class_type == "SaveImage" and "filename_prefix" not in inputs:
                inputs["filename_prefix"] = "ComfyUI"

            item = {"class_type": class_type or "Unknown", "inputs": inputs}

            # Optional title
            if isinstance(raw_spec, dict) and isinstance(raw_spec.get("_meta"), dict):
                item["_meta"] = dict(raw_spec["_meta"])
            elif getattr(node, "_wm_title", None):
                item["_meta"] = {"title": getattr(node, "_wm_title")}

            payload[key] = item

        return payload
