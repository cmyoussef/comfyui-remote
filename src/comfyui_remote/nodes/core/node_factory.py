"""Factory."""
from typing import Any
from ..base.node_base import NodeBase, NodeMetadata
from .node_registry import NodeRegistry


class NodeFactory:
    def __init__(self, registry: NodeRegistry) -> None:
        self._registry = registry

    def create(self, name: str, **kwargs: Any) -> NodeBase:
        cls = self._registry.get(name)
        meta = NodeMetadata(type=name, label=kwargs.pop("label", name))
        return cls(meta, **kwargs)
