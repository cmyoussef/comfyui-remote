"""Enums and aliases."""
from enum import Enum

class RunState(str, Enum):
    queued = "queued"
    running = "running"
    success = "success"
    error = "error"
    interrupted = "interrupted"
