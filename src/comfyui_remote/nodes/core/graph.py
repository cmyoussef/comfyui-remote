"""Graph model."""
from dataclasses import dataclass
from typing import Dict, List, Tuple
from ..base.node_base import NodeBase


@dataclass
class Connection:
    out_node_id: str
    out_port: str
    in_node_id: str
    in_port: str


class Graph:
    def __init__(self) -> None:
        self._nodes: Dict[str, NodeBase] = {}
        self._edges: List[Connection] = []

    def add_node(self, node: NodeBase) -> None:
        self._nodes[node.get_id()] = node

    def get_node(self, node_id: str) -> NodeBase:
        return self._nodes[node_id]

    def iter_nodes(self):
        return self._nodes.values()

    def connect(self, a_id: str, a_port: str, b_id: str, b_port: str) -> None:
        self._edges.append(Connection(a_id, a_port, b_id, b_port))

    def iter_connections(self):
        return iter(self._edges)

    def as_tuple(self) -> Tuple[Dict[str, NodeBase], List[Connection]]:
        return self._nodes, self._edges
