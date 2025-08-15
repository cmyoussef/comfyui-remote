"""Facade."""
from typing import Dict, Any
from .graph import Graph
from .node_registry import NodeRegistry
from .node_factory import NodeFactory
from ..base.node_base import NodeBase


class NodeCoreAPI:
    def __init__(self, registry: NodeRegistry) -> None:
        self._graph = Graph()
        self._registry = registry
        self._factory = NodeFactory(registry)

    def create_node(self, type_name: str, **kwargs: Any) -> NodeBase:
        node = self._factory.create(type_name, **kwargs)
        self._graph.add_node(node)
        return node

    def connect(self, from_id: str, from_port: str, to_id: str, to_port: str) -> None:
        self._graph.connect(from_id, from_port, to_id, to_port)

    def set_params(self, node_id: str, params: Dict[str, Any]) -> None:
        node = self._graph.get_node(node_id)
        for k, v in params.items(): node.set_param(k, v)

    def list_parameters(self, node_id: str) -> Dict[str, Any]:
        return self._graph.get_node(node_id).params()

    def graph_ref(self) -> Graph:
        return self._graph
