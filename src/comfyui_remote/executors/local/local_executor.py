"""Local executor."""
from __future__ import annotations

import os
import uuid

from ...connectors.comfy.connector import ComfyConnector
from ...connectors.comfy.server_manager import ComfyServerManager
from ...core.base.executor import ExecutorBase
from ...core.base.workflow import ExecutionContext
from ...workflows.compiler.comfy_compiler import ComfyCompiler


class LocalExecutor(ExecutorBase):
    def __init__(self):
        super().__init__()
        self._server = ComfyServerManager()
        self._handle = None
        self._connector = None

    def prepare(self, graph, ctx: ExecutionContext):
        opts = {}
        # allow tests to pass IO dirs
        if ctx and getattr(ctx, "extras", None):
            for k in ("input_dir", "output_dir", "temp_dir", "user_dir"):
                if ctx.extras.get(k):
                    opts[k] = ctx.extras[k]
        self._handle = self._server.start(opts)
        base = f"http://127.0.0.1:{self._handle.port}"
        self._connector = ComfyConnector(base_url=base, auth=(ctx.auth if ctx else None))

    def submit(self, graph, ctx: ExecutionContext) -> str:
        compiler = ComfyCompiler()
        payload = compiler.compile(graph, ctx)
        if os.getenv("COMFY_DEBUG"):
            print("[local-exec] compiled payload:", payload)

        if self._connector is None:  # safety
            base = f"http://127.0.0.1:{self._handle.port}"
            self._connector = ComfyConnector(base_url=base)

        client_id = f"local-{uuid.uuid4().hex[:8]}"
        try:
            self._connector.open(client_id=client_id)  # type: ignore[call-arg]
        except TypeError:
            self._connector.open()

        prompt_id = self._connector.post_workflow(payload, client_id=client_id)
        return prompt_id

    def poll(self, handle_id: str):
        return self._connector.status(handle_id)

    def collect(self, handle_id: str):
        try:
            return self._connector.fetch_outputs(handle_id)
        finally:
            try:
                if self._connector:
                    self._connector.close()
            finally:
                if self._handle:
                    self._server.stop()

    def cancel(self, handle_id: str):
        try:
            self._connector.cancel(handle_id)
        finally:
            if self._connector:
                self._connector.close()
            if self._handle:
                self._server.stop()

    def connector(self):
        return self._connector
