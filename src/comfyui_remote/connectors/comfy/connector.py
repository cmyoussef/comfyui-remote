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
        self._rest = ComfyRestClient(self._base)
        self._client_id: Optional[str] = None
        self._ws: Optional[ComfyWsClient] = None
        self._obs: Optional[IProgressObserver] = None
        self._last_status: Dict[str, Any] = {}

    def _ws_url(self, client_id: str) -> str:
        u = urllib.parse.urlparse(self._base)
        scheme = "wss" if u.scheme == "https" else "ws"
        return f"{scheme}://{u.hostname}:{u.port or (443 if scheme=='wss' else 80)}/ws?clientId={client_id}"

    def open(self) -> None:
        # nop until subscribe, ensured by post_workflow
        pass

    def post_workflow(self, payload: Dict[str, Any], client_id: str) -> str:
        self._client_id = client_id
        print('payload', payload)
        print('client_id', client_id)

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
        hist = self._rest.get(f"/history/{prompt_id}")
        outputs = {}
        try:
            nodes = list((hist.get(prompt_id) or {}).get("outputs", {}).items())
            for node_id, node_out in nodes:
                images = node_out.get("images") or []
                urls = []
                for im in images:
                    q = urllib.parse.urlencode({"filename": im["filename"], "subfolder": im["subfolder"], "type": im["type"]})
                    urls.append(f"{self._base}/view?{q}")
                outputs[node_id] = {"images": urls}
        except Exception:
            pass
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
