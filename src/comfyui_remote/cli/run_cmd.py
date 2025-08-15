"""CLI: run."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from ..nodes.core.node_registry import NodeRegistry
from ..nodes.core.node_core_api import NodeCoreAPI
from ..workflows.loader.workflow_loader import WorkflowLoader
from ..workflows.manager.workflow_manager import WorkflowManager
from ..services.validation_service import ValidationService
from ..services.progress_service import ProgressService
from ..services.config_manager import ConfigManager
from ..handlers.output.output_handler import OutputHandler
from ..core.base.workflow import ExecutionContext


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
        p.add_argument("--workflow", "-w", required=True, help="Path to Comfy editor JSON")
        p.add_argument("--params", "-p", help="YAML/JSON overrides")
        p.add_argument("--mode", choices=("local", "remote"), default="local")
        p.add_argument("--url", help="Remote base URL (for --mode remote)")
        p.add_argument("--token", help="Auth token (optional)")
        p.add_argument("--verbose", action="store_true")

    def run(self, args) -> int:
        reg = NodeRegistry()
        api = NodeCoreAPI(reg)
        WorkflowLoader(api).load_from_json(args.workflow)

        overrides = _load_params(args.params)
        wm = WorkflowManager(
            api,
            ValidationService(),
            ConfigManager(),
            ProgressService(),
            OutputHandler(),
        )
        if overrides:
            wm.apply_params(overrides)

        ctx = ExecutionContext(
            mode=args.mode,
            base_url=args.url or "",
            auth={"token": args.token} if args.token else {},
        )

        try:
            result = wm.execute(ctx)
            # We don't fail the CLI if the server run ends in 'error' — this is a launcher.
            if args.verbose:
                print("[run] result:", result)
            return 0
        except Exception as e:
            print("[run] error:", e)
            return 1
