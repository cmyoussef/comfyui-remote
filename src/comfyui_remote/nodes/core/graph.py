# src/comfyui_remote/nodes/core/graph.py
"""Graph model."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Iterator, Union

from ..base.node_base import NodeBase


@dataclass
class Connection:
    out_node_id: str
    out_port: str
    in_node_id: str
    in_port: str


class Graph:
    """
    Container of NodeBase, preserving file/editor insertion order.
    Supports iteration, len(), indexing by position or external id, and membership.
    """
    def __init__(self) -> None:
        self._nodes: Dict[str, NodeBase] = {}   # ext_id -> NodeBase
        self._order: List[str] = []             # insertion order of ext_ids
        self._edges: List[Connection] = []

    # -------- nodes API --------
    def add_node(self, node: NodeBase) -> None:
        nid = node.get_id()
        if nid not in self._nodes:
            self._order.append(nid)
        self._nodes[nid] = node

    def get_node(self, node_id: str) -> NodeBase:
        return self._nodes[str(node_id)]

    def iter_nodes(self) -> Iterator[NodeBase]:
        """Explicit iterator in insertion order (back-compat)."""
        for nid in self._order:
            yield self._nodes[nid]

    # -------- connections API --------
    def connect(self, a_id: str, a_port: str, b_id: str, b_port: str) -> None:
        self._edges.append(Connection(a_id, a_port, b_id, b_port))

    def iter_connections(self) -> Iterator[Connection]:
        return iter(self._edges)

    def as_tuple(self) -> Tuple[Dict[str, NodeBase], List[Connection]]:
        return self._nodes, self._edges

    # -------- Python container protocol --------
    def __iter__(self) -> Iterator[NodeBase]:
        return self.iter_nodes()

    def __len__(self) -> int:
        return len(self._order)

    def __getitem__(self, key: Union[int, str]) -> NodeBase:
        if isinstance(key, int):
            nid = self._order[key]
            return self._nodes[nid]
        return self._nodes[str(key)]

    def __contains__(self, key: object) -> bool:
        if isinstance(key, NodeBase):
            # membership by identity
            return key.get_id() in self._nodes and self._nodes[key.get_id()] is key
        try:
            return str(key) in self._nodes
        except Exception:
            return False
