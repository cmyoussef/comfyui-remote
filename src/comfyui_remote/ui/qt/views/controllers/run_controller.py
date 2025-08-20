"""Run controller."""
from ...core.base.workflow import ExecutionContext
from ...handlers.output.output_handler import OutputHandler
from ...nodes.core.node_core_api import NodeCoreAPI
from ...nodes.core.node_registry import NodeRegistry
from ...services.config_manager import ConfigManager
from ...services.logging_service import LoggingService
from ...services.progress_service import ProgressService
from ...services.validation_service import ValidationService
from ...workflows.loader.workflow_loader import WorkflowLoader
from ...workflows.manager.workflow_manager import WorkflowManager


class RunController:
    def __init__(self, wf_vm, params_model, runs_model):
        self._wf_vm = wf_vm
        self._params_model = params_model
        self._runs_model = runs_model
        self._logger = LoggingService().get_logger("comfy.ui.run")

    def load_workflow_file(self, path: str) -> None:
        registry = NodeRegistry()
        api = NodeCoreAPI(registry)
        loader = WorkflowLoader(api)
        loader.load_from_json(path)

        self._wf_vm.set_api(api)
        self._params_model.set_graph(api.graph_ref())

    def run_local(self) -> None:
        api = self._wf_vm.api()
        if api is None:
            self._logger.error("No workflow loaded")
            return

        wm = WorkflowManager(node_api=api)
        ctx = ExecutionContext(mode="local")
        res = wm.execute(ctx)
        self._logger.info("Run finished: %s", res.get("status"))
