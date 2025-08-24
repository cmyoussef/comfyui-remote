import unittest
from tests.utils.bootstrap import add_src_to_path, ensure_env
add_src_to_path()

from comfyui_remote.connectors.comfy.server_manager import ComfyServerManager
from comfyui_remote.connectors.comfy.ws_client import ComfyWsClient

class TestStep02ConnectWS(unittest.TestCase):
    def test_open_close_ws(self):
        mgr = ComfyServerManager();
        handle = mgr.start({})
        ensure_env(self, "COMFYUI_HOME", "Set to your ComfyUI folder (contains main.py).")
        try:
            ws = ComfyWsClient(f"ws://127.0.0.1:{handle.port}/ws?clientId=step02")
            ws.open(); ws.close()
        finally:
            mgr.stop()

if __name__ == "__main__":
    unittest.main(verbosity=2)
