# tests/unit/test_02_ws_client.py
import unittest, json, time
from tests.utils.bootstrap import add_src_to_path
add_src_to_path()

from comfyui_remote.connectors.comfy import ws_client as mod
from comfyui_remote.connectors.comfy.ws_client import ComfyWsClient

# We keep a reference to the created ws so the test can emit after subscribe.
_TEST_LAST_WS = {"inst": None}

class _WS:
    def __init__(self, url, on_message=None, on_open=None, on_close=None, on_error=None, **kwargs):
        self._on_message = on_message or (lambda *a, **k: None)
        self._on_open = on_open or (lambda *a, **k: None)
        self._on_close = on_close or (lambda *a, **k: None)
        self._on_error = on_error or (lambda *a, **k: None)
        _TEST_LAST_WS["inst"] = self

    def run_forever(self):
        # Signal open; DO NOT emit messages here (to avoid race).
        self._on_open(self)
        # Block briefly so the test can subscribe and then explicitly emit.
        time.sleep(0.05)

    def close(self):
        self._on_close(self)

    # Helper so the test can emit at deterministic time
    def test_emit(self, payload: dict):
        self._on_message(self, json.dumps(payload))

class TestWSClient(unittest.TestCase):
    def test_subscribe_dispatch(self):
        mod.WebSocketApp = _WS
        got = []
        ws = ComfyWsClient("ws://x/ws?clientId=a")
        ws.open()
        ws.subscribe("P", lambda e: got.append(e))
        # Emit AFTER subscribe so the client can route it
        _TEST_LAST_WS["inst"].test_emit({"type": "executing", "data": {"prompt_id": "P", "node": "N"}})
        time.sleep(0.05)
        ws.close()
        self.assertTrue(got and got[0]["type"] == "executing")

if __name__ == "__main__":
    unittest.main(verbosity=2)
