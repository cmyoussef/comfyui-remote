# tests/unit/test_01_rest_client.py
import unittest
from tests.utils.bootstrap import add_src_to_path
add_src_to_path()

from comfyui_remote.connectors.comfy.rest_client import ComfyRestClient
from comfyui_remote.connectors.session import SessionFactory

class _FakeResp:
    def __init__(self, url="http://x:1/ok", status=200, json=None, content=b"", reason="OK"):
        self.url = url
        self.status_code = status
        self._json = json
        self.content = content
        self.reason = reason
        self.text = ""  # compatibility

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json

class _FakeSession:
    def __init__(self):
        self.headers = {}
        self.timeout = None

    def get(self, url):
        if url.endswith("/object_info"):
            return _FakeResp(url=url, json={"ok": True})
        return _FakeResp(url=url, content=b"B")

    def post(self, url, json):
        return _FakeResp(url=url, json={"prompt_id": "pid-1"})

class TestRestClient(unittest.TestCase):
    def test_get_post(self):
        # Swap the factory to return our fake session
        SessionFactory.create = lambda self: _FakeSession()
        c = ComfyRestClient("http://x:1")
        self.assertEqual(c.get("/object_info")["ok"], True)
        self.assertEqual(c.post("/prompt", {"prompt": {}})["prompt_id"], "pid-1")
        self.assertEqual(c.get_bytes("http://x:1/view?f=1"), b"B")

if __name__ == "__main__":
    unittest.main(verbosity=2)
