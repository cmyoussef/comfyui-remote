"""Workflow facade."""
from typing import Dict, Any, List
from ..workflows.templates.repository import TemplateRepository
from ..workflows.loader.workflow_loader import WorkflowLoader
from ..nodes.core.node_core_api import NodeCoreAPI


class WorkflowAPI:
    def __init__(self, repo: TemplateRepository, loader: WorkflowLoader, node_api: NodeCoreAPI) -> None:
        self._repo = repo
        self._loader = loader
        self._node_api = node_api

    def list_templates(self) -> List[Dict[str, Any]]:
        return [dict(id=t.id, name=t.name, path=t.path) for t in self._repo.list()]

    def load(self, src: str, is_template: bool = False) -> None:
        if is_template:
            tpl = self._repo.get(src)
            self._loader.load_from_template(tpl)
        else:
            self._loader.load_from_json(src)

    def parameters(self) -> Dict[str, Any]:
        out = {}
        for n in self._node_api.graph_ref().iter_nodes():
            out[n.meta().label or n.meta().type] = n.params()
        return out

    def set_params(self, d: Dict[str, Any]) -> None:
        for n in self._node_api.graph_ref().iter_nodes():
            for k, v in d.items(): n.set_param(k, v)
