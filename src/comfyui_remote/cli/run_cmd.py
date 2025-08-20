"""CLI: run."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from ..core.base.workflow import ExecutionContext
from ..nodes.core.node_core_api import NodeCoreAPI
from ..nodes.core.node_registry import NodeRegistry
from ..workflows.loader.workflow_loader import WorkflowLoader
from ..workflows.manager.workflow_manager import WorkflowManager


def _load_params(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    text = open(path, "r", encoding="utf-8").read()
    # very small YAML/JSON best‑effort: try JSON first, then yaml if installed
    try:
        return json.loads(text)
    except Exception:
        try:
            import yaml  # type: ignore
            return yaml.safe_load(text) or {}
        except Exception:
            return {}


class RunCommand:
    @staticmethod
    def configure(p):
        p.add_argument("--workflow", "-w", required=True, help="Path to Comfy editor JSON or prompt JSON")
        p.add_argument("--params", "-p", help="YAML/JSON overrides")
        p.add_argument("--mode", choices=("local", "remote"), default="local")
        p.add_argument("--url", help="Remote base URL (for --mode remote)")
        p.add_argument("--token", help="Auth token (optional)")

        # NEW: explicit I/O override flags (optional)
        p.add_argument("--input-dir", help="Override Comfy input directory")
        p.add_argument("--output-dir", help="Override Comfy output directory")
        p.add_argument("--temp-dir", help="Override Comfy temp directory")
        p.add_argument("--user-dir", help="Override Comfy user directory")

        p.add_argument("--verbose", action="store_true")

    def run(self, args) -> int:
        reg = NodeRegistry()
        api = NodeCoreAPI(reg)
        WorkflowLoader(api).load_from_json(args.workflow)

        overrides = _load_params(args.params)
        wm = WorkflowManager(node_api=api)
        if overrides:
            wm.apply_params(overrides)

        # Resolve I/O dirs from CLI or environment (test expects COMFY_INPUT_DIR/COMFY_OUTPUT_DIR).
        def _pick(cli_val: Optional[str], *env_names: str) -> Optional[str]:
            if cli_val:
                return cli_val
            for name in env_names:
                v = os.getenv(name)
                if v:
                    return v
            return None

        extras: Dict[str, Any] = {}
        v = _pick(getattr(args, "input_dir", None), "COMFY_INPUT_DIR", "COMFY_INPUT")
        if v:
            extras["input_dir"] = v
        v = _pick(getattr(args, "output_dir", None), "COMFY_OUTPUT_DIR", "COMFY_OUTPUT")
        if v:
            extras["output_dir"] = v
        v = _pick(getattr(args, "temp_dir", None), "COMFY_TEMP_DIR", "COMFY_TEMP")
        if v:
            extras["temp_dir"] = v
        v = _pick(getattr(args, "user_dir", None), "COMFY_USER_DIR", "COMFY_USER")
        if v:
            extras["user_dir"] = v

        if args.verbose and extras:
            print("[run] using I/O overrides:", extras)

        ctx = ExecutionContext(
            mode=args.mode,
            base_url=args.url or "",
            auth={"token": args.token} if args.token else {},
            extras=extras,  # <-- critical for the LocalExecutor → ComfyServerManager
        )

        try:
            result = wm.execute(ctx)
            if args.verbose:
                print("[run] result:", result)
            # Always return 0 on completion (launcher semantics), even if the remote run ended in 'error'.
            return 0
        except Exception as e:
            print("[run] error:", e)
            return 1
