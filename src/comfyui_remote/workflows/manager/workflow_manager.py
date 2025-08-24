from __future__ import annotations

import json
import os
import re
import warnings  # <-- add
from pathlib import Path
from typing import Dict, Any, Optional, Iterable, List, Tuple

from ...config.manager import ConfigManager
from ...connectors.comfy.connector import ComfyConnector
# REMOVE these two heavy imports (we no longer launch here)
# from ...connectors.comfy.rest_client import ComfyRestClient
# from ...connectors.comfy.server_manager import ComfyServerManager
from ...connectors.comfy.schema_resolver import SchemaResolverRegistry, is_primitive_tag  # <-- add is_primitive_tag
from ...core.base.workflow import ExecutionContext
from ...executors.executor_factory import ExecutorFactory
from ...handlers.output.output_handler import OutputHandler
from ...nodes.core.node_core_api import NodeCoreAPI
from ...nodes.core.node_registry import NodeRegistry
from ...services.progress_service import ProgressService
from ...services.validation_service import ValidationService
from ...workflows.compiler.comfy_compiler import ComfyCompiler
from ...workflows.loader.workflow_loader import WorkflowLoader


def _is_primitive_value(v: Any) -> bool:
    return isinstance(v, (str, int, float, bool)) or v is None


def _compatible(val: Any, tag: Optional[str]) -> bool:
    """Type compatibility aligned with compiler mapping."""
    if tag is None:  # treat as STRING (e.g., choices)
        return isinstance(val, str)
    t = tag.upper()
    if t == "INT":
        return isinstance(val, int)
    if t == "FLOAT":
        return isinstance(val, (int, float))
    if t in ("STRING",):
        return isinstance(val, str)
    if t in ("BOOL", "BOOLEAN"):
        return isinstance(val, bool)
    return False


class WMProgressObserver:
    """Adapter that forwards connector WS events into ProgressService."""

    def __init__(self, svc: ProgressService):
        self._svc = svc

    def update(self, event: Dict[str, Any]) -> None:
        # Fan‑out to all subscribers; ignore best‑effort errors.
        try:
            self._svc.publish(event)
        except Exception:
            pass


def _normalize_ext_id(x: str | int) -> str:
    """Normalize external ID: accepts '6', 6, 'n6' and returns '6'."""
    s = str(x)
    if s.lower().startswith("n"):
        s = s[1:]
    return s.strip()


