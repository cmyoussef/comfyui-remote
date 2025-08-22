# src/comfyui_remote/workflows/compiler/comfy_compiler.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ...connectors.comfy.schema_resolver import (
    SchemaResolverRegistry,
    is_primitive_tag,
)


def _is_primitive_value(v: Any) -> bool:
    return isinstance(v, (str, int, float, bool)) or v is None


def _compatible(val: Any, tag: Optional[str]) -> bool:
    """Type compatibility used by the sliding alignment."""
    if tag is None:
        # treat as STRING (e.g., choices)
        return isinstance(val, str)
    tag = tag.upper()
    if tag == "INT":
        return isinstance(val, int)
    if tag == "FLOAT":
        return isinstance(val, (int, float))
    if tag in ("STRING",):
        return isinstance(val, str)
    if tag in ("BOOL", "BOOLEAN"):
        return isinstance(val, bool)
    # non-primitive connector types are never matched from widgets
    return False


class ComfyCompiler:
    """
    Compile a NodeGraph into a /prompt payload by:
      1) starting from recorded connections (node.raw_inputs)
      2) mapping widgets_values into named inputs using the server schema
         (type-aware sliding alignment; skips UI-only tokens like "randomize")
      3) overlaying runtime primitive overrides from node.params()
      4) ensuring SaveImage has filename_prefix
    """

    def __init__(self, resolver_timeout: float = 5.0) -> None:
        self._resolver_timeout = resolver_timeout

    def _assign_widgets_with_schema(
        self,
        base_inputs: Dict[str, Any],
        widgets: List[Any],
        arg_specs: List[tuple],
    ) -> None:
        if not widgets or not arg_specs:
            return

        # Filter to widget-assignable (primitive) names and keep order
        assignable = [(nm, ty) for (nm, ty, _meta) in arg_specs if is_primitive_tag(ty)]

        j = 0
        N = len(widgets)
        for name, ty in assignable:
            if name in base_inputs:
                # connection already provides it
                continue
            # slide forward to a compatible token
            while j < N:
                candidate = widgets[j]
                j += 1
                if _compatible(candidate, ty):
                    base_inputs[name] = candidate
                    break
            # if we run out of tokens, we leave it unset
        # done

    def compile(self, graph, ctx) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}

        base_url = getattr(ctx, "base_url", "") if ctx else ""
        resolver = SchemaResolverRegistry.get(base_url, timeout=self._resolver_timeout) if base_url else None

        for node in list(graph.iter_nodes()):
            key = str(node.get_id())

            # 1) start with connections (graph structure)
            inputs: Dict[str, Any] = dict(node.raw_inputs)

            # 2) map widgets to named inputs using the server schema
            if resolver:
                try:
                    arg_specs = resolver.get_arg_specs(node.ctype)
                except Exception:
                    arg_specs = []
                if arg_specs:
                    self._assign_widgets_with_schema(inputs, list(node.widgets_values), arg_specs)

            # 3) overlay primitive runtime overrides
            for pname, pval in node.params().items():
                if _is_primitive_value(pval):
                    inputs[pname] = pval

            # 4) SaveImage nicety
            if node.ctype == "SaveImage" and "filename_prefix" not in inputs:
                inputs["filename_prefix"] = "ComfyUI"

            entry = {"class_type": node.ctype, "inputs": inputs}
            if node.title:
                entry["_meta"] = {"title": node.title}
            payload[key] = entry

        return payload
