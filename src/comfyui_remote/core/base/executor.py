from __future__ import annotations

import time
from typing import Protocol, Optional, Dict, Any


class IExecutor(Protocol):
    def prepare(self, graph, ctx) -> None: ...
    def submit(self, graph, ctx) -> str: ...
    def poll(self, handle_id: str) -> Dict[str, Any]: ...
    def collect(self, handle_id: str) -> Dict[str, Any]: ...
    def cancel(self, handle_id: str) -> None: ...


class ExecutorBase:
    """
    Shared 'execute' loop:
      - prepare() -> submit() -> subscribe(observer) -> poll() -> collect()
    Subclasses should:
      - implement prepare/submit/poll/collect/cancel
      - optionally expose 'connector()' that has subscribe(prompt_id, observer).
    """

    def __init__(self) -> None:
        self._observer = None
        self._debug = False

    # ---- optional wiring ----
    def set_observer(self, obs) -> None:
        """Observer must have an 'update(event_dict)' method. Stored for WS subscription."""
        self._observer = obs

    def enable_debug(self, on: bool = True) -> None:
        self._debug = bool(on)

    def connector(self):
        """
        Optional: return a connector that supports subscribe(prompt_id, observer).
        Subclasses may override; default returns None.
        """
        return None

    # ---- abstract-ish: subclasses must implement the following ----
    def prepare(self, graph, ctx) -> None:
        raise NotImplementedError

    def submit(self, graph, ctx) -> str:
        raise NotImplementedError

    def poll(self, handle_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    def collect(self, handle_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    def cancel(self, handle_id: str) -> None:
        raise NotImplementedError

    # ---- public one-shot execution driver ----
    def execute(self, graph, ctx) -> Dict[str, Any]:
        """
        Drive the whole run and return a normalized dict:
            {
              "handle_id": <prompt_id>,
              "state": "success" | "error" | "timeout",
              "artifacts": <dict from collect() or {}>,
              "status": <last status dict>,
            }
        """
        # default timeout/backoff; if ctx provides, use it
        timeout_s = getattr(ctx, "timeout_s", 60.0)
        interval_s = getattr(ctx, "poll_interval_s", 0.25)

        # 1) prepare & submit
        self.prepare(graph, ctx)
        handle_id = self.submit(graph, ctx)

        # 2) subscribe progress observer if we have both connector & observer
        conn = self.connector()
        if conn is not None and self._observer is not None:
            try:
                conn.subscribe(handle_id, self._observer)
            except Exception:
                # non-fatal: just continue without live WS updates
                pass

        # 3) poll until done
        t0 = time.time()
        last_status: Dict[str, Any] = {}
        while time.time() - t0 < timeout_s:
            st = self.poll(handle_id) or {}
            last_status = st
            state = st.get("state")
            if state in ("success", "error"):
                break
            time.sleep(interval_s)
        else:
            # timeout
            try:
                self.cancel(handle_id)
            except Exception:
                pass
            return {"handle_id": handle_id, "state": "timeout", "artifacts": {}, "status": last_status}

        # 4) collect artifacts
        try:
            artifacts = self.collect(handle_id) or {}
        except Exception:
            artifacts = {}

        return {"handle_id": handle_id, "state": last_status.get("state", ""), "artifacts": artifacts, "status": last_status}
