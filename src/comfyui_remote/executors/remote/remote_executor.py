from __future__ import annotations

import uuid
from typing import Optional, Dict, Any

from ...core.base.executor import ExecutorBase
from ...core.base.workflow import ExecutionContext
from ...connectors.comfy.connector import ComfyConnector
from ...workflows.compiler.comfy_compiler import ComfyCompiler


class RemoteExecutor(ExecutorBase):
    """
    Executes a compiled graph on an already-running ComfyUI server.

    Requires: ExecutionContext(mode="remote", base_url="http://host:port")
    """

    def __init__(self) -> None:
        super().__init__()
        self._connector: Optional[ComfyConnector] = None
        self._current_client_id: Optional[str] = None

    # ---- ExecutorBase required API ----
    def prepare(self, graph, ctx: ExecutionContext) -> None:
        if not ctx or ctx.mode != "remote" or not ctx.base_url:
            raise ValueError("RemoteExecutor requires ExecutionContext(mode='remote', base_url=...)")
        self._connector = ComfyConnector(base_url=ctx.base_url, auth=(ctx.auth if hasattr(ctx, "auth") else None))

    def submit(self, graph, ctx: ExecutionContext) -> str:
        if self._connector is None:
            raise RuntimeError("RemoteExecutor not prepared")

        # Compile payload
        payload = ComfyCompiler().compile(graph, ctx)
        if self._debug:
            print("[remote-exec] compiled payload:", payload)

        # Use the SAME client_id for WS and REST
        self._current_client_id = f"remote-{uuid.uuid4().hex[:8]}"
        try:
            # If open() accepts a client_id, use it; otherwise fall back
            self._connector.open(client_id=self._current_client_id)  # type: ignore[call-arg]
        except TypeError:
            self._connector.open()

        prompt_id = self._connector.post_workflow(payload, client_id=self._current_client_id)
        return prompt_id

    def poll(self, handle_id: str) -> Dict[str, Any]:
        if self._connector is None:
            raise RuntimeError("RemoteExecutor not prepared")

        st = self._connector.status(handle_id) or {}
        state = st.get("state")
        if state:
            return st

        # Fallback if WS events didn't arrive: try /history and infer success
        try:
            outs = self._connector.fetch_outputs(handle_id)
            if outs:  # If outputs are present, the prompt completed
                return {"state": "success", "outputs_present": True}
        except Exception:
            pass

        return st

    def collect(self, handle_id: str) -> Dict[str, Any]:
        if self._connector is None:
            raise RuntimeError("RemoteExecutor not prepared")
        return self._connector.fetch_outputs(handle_id)

    def cancel(self, handle_id: str) -> None:
        if self._connector:
            try:
                self._connector.cancel(handle_id)
            finally:
                self._connector.close()

    # Optional hook so ExecutorBase can subscribe a progress observer
    def connector(self):
        return self._connector
