"""Exec facade."""
from typing import Dict, Any
from ..workflows.manager.workflow_manager import WorkflowManager
from ..core.base.workflow import ExecutionContext


class ExecutionAPI:
    def __init__(self, wm: WorkflowManager) -> None:
        self._wm = wm

    def run(self, ctx: ExecutionContext) -> Dict[str, Any]:
        return self._wm.execute(ctx)

    def progress(self, handle_id: str):
        # Proxy to manager's best‑effort progress if available
        try:
            return self._wm.get_progress(handle_id)
        except Exception:
            return {}

    def cancel(self, handle_id: str) -> None:
        self._wm.cancel(handle_id)

    def results(self, handle_id: str) -> Dict[str, Any]:
        return self._wm.results(handle_id)
