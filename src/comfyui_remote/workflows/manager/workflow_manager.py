from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, Iterable, List, Tuple

from ...config.manager import ConfigManager
from ...connectors.comfy.connector import ComfyConnector
from ...core.base.workflow import ExecutionContext
from ...executors.executor_factory import ExecutorFactory
from ...handlers.output.output_handler import OutputHandler
from ...nodes.core.node_core_api import NodeCoreAPI
from ...nodes.core.node_registry import NodeRegistry
from ...services.progress_service import ProgressService
from ...services.validation_service import ValidationService
from ...workflows.compiler.comfy_compiler import ComfyCompiler
from ...workflows.loader.workflow_loader import WorkflowLoader


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
        """
        Load editor JSON or compiled prompt JSON, build the file index,
        and bind ext_ids to the actual NodeBase instances by file order.
        """
        # Load into the live graph
        WorkflowLoader(self._api).load_from_json(editor_or_prompt_json_path)
        self._loaded_path = str(editor_or_prompt_json_path)

        # Build a precise index from the file
        self._build_index_from_file(self._loaded_path)

        # Bind live nodes by file order
        self._bind_nodes_to_file_order()

        return sum(1 for _ in self.graph.iter_nodes())

    def get_compiled_prompt(self, ctx: Optional[ExecutionContext] = None) -> Dict[str, Any]:
        return self._compiler.compile(self.graph, ctx or self._ctx)

    def save_prompt(self, path: str | Path, ctx: Optional[ExecutionContext] = None) -> None:
        """Serialize the compiled prompt. If you want schema‑driven expansion,
        pass a ctx with base_url or call set_execution_context(...) first."""
        payload = self._compiler.compile(self.graph, ctx or self._ctx)
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

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

    def set_param_by_type(self, class_type: str, updates: Dict[str, Any], limit: Optional[int] = None) -> int:
        hits = 0
        for n in self.graph.iter_nodes():
            ctype = getattr(n, "_wm_class_type", None) or getattr(getattr(n, "meta", None), "type", None)
            if ctype == class_type:
                for k, v in updates.items():
                    n.set_param(k, v)
                    hits += 1
                    if limit and hits >= limit:
                        return hits
        return hits

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
                        total += self.set_param_by_title(title, pname, pval, match="exact")

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
