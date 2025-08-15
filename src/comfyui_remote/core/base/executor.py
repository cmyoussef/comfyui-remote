"""Executor base classes."""
from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from typing import Any, Optional, TYPE_CHECKING

from .connector import IConnector

if TYPE_CHECKING:
    from .workflow import ExecutionContext


class IExecutor(ABC):
    """Strategy for executing a workflow."""

    @abstractmethod
    def prepare(self, graph: Any, ctx: "ExecutionContext") -> None:
        """Prep resources."""

    @abstractmethod
    def submit(self, graph: Any, ctx: "ExecutionContext") -> str:
        """Submit work and return a handle."""

    @abstractmethod
    def poll(self, handle_id: str) -> dict:
        """Return status for a handle."""

    @abstractmethod
    def collect(self, handle_id: str) -> dict:
        """Collect outputs for a handle."""

    @abstractmethod
    def cancel(self, handle_id: str) -> None:
        """Cancel a running handle."""

    @abstractmethod
    def execute(self, graph: Any, ctx: "ExecutionContext") -> dict:
        """Template method to run end-to-end."""


class ExecutorBase(IExecutor):
    """Template + helpers for executors."""

    def __init__(self) -> None:
        self._connector: Optional[IConnector] = None

    # ---- wiring helpers -------------------------------------------------

    def use_connector(self, connector: IConnector) -> None:
        """Attach a connector."""
        self._connector = connector

    # ---- overridables ---------------------------------------------------

    def prepare(self, graph: Any, ctx: "ExecutionContext") -> None:
        """Default no-op."""
        return None

    @abstractmethod
    def submit(self, graph: Any, ctx: "ExecutionContext") -> str:
        """Must return a handle/prompt_id."""
        raise NotImplementedError

    def poll(self, handle_id: str) -> dict:
        """Default delegates to connector."""
        if not self._connector:
            raise RuntimeError("No connector bound")
        return self._connector.status(handle_id)

    def collect(self, handle_id: str) -> dict:
        """Default delegates to connector."""
        if not self._connector:
            raise RuntimeError("No connector bound")
        return self._connector.fetch_outputs(handle_id)

    def cancel(self, handle_id: str) -> None:
        """Default delegates to connector."""
        if not self._connector:
            return
        self._connector.cancel(handle_id)

    # ---- template method ------------------------------------------------

    def execute(self, graph: Any, ctx: "ExecutionContext") -> dict:
        """Prepare → submit → poll → collect."""
        self.prepare(graph, ctx)
        handle = self.submit(graph, ctx)

        # Poll loop (tunable via env)
        max_iters = int(os.getenv("COMFY_POLL_ITERS", "50"))
        sleep_s = float(os.getenv("COMFY_POLL_SLEEP", "0.2"))

        status: dict = {"state": "submitted"}
        for _ in range(max_iters):
            try:
                status = self.poll(handle) or {}
            except Exception:
                # Be tolerant; continue polling briefly.
                status = status or {}
            state = (status.get("state") or status.get("status") or "").lower()
            if state in {"success", "error", "failed", "canceled", "cancelled"}:
                break
            time.sleep(sleep_s)

        try:
            outputs = self.collect(handle)
        except Exception:
            outputs = {}

        return {
            "handle_id": handle,
            "status": (status.get("state") or status.get("status") or "unknown"),
            "details": status,
            "outputs": outputs,
        }
