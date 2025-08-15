"""Executor factory."""
from typing import Optional
from .local.local_executor import LocalExecutor
from .remote.remote_executor import RemoteExecutor
from ..core.base.executor import IExecutor
from ..core.base.workflow import ExecutionContext


class ExecutorFactory:
    def create(self, mode: str, ctx: ExecutionContext) -> IExecutor:
        m = (mode or "local").lower()
        if m == "local":
            return LocalExecutor()
        if m == "remote":
            if not ctx.base_url:
                raise ValueError("Remote mode requires base_url")
            return RemoteExecutor()
        # Plugins could be resolved via entry points here.
        raise ValueError(f"Unknown mode: {mode}")
