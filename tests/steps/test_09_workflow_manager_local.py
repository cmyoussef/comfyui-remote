import json, shutil, tempfile, unittest
from pathlib import Path
from tests.utils.bootstrap import add_src_to_path, ensure_env
add_src_to_path()

from comfyui_remote.workflows.manager.workflow_manager import WorkflowManager
from comfyui_remote.core.base.workflow import ExecutionContext

RES_IMG = Path(__file__).resolve().parents[2] / "tests" / "resources" / "images" / "tiny.png"

def _write_min_prompt_json(path: Path):
    payload = {
        "1": {"class_type": "LoadImage", "inputs": {"image": "tiny.png"}},
        "2": {"class_type": "SaveImage", "inputs": {"filename_prefix": "ComfyUI", "images": ["1", 0]}},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

class TestStep09WorkflowManagerLocal(unittest.TestCase):
    def test_end_to_end(self):
        # ensure_env(self, "COMFYUI_HOME", "Set to your ComfyUI folder (contains main.py).")

        # IO dirs & resource
        tmp_in = Path(tempfile.mkdtemp(prefix="comfy_in_"))
        tmp_out = Path(tempfile.mkdtemp(prefix="comfy_out_"))
        shutil.copy2(RES_IMG, tmp_in / "tiny.png")

        # Minimal prompt JSON
        wf_dir = Path(tempfile.mkdtemp(prefix="wf_"))
        wf = wf_dir / "io_min.prompt.json"
        _write_min_prompt_json(wf)

        # Manager‑centric flow with defaults
        wm = WorkflowManager()
        wm.load(str(wf))
        wm.set_execution_context(
            ExecutionContext(mode="local", extras={"input_dir": str(tmp_in), "output_dir": str(tmp_out)})
        )
        res = wm.execute()

        self.assertIsInstance(res, dict)
        self.assertIn("state", res)

        produced = list(tmp_out.glob("*.png"))
        self.assertTrue(produced, f"No .png outputs in {tmp_out}")
