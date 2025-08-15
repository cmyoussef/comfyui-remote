# tests/steps/test_03_post_prompt.py
import unittest, time, tempfile, shutil
from pathlib import Path
from tests.utils.bootstrap import add_src_to_path, ensure_env
add_src_to_path()

from comfyui_remote.connectors.comfy.server_manager import ComfyServerManager
from comfyui_remote.connectors.comfy.connector import ComfyConnector

RES = Path(__file__).resolve().parents[2] / "tests" / "resources"
RES_IMG = RES / "images" / "tiny.png"   # ensure this file exists

class _Obs:
    def __init__(self): self.events=[]
    def update(self, e): self.events.append(e)

class TestStep03PostPrompt(unittest.TestCase):
    def test_post_minimal_io(self):
        ensure_env(self, "COMFYUI_HOME", "Set to the folder containing ComfyUI/main.py")

        # temp IO roots and copy a tiny resource image into input dir
        tmp_in = Path(tempfile.mkdtemp(prefix="comfy_in_"))
        tmp_out = Path(tempfile.mkdtemp(prefix="comfy_out_"))
        tmp_img = tmp_in / "tiny.png"
        if not RES_IMG.exists():
            self.fail(f"Missing resource image: {RES_IMG}")
        shutil.copy2(RES_IMG, tmp_img)

        mgr = ComfyServerManager()
        handle = mgr.start({"input_dir": str(tmp_in), "output_dir": str(tmp_out)})

        base = f"http://127.0.0.1:{handle.port}"
        print(f"[step03] base={base} log={handle.log_path} input_dir={tmp_in} output_dir={tmp_out}")

        c = ComfyConnector(base_url=base)
        try:
            c.open()

            # Minimal, model-free graph: LoadImage -> SaveImage
            # IMPORTANT:
            # - Connections use ["node_key", OUTPUT_INDEX] (int).
            # - filename_prefix is required by your Comfy build.
            prompt = {
                "n1": {"class_type": "LoadImage", "inputs": {"image": "tiny.png"}},
                "n2": {
                    "class_type": "SaveImage",
                    "inputs": {
                        "images": ["n1", 0],
                        "filename_prefix": "remote_test"
                    }
                },
            }

            pid = c.post_workflow(prompt, client_id="step03")
            self.assertTrue(pid, "Server did not return a prompt_id")

            obs = _Obs(); c.subscribe(pid, obs)

            # poll for completion (success or error)
            for _ in range(50):  # ~10s
                st = c.status(pid)
                if st.get("state") in ("success", "error"):
                    print("[step03] status:", st)
                    break
                time.sleep(0.2)

            outs = c.fetch_outputs(pid)
            print("[step03] outputs:", outs)
            self.assertTrue(outs, "No outputs fetched")

        except Exception as e:
            try:
                log_tail = Path(handle.log_path).read_text(errors="ignore")[-3000:]
                print("\n--- Comfy log (tail) ---\n", log_tail)
            except Exception:
                pass
            self.fail(f"POST/subscribe failed: {e}")
        finally:
            c.close()
            mgr.stop()

if __name__ == "__main__":
    unittest.main(verbosity=2)
