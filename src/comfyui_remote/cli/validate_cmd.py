"""CLI: validate."""
from __future__ import annotations

from ..nodes.core.node_registry import NodeRegistry
from ..nodes.core.node_core_api import NodeCoreAPI
from ..workflows.loader.workflow_loader import WorkflowLoader
from ..services.validation_service import ValidationService


class ValidateCommand:
    @staticmethod
    def configure(p):
        p.add_argument("--workflow", "-w", required=True, help="Path to Comfy editor JSON")

    def run(self, args) -> int:
        api = NodeCoreAPI(NodeRegistry())
        WorkflowLoader(api).load_from_json(args.workflow)
        errs = ValidationService().validate_graph(api.graph_ref())
        if errs:
            print("[validate] errors:", errs)
            return 1
        print("[validate] OK")
        return 0
