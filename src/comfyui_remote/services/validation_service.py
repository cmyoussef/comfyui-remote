"""Validation."""
from typing import List
from ..nodes.core.graph import Graph


class ValidationService:
    def validate_graph(self, graph: Graph) -> List[str]:
        errs = []
        if not list(graph.iter_nodes()):
            errs.append("Graph is empty")
        return errs

    def validate_node(self, node) -> List[str]:
        return []

    def validate_params(self, node, params) -> List[str]:
        return []
