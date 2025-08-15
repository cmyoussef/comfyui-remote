"""VM: workflow."""
from ...nodes.core.node_core_api import NodeCoreAPI


class WorkflowViewModel:
    def __init__(self) -> None:
        self._api: NodeCoreAPI = None

    def set_api(self, api: NodeCoreAPI) -> None:
        self._api = api

    def api(self) -> NodeCoreAPI:
        return self._api
