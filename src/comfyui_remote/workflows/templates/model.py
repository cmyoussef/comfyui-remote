"""Template model."""
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class WorkflowTemplate:
    id: str
    name: str
    meta: Dict[str, Any]
    defaults: Dict[str, Any]
    path: str
