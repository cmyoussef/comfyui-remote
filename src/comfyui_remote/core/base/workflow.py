"""Workflow types."""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class ExecutionContext:
    mode: str = "local"
    work_dir: str = "."
    base_url: Optional[str] = None
    auth: Dict[str, Any] = field(default_factory=dict)
    env: Dict[str, str] = field(default_factory=dict)
    extras: Dict[str, Any] = field(default_factory=dict)