class WorkflowManager:
    """
    High-level manager: load, index, patch, compile, execute.

    Key points for precise patching:
    - We index the workflow file (editor or compiled prompt) to get {ext_id -> (title, class_type)} and {title -> [ext_id]}.
    - We then bind those ext_ids to the live NodeBase objects by **file order** on load.
    - We store attributes on each node: _wm_ext_id, _wm_title, _wm_class_type, so later lookups are trivial.
    - Title lookups use the file index directly (no guessing).
    """

    def __init__(self,
                 node_registry: Optional[NodeRegistry] = None,
                 node_api: Optional[NodeCoreAPI] = None,
                 validator: Optional[ValidationService] = None,
                 config: Optional[ConfigManager] = None,
                 progress: Optional[ProgressService] = None,
                 output: Optional[OutputHandler] = None,
                 compiler: Optional[ComfyCompiler] = None,
                 executor_factory: Optional[ExecutorFactory] = None) -> None:

        self._registry = node_registry or NodeRegistry()
        self._api = node_api or NodeCoreAPI(self._registry)
        self._validator = validator or ValidationService()
        self._config = config or ConfigManager()
        self._progress = progress or ProgressService()
        self._output = output or OutputHandler()
        self._compiler = compiler or ComfyCompiler()
        self._executors = executor_factory or ExecutorFactory()
        self._last_executor: Optional[ExecutorFactory] = None
        self._loaded_path: Optional[str] = None
        self._ctx: ExecutionContext = ExecutionContext(mode="local")
        self._last_handle_id: Optional[str] = None

        # File-derived index
        self._index_by_id: Dict[str, Dict[str, Any]] = {}  # ext_id -> {title, class_type}
        self._index_by_title: Dict[str, List[str]] = {}  # title -> [ext_id, ...]
        self._ext_ids_order: List[str] = []  # file order of ext_ids
        self._file_nodes: List[Dict[str, Any]] = []  # file order records with ext_id/class_type/title

        # Binding ext_ids to live NodeBase objects (built on load)
        self._bind_ext_to_node: Dict[str, Any] = {}
        self._bind_node_to_ext: Dict[int, str] = {}

        auto_materialize_params = str(os.getenv("COMFY_MATERIALIZE_PARAMS", "true")).lower() in ("1", "true", "yes",
                                                                                                 "on")

        self.auto_materialize_params = auto_materialize_params

    def materialize_params(self, overwrite: bool = False) -> int:
        """
        Populate NodeBase.params() with schema-derived primitive inputs so that
        iterating nodes shows meaningful params (steps, cfg, text, etc.).

        - Uses ComfyCompiler (single source of truth).
        - Skips connection values [src_id, slot].
        - overwrite=False keeps any runtime overrides you've already set.

        Returns the number of (node,param) assignments.
        """
        # Ensure a resolver key (http | file: | inline:)
        key = getattr(self._ctx, "base_url", None)
        if not key:
            try:
                key = SchemaResolverRegistry.ensure()
                self._ctx.base_url = key
            except Exception:
                return 0

        payload = self._compiler.compile(self.graph, self._ctx)
        hits = 0
        for node_id, spec in payload.items():
            ins = spec.get("inputs") or {}
            try:
                node = self.graph.get_node(node_id)
            except Exception:
                continue

            for pname, pval in ins.items():
                # Skip connections of the form [id, slot]
                if isinstance(pval, list) and len(pval) == 2 and all(isinstance(x, (str, int)) for x in pval):
                    continue
                if (not overwrite) and node.has_param(pname):
                    continue
                node.set_param(pname, pval)
                hits += 1
        return hits

    # ---------- Properties ----------
    @property
    def graph(self):
        return self._api.graph_ref()

    @property
    def node_api(self) -> NodeCoreAPI:
        return self._api

    @property
    def loaded_path(self) -> Optional[str]:
        return self._loaded_path

    @property
    def last_handle_id(self) -> Optional[str]:
        return self._last_handle_id

    # ---------- Lifecycle ----------
    def set_execution_context(self, ctx: ExecutionContext) -> None:
        self._ctx = ctx

    def load(self, editor_or_prompt_json_path: str) -> int:
        # Load + index + bind as you had
        WorkflowLoader(self._api).load_from_json(editor_or_prompt_json_path)
        self._loaded_path = str(editor_or_prompt_json_path)
        self._build_index_from_file(self._loaded_path)
        self._bind_nodes_to_file_order()

        count = sum(1 for _ in self.graph.iter_nodes())

        # Optional: auto-materialize (default ON) so params() is immediately useful
        if self.auto_materialize_params:
            try:
                if not getattr(self._ctx, "base_url", None):
                    self._ctx.base_url = SchemaResolverRegistry.ensure()
                self.materialize_params(overwrite=False)
            except Exception:
                # keep non-fatal; you can guard with COMFY_DEBUG to raise
                pass

        return count

    def ensure_schema(self, base_url: Optional[str] = None) -> Optional[str]:
        """
        Ensure a resolver key is available for compiler/saver:
          - honors COMFY_SCHEMA_JSON / COMFY_REMOTE_URL
          - else tries the on-disk cache
          - else launches ephemeral (handled by SchemaResolverRegistry)
        """
        try:
            key = SchemaResolverRegistry.ensure(base_url=base_url or None)
            self._schema_key = key
            self._ctx.base_url = key
            return key
        except Exception:
            return None

    def export_prompt(self,
                      path: Optional[str] = None,
                      ctx: Optional[ExecutionContext] = None,
                      pretty: bool = True) -> Dict[str, Any]:
        """
        Compile and optionally write the /prompt payload.
        - No mutation of the workflow JSON — this is the exact dict you posted.
        """
        payload = self._compiler.compile(self.graph, ctx or self._ctx)
        if path:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            txt = json.dumps(payload, indent=2 if pretty else None, ensure_ascii=False)
            p.write_text(txt, encoding="utf-8")
        return payload

    def save_editor_json(self,
                         out_path: Optional[str] = None,
                         *,
                         allow_clear_titles: bool = False,
                         materialize_params: Optional[bool] = None,
                         pretty: bool = True) -> Dict[str, Any]:
        """
        Persist the *editor JSON* with live titles and (optionally) materialized
        primitive param overrides into widgets_values.

        - If `out_path` is None, returns the patched JSON dict without writing.
        - Only updates what's different (titles / affected widget indices).
        - `materialize_params` defaults to self.auto_materialize_params.
        """
        if not self._loaded_path:
            raise RuntimeError("No workflow loaded; call load(path) first.")

        materialize = self.auto_materialize_params if materialize_params is None else bool(materialize_params)

        try:
            data = json.loads(Path(self._loaded_path).read_text(encoding="utf-8"))
        except Exception as e:
            raise RuntimeError(f"Failed to read editor JSON {self._loaded_path}: {e}") from e

        # Only editor JSON is supported for write-back
        if not (isinstance(data, dict) and "nodes" in data and isinstance(data["nodes"], list)):
            warnings.warn("Loaded workflow was not an editor JSON; skipping write-back.", RuntimeWarning)
            return data

        # Resolve schema (best-effort) — if unavailable, we still save titles
        resolver = None
        if materialize:
            try:
                key = getattr(self._ctx, "base_url", None) or SchemaResolverRegistry.ensure()
                resolver = SchemaResolverRegistry.get(key)
            except Exception:
                resolver = None
                materialize = False
                warnings.warn(
                    "Schema not available; will save titles only (param materialization skipped).",
                    RuntimeWarning
                )

        # Live node lookup by ext_id
        live_by_id: Dict[str, Any] = dict(self._bind_ext_to_node)

        for nd in data["nodes"]:
            if not isinstance(nd, dict):
                continue

            ext_id = _normalize_ext_id(nd.get("id"))
            nb = live_by_id.get(ext_id)
            if nb is None:
                continue

            # ---- Titles (update only when different) ----
            old_title = nd.get("title")
            new_title = nb.title
            if new_title is not None:
                if old_title != new_title:
                    nd["title"] = new_title
            else:
                if allow_clear_titles and "title" in nd:
                    del nd["title"]

            # ---- Param → widgets_values (schema-aware, minimal) ----
            if not materialize:
                continue

            widgets = list(nd.get("widgets_values", []))
            if not widgets:
                continue

            # Resolve arg specs
            arg_specs = []
            try:
                if resolver:
                    arg_specs = resolver.get_arg_specs(nb.ctype)
            except Exception:
                arg_specs = []

            if not arg_specs:
                continue

            assignable = [(nm, ty) for (nm, ty, _meta) in arg_specs if is_primitive_tag(ty)]
            base_inputs: Dict[str, Any] = dict(getattr(nb, "raw_inputs", {}) or {})

            # Rebuild name->index by replaying sliding alignment on ORIGINAL widgets
            name_to_index: Dict[str, int] = {}
            j = 0
            N = len(widgets)
            for name, ty in assignable:
                if name in base_inputs:
                    # connected input: UI often hides a widget; we don't force it
                    continue
                while j < N:
                    tok = widgets[j]
                    j += 1
                    if _compatible(tok, ty):
                        name_to_index[name] = j - 1
                        break

            overrides = nb.params() or {}
            if not overrides:
                continue

            new_widgets = list(widgets)
            changed = False

            for pname, pval in overrides.items():
                if not _is_primitive_value(pval):
                    continue
                idx = name_to_index.get(pname)
                if idx is None or not (0 <= idx < len(new_widgets)):
                    continue
                if new_widgets[idx] != pval:
                    new_widgets[idx] = pval
                    changed = True

            if changed:
                nd["widgets_values"] = new_widgets

        if out_path:
            p = Path(out_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, indent=2 if pretty else None, ensure_ascii=False), encoding="utf-8")

        return data

    def record_run(self,
                   out_dir: str,
                   *,
                   include_compiled: bool = True,
                   include_editor: bool = True,
                   pretty: bool = True) -> Dict[str, str]:
        """
        Save reproducibility artifacts for debugging under `out_dir`:
          - compiled.prompt.json (exact payload)
          - editor.patched.json  (UI-friendly, titles/params reflected)
          - manifest.json        (context snippet)
        Returns a dict of written paths (only those created).
        """
        out: Dict[str, str] = {}
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)

        if include_compiled:
            path = str(d / "compiled.prompt.json")
            self.export_prompt(path, pretty=pretty)
            out["compiled"] = path

        if include_editor:
            path = str(d / "editor.patched.json")
            self.save_editor_json(path, pretty=pretty)
            out["editor"] = path

        manifest = {
            "loaded_path": self._loaded_path,
            "base_url_or_key": getattr(self._ctx, "base_url", None),
            "last_handle_id": self._last_handle_id,
            "node_count": len(self),
        }
        man_path = str(d / "manifest.json")
        Path(man_path).write_text(json.dumps(manifest, indent=2 if pretty else None, ensure_ascii=False),
                                  encoding="utf-8")
        out["manifest"] = man_path

        return out

    # ---------- Indexing from file ----------
    def _build_index_from_file(self, path: str) -> None:
        """
        Populate:
          _index_by_id[ext_id]   = {"title": <or None>, "class_type": <string>}
          _index_by_title[title] = [ext_id, ...]
          _ext_ids_order         = [ext_id, ...]   (file order)
          _file_nodes            = [{"ext_id","class_type","title"}, ...] (file order)
        Works for both Editor JSON and compiled prompt JSON.
        """
        self._index_by_id.clear()
        self._index_by_title.clear()
        self._ext_ids_order.clear()
        self._file_nodes.clear()

        data = {}
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return

        if isinstance(data, dict) and "nodes" in data and isinstance(data["nodes"], list):
            # Editor JSON
            for n in data["nodes"]:
                try:
                    ext_id = _normalize_ext_id(n.get("id"))
                    class_type = str(n.get("type") or "")
                    title = n.get("title") or None
                    self._index_by_id[ext_id] = {"title": title, "class_type": class_type}
                    if title:
                        self._index_by_title.setdefault(title, []).append(ext_id)
                    self._ext_ids_order.append(ext_id)
                    self._file_nodes.append({
                        "ext_id": ext_id,
                        "class_type": class_type,
                        "title": title,
                    })
                except Exception:
                    continue
        elif isinstance(data, dict):
            # Compiled prompt JSON (ordered mapping in modern Python)
            for k, spec in data.items():
                if not isinstance(spec, dict):
                    continue
                try:
                    ext_id = _normalize_ext_id(k)
                    class_type = str(spec.get("class_type") or "")
                    meta = spec.get("_meta") or {}
                    title = meta.get("title") or None
                    self._index_by_id[ext_id] = {"title": title, "class_type": class_type}
                    if title:
                        self._index_by_title.setdefault(title, []).append(ext_id)
                    self._ext_ids_order.append(ext_id)
                    self._file_nodes.append({
                        "ext_id": ext_id,
                        "class_type": class_type,
                        "title": title,
                    })
                except Exception:
                    continue

    def _bind_nodes_to_file_order(self) -> None:
        """
        Bind ext_ids from the file (in order) to live nodes by the **insertion order**
        returned by graph.iter_nodes(). This is the most robust strategy when metadata
        isn't propagated by the loader.

        Also tag nodes with attributes: _wm_ext_id, _wm_title, _wm_class_type
        so subsequent lookups are trivial and fast.
        """
        self._bind_ext_to_node.clear()
        self._bind_node_to_ext.clear()

        nodes_in_graph: List[Any] = list(self.graph.iter_nodes())
        # zip by order; tolerate unequal lengths
        count = min(len(self._ext_ids_order), len(nodes_in_graph))
        for i in range(count):
            ext_id = self._ext_ids_order[i]
            node = nodes_in_graph[i]
            rec = self._index_by_id.get(ext_id, {})
            title = rec.get("title")
            class_type = rec.get("class_type") or ""

            # Attach attributes for future lookups
            try:
                setattr(node, "_wm_ext_id", ext_id)
                if title is not None:
                    setattr(node, "_wm_title", title)
                if class_type:
                    setattr(node, "_wm_class_type", class_type)
            except Exception:
                pass

            self._bind_ext_to_node[ext_id] = node
            self._bind_node_to_ext[id(node)] = ext_id

    # ---------- Selection helpers ----------
    def _node_identity(self, n: Any) -> Tuple[str, str, Optional[str]]:
        """
        Return (ext_id, class_type, title) for a given live node, using:
          - attached attributes (preferred)
          - file index (via reverse binding)
        """
        ext_id = getattr(n, "_wm_ext_id", "") or getattr(n, "_ext_id", "")
        if not ext_id:
            ext_id = self._bind_node_to_ext.get(id(n), "") or ""

        class_type = getattr(n, "_wm_class_type", "")
        title = getattr(n, "_wm_title", None)

        if (not class_type) or (title is None):
            if ext_id and ext_id in self._index_by_id:
                info = self._index_by_id[ext_id]
                class_type = class_type or info.get("class_type", "")
                if title is None:
                    title = info.get("title")
        return ext_id, class_type, title

    def _find_nodes_by_id(self, ext_id: str | int) -> List[Any]:
        ext = _normalize_ext_id(ext_id)
        n = self._bind_ext_to_node.get(ext)
        return [n] if n is not None else []

    def _find_nodes_by_title(self, title: str, match: str = "exact") -> List[Any]:
        """
        match: 'exact' | 'icontains' | 'regex'
        """
        title = title or ""
        out: List[Any] = []
        if not title:
            return out

        if match == "exact" and title in self._index_by_title:
            ids = self._index_by_title.get(title, [])
            for ext in ids:
                n = self._bind_ext_to_node.get(ext)
                if n is not None:
                    out.append(n)
            # Even if some nodes were not bound (different loader), we stop here:
            if out:
                return out
            # Fallback to scan if bindings missing below.

        # Flexible fallback scan using attached titles
        for n in self.graph.iter_nodes():
            _ext, _ct, tl = self._node_identity(n)
            cur = tl or ""
            if not cur:
                continue
            if match == "exact" and cur == title:
                out.append(n)
            elif match == "icontains" and title.lower() in cur.lower():
                out.append(n)
            elif match == "regex" and re.search(title, cur):
                out.append(n)
        return out

    def _find_nodes_by_type(self, class_type: str) -> List[Any]:
        ct = (class_type or "").strip()
        out: List[Any] = []
        if not ct:
            return out
        for n in self.graph.iter_nodes():
            _ext, nct, _tl = self._node_identity(n)
            if nct == ct:
                out.append(n)
        return out

    # ---------- Precise patching ----------
    def set_param_by_title(self, title: str, name: str, value: Any, limit: Optional[int] = None) -> int:
        hits = 0
        t_norm = (title or "").strip().lower()
        for n in self.graph.iter_nodes():
            nt = (n.title or "").strip().lower()
            if nt == t_norm:
                n.set_param(name, value)
                hits += 1
                if limit and hits >= limit:
                    break
        return hits

    def set_param_by_type(self, ctype: str, values: Dict[str, Any], limit: Optional[int] = None) -> int:
        hits = 0
        c_norm = (ctype or "").strip()
        for n in self.graph.iter_nodes():
            if n.ctype == c_norm:
                for k, v in values.items():
                    n.set_param(k, v)
                hits += 1
                if limit and hits >= limit:
                    break
        return hits

    def set_param_by_id(self, ext_id: str | int, name: str, value: Any) -> int:
        ext = _normalize_ext_id(ext_id)
        n = self._bind_ext_to_node.get(ext)
        if n is None:
            return 0
        n.set_param(name, value)
        return 1

    # ---------- Structured overrides ----------
    def apply_overrides(self, spec: Dict[str, Any]) -> int:
        """
        Apply a structured override bundle:

        {
          "by_id":    { "6": {"text":"new text"}, "9": {"filename_prefix":"run_001"} },
          "by_title": { "Main_prompt": {"text":"new text"} },
          "by_type":  { "KSampler": {"steps": 8, "cfg": 3.5 } }
        }
        """
        total = 0
        if not isinstance(spec, dict):
            return 0

        by_id = spec.get("by_id") or {}
        if isinstance(by_id, dict):
            for k, updates in by_id.items():
                if isinstance(updates, dict):
                    for pname, pval in updates.items():
                        total += self.set_param_by_id(k, pname, pval)

        by_title = spec.get("by_title") or {}
        if isinstance(by_title, dict):
            for title, updates in by_title.items():
                if isinstance(updates, dict):
                    for pname, pval in updates.items():
                        total += self.set_param_by_title(title, pname, pval)

        by_type = spec.get("by_type") or {}
        if isinstance(by_type, dict):
            for ctype, updates in by_type.items():
                if isinstance(updates, dict):
                    total += self.set_param_by_type(ctype, updates)

        return total

    # ---------- Blanket (legacy) ----------
    def apply_globals(self, overrides: Dict[str, Any]) -> int:
        """
        Blanket/legacy behavior: for each (k,v), set wherever param 'k' exists.
        Prefer the precise APIs.
        """
        hits = 0
        for n in self.graph.iter_nodes():
            np = n.params()
            for k, v in overrides.items():
                if k in np:
                    n.set_param(k, v)
                    hits += 1
        return hits

    # Back-compat alias
    def apply_params(self, overrides: Dict[str, Any]) -> int:
        return self.apply_globals(overrides)

    # ---------- Validation / Execution ----------
    def validate(self) -> Iterable[Dict[str, Any]]:
        return self._validator.validate_graph(self.graph)

    def execute(self, ctx: Optional[ExecutionContext] = None) -> Dict[str, Any]:
        _ = self.validate()
        use_ctx = ctx or self._ctx
        executor = self._executors.create(use_ctx.mode, use_ctx)
        self._last_executor = executor  # <-- keep a handle for cancel()

        obs = WMProgressObserver(self._progress)
        try:
            executor.set_observer(obs)  # optional
        except Exception:
            pass

        result = executor.execute(self.graph, use_ctx)
        self._last_handle_id = result.get("handle_id")
        try:
            self._output.store(self._last_handle_id or "last", result.get("artifacts", {}))
        except Exception:
            pass
        return result

    def cancel(self, handle_id: str) -> None:
        """
        Best‑effort cancellation via the last executor, if available.
        """
        try:
            ex = getattr(self, "_last_executor", None)
            if ex is not None:
                ex.cancel(handle_id)
        except Exception:
            pass

    def results(self, handle_id: str) -> Dict[str, Any]:
        """
        Return collected artifacts/outputs for a run handle.
        Uses the existing remote outputs path when applicable.
        """
        try:
            return self.get_outputs(handle_id) if hasattr(self, "get_outputs") else {}
        except Exception:
            return {}

    def get_progress(self, handle_id: str) -> Dict[str, Any]:
        """
        Best‑effort status: if outputs exist we consider it 'success', else 'running'.
        """
        try:
            base = self._ctx.base_url or ""
            if not base:
                return {}
            conn = ComfyConnector(base_url=base, auth=self._ctx.auth or {})
            outs = conn.fetch_outputs(handle_id)
            return {"state": "success"} if outs else {"state": "running"}
        except Exception:
            return {}

    def get_outputs(self, handle_id: str) -> Dict[str, Any]:
        try:
            base = self._ctx.base_url or ""
            if not base:
                return {}
            conn = ComfyConnector(base_url=base, auth=self._ctx.auth or {})
            return conn.fetch_outputs(handle_id)
        except Exception:
            return {}

    # ---------- Debug helpers ----------
    def debug_index(self) -> Dict[str, Any]:
        """
        Return a snapshot of our file index and live bindings for diagnostics.
        """
        return {
            "file_order": list(self._ext_ids_order),
            "index_by_id": dict(self._index_by_id),
            "index_by_title": {k: list(v) for k, v in self._index_by_title.items()},
            "bound_ids": list(self._bind_ext_to_node.keys()),
            "bound_count": len(self._bind_ext_to_node),
        }

    def debug_dump_bindings(self) -> None:
        """
        Print ext_id -> (class_type, title) with whether a node is bound.
        """
        print("[WM] File nodes (order):")
        for rec in self._file_nodes:
            ext = rec["ext_id"]
            n = self._bind_ext_to_node.get(ext)
            print(f"  id={ext:>3}  type={rec['class_type']:<22}  title={rec['title']!r}  bound={'Y' if n else 'N'}")

    # -------- Python container protocol (delegate to Graph) --------
    def __iter__(self):
        yield from self.graph.iter_nodes()

    def __len__(self):
        return sum(1 for _ in self.graph.iter_nodes())

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.graph.iter_nodes())[key]
        # treat as ext_id
        ext = _normalize_ext_id(str(key))
        n = self._bind_ext_to_node.get(ext)
        if n is None:
            raise KeyError(key)
        return n

    def __contains__(self, key) -> bool:
        from ...nodes.base.node_base import NodeBase
        if isinstance(key, NodeBase):
            return id(key) in self._bind_node_to_ext
        return _normalize_ext_id(str(key)) in self._bind_ext_to_node

    def __bool__(self) -> bool:
        return len(self) > 0

    def __str__(self) -> str:
        return f"<WorkflowManager {self._loaded_path}, nodes={len(self)}, ctx={self._ctx!r}>"

    def __repr__(self) -> str:
        return str(self)
