import unittest, os
from pathlib import Path
from tests.utils.bootstrap import add_src_to_path, ensure_env
add_src_to_path()

from comfyui_remote.connectors.comfy.server_manager import ComfyServerManager
from comfyui_remote.connectors.comfy.rest_client import ComfyRestClient

class TestStep01Server(unittest.TestCase):
    def test_start_healthcheck_stop(self):
        mgr = ComfyServerManager()
        ensure_env(self, "COMFYUI_HOME", "Set to your ComfyUI folder (contains main.py).")
        handle = mgr.start({})
        try:
            base = f"http://127.0.0.1:{handle.port}"
            data = ComfyRestClient(base).get("/object_info")
            self.assertIsInstance(data, dict)
        finally:
            mgr.stop()

if __name__ == "__main__":
    unittest.main(verbosity=2)
