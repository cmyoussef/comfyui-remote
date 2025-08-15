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
        prompt_id = (data.get("data") or {}).get("prompt_id") or (data.get("prompt_id"))
        for cb in list(self._subscribers.values()):
            cb(data)

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
        self._subscribers[key] = callback

    def close(self) -> None:
        if self._app:
            try: self._app.close()
            except Exception: pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._app = None
        self._thread = None
        self._subscribers.clear()
