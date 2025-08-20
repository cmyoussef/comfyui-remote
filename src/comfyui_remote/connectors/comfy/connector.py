"""Comfy connector."""
import urllib.parse
from typing import Dict, Any, Optional
from ..session import SessionFactory
from .rest_client import ComfyRestClient
from .ws_client import ComfyWsClient
from ...core.base.connector import IConnector, IProgressObserver
from ...core.types import RunState


class ComfyConnector(IConnector):
    def __init__(self, base_url: str, auth: Optional[Dict[str, Any]] = None, timeout: float = 60.0) -> None:
        self._base = base_url.rstrip("/")
        self._auth = auth or {}
        self._timeout = timeout
        self._rest = ComfyRestClient(self._base, auth=self._auth, timeout=self._timeout)
        self._client_id: Optional[str] = None
        self._ws: Optional[ComfyWsClient] = None
        self._obs: Optional[IProgressObserver] = None
        self._last_status: Dict[str, Any] = {}

    def set_timeout(self, timeout: float) -> None:
        self._timeout = timeout
        self._rest.set_timeout(timeout)

    def _ws_url(self, client_id: str) -> str:
        u = urllib.parse.urlparse(self._base)
        scheme = "wss" if u.scheme == "https" else "ws"
        return f"{scheme}://{u.hostname}:{u.port or (443 if scheme=='wss' else 80)}/ws?clientId={client_id}"

    def open(self, client_id: Optional[str] = None) -> None:
        # nop until subscribe, ensured by post_workflow
        if client_id:
            self._client_id = client_id

    def post_workflow(self, payload: Dict[str, Any], client_id: str) -> str:
        self._client_id = client_id

        res = self._rest.post("/prompt", {"prompt": payload, "client_id": client_id})
        prompt_id = res.get("prompt_id")
        if not prompt_id:
            raise ValueError("No prompt_id returned")
        return prompt_id

    def subscribe(self, prompt_id: str, observer: IProgressObserver) -> None:
        self._obs = observer
        ws = ComfyWsClient(self._ws_url(self._client_id))
        def _dispatch(evt: Dict[str, Any]) -> None:
            t = evt.get("type")
            data = evt.get("data") or {}
            pid = data.get("prompt_id")
            if pid and pid != prompt_id:
                return
            # Track finish states
            if t == "execution_success":
                self._last_status = {"state": RunState.success.value, "data": data}
            elif t == "execution_error":
                self._last_status = {"state": RunState.error.value, "data": data}
            elif t == "execution_interrupted":
                self._last_status = {"state": RunState.interrupted.value, "data": data}
            elif t == "executing":
                node = data.get("node")
                if node is None:
                    # may be finishing; keep polling until success/error arrives
                    pass
                else:
                    self._last_status = {"state": RunState.running.value, "node": node}
            elif t == "progress":
                # value/max
                pass
            observer.update(evt)
        ws.open()
        ws.subscribe(prompt_id, _dispatch)
        self._ws = ws

    def status(self, prompt_id: str) -> Dict[str, Any]:
        return self._last_status or {"state": RunState.running.value}

    def fetch_outputs(self, prompt_id: str) -> Dict[str, Any]:
        """
        Handle both Comfy shapes:
          - GET /history/{id} -> {"prompt": {...}, "outputs": {...}}
          - GET /history      -> { "<id>": {"prompt": {...}, "outputs": {...}} }
        """
        outputs: Dict[str, Any] = {}
        entry: Dict[str, Any] = {}
        # 1) Try /history/{id}
        try:
            data = self._rest.get(f"/history/{prompt_id}") or {}
            if isinstance(data, dict):
                entry = data.get(prompt_id) if prompt_id in data else data
        except Exception:
            entry = {}
        # 2) Fallback to /history
        if not entry:
            try:
                hist = self._rest.get("/history") or {}
                entry = hist.get(prompt_id, {})
            except Exception:
                entry = {}
        # 3) Normalize view URLs
        try:
            for node_id, node_out in (entry.get("outputs") or {}).items():
                urls = []
                for im in (node_out.get("images") or []):
                    q = urllib.parse.urlencode({
                        "filename": im.get("filename", ""),
                        "subfolder": im.get("subfolder", ""),
                        "type": im.get("type", ""),
                    })
                    urls.append(f"{self._base}/view?{q}")
                outputs[node_id] = {"images": urls}
        except Exception:
            # keep it best‑effort
            return {}
        return outputs

    def cancel(self, prompt_id: str) -> None:
        try:
            self._rest.post("/interrupt", {})
        except Exception:
            pass

    def close(self) -> None:
        if self._ws:
            self._ws.close()
            self._ws = None
