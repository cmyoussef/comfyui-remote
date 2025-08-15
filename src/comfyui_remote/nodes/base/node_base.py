"""Node base."""
from typing import Dict, Any
from dataclasses import dataclass, field
import uuid


@dataclass
class NodeMetadata:
    type: str
    label: str = ""
    category: str = ""


class NodeBase:
    def __init__(self, meta: NodeMetadata, **params: Any) -> None:
        self._id = str(uuid.uuid4())
        self._meta = meta
        self._params: Dict[str, Any] = dict(params)

    def get_id(self) -> str: return self._id
    def inputs(self) -> Dict[str, Any]: return {}
    def outputs(self) -> Dict[str, Any]: return {}
    def set_param(self, name: str, value: Any) -> None: self._params[name] = value
    def get_param(self, name: str) -> Any: return self._params.get(name)
    def params(self) -> Dict[str, Any]: return dict(self._params)
    def meta(self) -> NodeMetadata: return self._meta
