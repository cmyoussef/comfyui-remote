import json, os, shutil, tempfile, time, unittest
from pathlib import Path
from tests.utils.bootstrap import add_src_to_path, ensure_env
add_src_to_path()

from comfyui_remote.nodes.core.node_registry import NodeRegistry
from comfyui_remote.nodes.core.node_core_api import NodeCoreAPI
from comfyui_remote.workflows.loader.workflow_loader import WorkflowLoader
from comfyui_remote.executors.local.local_executor import LocalExecutor
from comfyui_remote.core.base.workflow import ExecutionContext

RES_IMG = Path(__file__).resolve().parents[2] / "tests" / "resources" / "images" / "tiny.png"

def _write_min_prompt_json(path: Path):
    """
    Minimal *prompt JSON* (not editor JSON):
      LoadImage -> SaveImage
    """
    payload = {
        "n1": {"class_type": "LoadImage", "inputs": {"image": "tiny.png"}},
        "n2": {"class_type": "SaveImage", "inputs": {"filename_prefix": "ComfyUI", "images": ["n1", 0]}},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

class TestStep07SubmitLocal(unittest.TestCase):
    def test_submit(self):
        ensure_env(self, "COMFYUI_HOME", "Set to your ComfyUI folder (contains main.py).")

        # Prepare IO dirs and resource image
        tmp_in = Path(tempfile.mkdtemp(prefix="comfy_in_"))
        tmp_out = Path(tempfile.mkdtemp(prefix="comfy_out_"))
        shutil.copy2(RES_IMG, tmp_in / "tiny.png")

        # Build a minimal *prompt JSON*, then load via WorkflowLoader
        api = NodeCoreAPI(NodeRegistry())
        wf_dir = Path(tempfile.mkdtemp(prefix="wf_"))
        wf = wf_dir / "io_min.prompt.json"
        _write_min_prompt_json(wf)
        WorkflowLoader(api).load_from_json(str(wf))

        # Execute locally
        exe = LocalExecutor()
        ctx = ExecutionContext(mode="local", extras={"input_dir": str(tmp_in), "output_dir": str(tmp_out)})
        exe.prepare(api.graph_ref(), ctx)
        prompt_id = exe.submit(api.graph_ref(), ctx)

        # Poll until done
        for _ in range(50):  # ~10s at 0.2s each
            st = exe.poll(prompt_id)
            if st.get("state") in ("success", "error"):
                break
            time.sleep(0.2)

        outs = exe.collect(prompt_id)
        self.assertTrue(outs, "No outputs collected")

        # Output dir should have an image produced by SaveImage
        produced = list(tmp_out.glob("*.png"))
        self.assertTrue(produced, f"No .png outputs in {tmp_out}")
