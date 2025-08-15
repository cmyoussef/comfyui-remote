"""Connector interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional, Protocol, Union

# Prefer the shared observer interface if present.
try:
    from .observer import IProgressObserver  # type: ignore
except Exception:
    class IProgressObserver(Protocol):  # fallback Protocol
        def update(self, event: dict) -> None: ...


ObserverLike = Union[IProgressObserver, Callable[[dict], None]]


class IConnector(ABC):
    """Abstract transport to a backend (e.g., ComfyUI)."""

    @abstractmethod
    def open(self) -> None:
        """Open underlying resources."""

    @abstractmethod
    def close(self) -> None:
        """Close underlying resources."""

    @abstractmethod
    def post_workflow(self, payload: dict, client_id: Optional[str] = None) -> str:
        """Submit a workflow and return a handle/prompt_id."""

    @abstractmethod
    def subscribe(self, job_id: str, observer: ObserverLike) -> None:
        """Subscribe to progress/events for a job."""

    @abstractmethod
    def status(self, job_id: str) -> dict:
        """Return job status/state."""

    @abstractmethod
    def fetch_outputs(self, job_id: str) -> dict:
        """Fetch job artifacts/outputs."""

    @abstractmethod
    def cancel(self, job_id: str) -> None:
        """Request cancellation of a job."""
