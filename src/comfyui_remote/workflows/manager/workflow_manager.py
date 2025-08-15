"""Workflow orchestrator."""
from typing import Dict, Any, Callable, Optional
from ...nodes.core.node_core_api import NodeCoreAPI
from ...services.validation_service import ValidationService
from ...services.progress_service import ProgressService, IProgressObserver
from ...services.config_manager import ConfigManager
from ...handlers.output.output_handler import OutputHandler
from ..compiler.comfy_compiler import ComfyCompiler
from ...executors.executor_factory import ExecutorFactory
from ...core.base.workflow import ExecutionContext
from ...core.exceptions import ValidationError


class WMProgressObserver(IProgressObserver):
    def __init__(self, bus: ProgressService) -> None:
        self._bus = bus

    def update(self, event: Dict[str, Any]) -> None:
        self._bus.publish(event)


class WorkflowManager:
    def __init__(self,
                 node_api: NodeCoreAPI,
                 validator: ValidationService,
                 config: ConfigManager,
                 progress: ProgressService,
                 output: OutputHandler,
                 compiler: Optional[ComfyCompiler] = None) -> None:
        self._api = node_api
        self._validator = validator
        self._config = config
        self._progress = progress
        self._output = output
        self._compiler = compiler or ComfyCompiler()
        self._on_progress: Optional[Callable[[Dict[str, Any]], None]] = None

    def load_workflow(self, loader_callable, *args, **kwargs) -> None:
        loader_callable(*args, **kwargs)

    def apply_params(self, overrides: Dict[str, Any]) -> None:
        for node in self._api.graph_ref().iter_nodes():
            for k, v in overrides.items():
                node.set_param(k, v)

    def validate(self) -> None:
        errs = self._validator.validate_graph(self._api.graph_ref())
        if errs:
            raise ValidationError("; ".join(errs))

    def on_progress(self, cb: Callable[[Dict[str, Any]], None]) -> None:
        self._on_progress = cb
        if cb:
            self._progress.subscribe(cb)

    def execute(self, ctx: ExecutionContext) -> Dict[str, Any]:
        self.validate()
        executor = ExecutorFactory().create(ctx.mode, ctx)
        # bind progress
        obs = WMProgressObserver(self._progress)
        self._progress.attach_connector_observer = obs  # hint for connector
        result = executor.execute(self._api.graph_ref(), ctx)
        self._output.store(result.get("handle_id", "last"), result.get("artifacts", {}))
        return result

    def cancel(self, handle_id: str) -> None:
        # This would require a retained executor/connector registry; kept simple now.
        pass

    def results(self, handle_id: str) -> Dict[str, Any]:
        return self._output.paths(handle_id)
