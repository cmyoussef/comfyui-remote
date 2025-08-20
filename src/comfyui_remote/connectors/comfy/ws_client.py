"""Comfy WS."""
import json
import threading
from typing import Dict, Any, Optional, Callable
from websocket import WebSocketApp


class ComfyWsClient:
    def __init__(self, ws_url: str) -> None:
        self._ws_url = ws_url
        self._app: Optional[WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._subscribers: Dict[str, Callable[[Dict[str, Any]], None]] = {}

    def _on_message(self, _ws, message: str):
        try:
            data = json.loads(message)
        except Exception:
            return

        # Try to extract prompt_id from the message
        pid = None
        try:
            payload = data.get("data") or {}
            pid = payload.get("prompt_id") or data.get("prompt_id")
            if pid is not None:
                pid = str(pid)
        except Exception:
            pid = None

        # Targeted dispatch (if we have a subscriber for this prompt_id)
        if pid and pid in self._subscribers:
            try:
                self._subscribers[pid](data)
            except Exception:
                pass
            return

        # Fallback: broadcast to all
        for cb in list(self._subscribers.values()):
            try:
                cb(data)
            except Exception:
                pass

    def _on_open(self, _ws): pass
    def _on_close(self, _ws, *_): pass
    def _on_error(self, _ws, _err): pass

    def open(self) -> None:
        self._app = WebSocketApp(
            self._ws_url,
            on_message=self._on_message,
            on_open=self._on_open,
            on_close=self._on_close,
            on_error=self._on_error,
        )
        self._thread = threading.Thread(target=self._app.run_forever, daemon=True)
        self._thread.start()

    def subscribe(self, key: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        # 'key' is typically the prompt_id
        self._subscribers[str(key)] = callback

    def close(self) -> None:
        if self._app:
            try: self._app.close()
            except Exception: pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._app = None
        self._thread = None
        self._subscribers.clear()
