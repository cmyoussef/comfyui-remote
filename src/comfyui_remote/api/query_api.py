"""Query facade."""
from typing import Dict, Any, List
from ..nodes.core.node_core_api import NodeCoreAPI


class QueryAPI:
    def __init__(self, node_api: NodeCoreAPI) -> None:
        self._api = node_api

    def describe_graph(self) -> Dict[str, Any]:
        nodes = []
        for n in self._api.graph_ref().iter_nodes():
            nodes.append({
                "id": n.get_id(),
                "type": n.meta().type,
                "label": n.meta().label,
                "params": n.params()
            })
        return {"nodes": nodes}

    def list_nodes(self) -> List[str]:
        return [n.meta().type for n in self._api.graph_ref().iter_nodes()]

    def get_node(self, node_id: str) -> Dict[str, Any]:
        n = self._api.graph_ref().get_node(node_id)
        return {"id": n.get_id(), "type": n.meta().type, "params": n.params()}
