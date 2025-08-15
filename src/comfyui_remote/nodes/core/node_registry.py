"""Registry."""
from typing import Dict, Type
from ..base.node_base import NodeBase


class NodeRegistry:
    def __init__(self) -> None:
        self._types: Dict[str, Type[NodeBase]] = {}

    def register(self, name: str, cls: Type[NodeBase]) -> None:
        self._types[name] = cls

    def get(self, name: str) -> Type[NodeBase]:
        return self._types[name]

    def all(self): return list(self._types.keys())
