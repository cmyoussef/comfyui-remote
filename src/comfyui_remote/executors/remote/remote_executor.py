"""Remote executor."""
from typing import Dict, Any
import uuid
from ...core.base.executor import IExecutor
from ...core.base.workflow import ExecutionContext
from ...nodes.core.graph import Graph
from ...connectors.comfy.connector import ComfyConnector
from ...workflows.compiler.comfy_compiler import ComfyCompiler
from ...services.progress_service import ProgressEventAdapter


class RemoteExecutor(IExecutor):
    def __init__(self) -> None:
        self._connector: ComfyConnector = None

    def prepare(self, graph: Graph, ctx: ExecutionContext) -> None:
        self._connector = ComfyConnector(base_url=ctx.base_url, auth=ctx.auth)
        self._connector.open()

    def submit(self, graph: Graph, ctx: ExecutionContext) -> str:
        client_id = str(uuid.uuid4())
        payload = ctx.extras.get("_compiled_payload") or ComfyCompiler().compile(graph, ctx)
        ctx.extras["_compiled_payload"] = payload
        prompt_id = self._connector.post_workflow(payload, client_id=client_id)
        observer = getattr(ctx, "progress_observer", None) or ProgressEventAdapter()
        self._connector.subscribe(prompt_id, observer)
        return prompt_id

    def poll(self, handle_id: str) -> Dict[str, Any]:
        return self._connector.status(handle_id)

    def cancel(self, handle_id: str) -> None:
        self._connector.cancel(handle_id)

    def collect(self, handle_id: str) -> Dict[str, Any]:
        artifacts = self._connector.fetch_outputs(handle_id)
        self._connector.close()
        return {"handle_id": handle_id, "artifacts": artifacts}
