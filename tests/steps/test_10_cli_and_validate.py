import unittest, os, sys, json, tempfile, shutil
from pathlib import Path
from tests.utils.bootstrap import add_src_to_path, ensure_env
add_src_to_path()

RES = Path(__file__).resolve().parents[2] / "tests" / "resources" / "images"
RES_IMG = RES / "tiny.png"

def _write_min_editor_json(path: Path):
    data = {
        "nodes": [
            {
                "id": 1, "type": "LoadImage",
                "inputs": [],
                "outputs": [{"name": "IMAGE", "type": "IMAGE", "slot_index": 0}],
                "widgets_values": ["tiny.png", "image"]
            },
            {
                "id": 2, "type": "SaveImage",
                "inputs": [{"name": "images", "type": "IMAGE", "link": 1}],
                "outputs": [],
                "widgets_values": ["ComfyUI"]
            }
        ],
        "links": [[1, 1, 0, 2, 0, "IMAGE"]],
        "last_node_id": 2, "last_link_id": 1, "version": 0.4
    }
    path.write_text(json.dumps(data), encoding="utf-8")

class TestStep10CLI(unittest.TestCase):
    def test_validate(self):
        # Validate against txt2img (logic only)
        from comfyui_remote.cli.main import main
        wf = Path(__file__).resolve().parents[2] / "tests" / "resources" / "workflows" / "txt2img.json"
        old = sys.argv
        try:
            sys.argv = ["prog","validate","--workflow",str(wf)]
            code = main(); self.assertEqual(code, 0)
        finally:
            sys.argv = old

    def test_run_local_best_effort(self):
        ensure_env(self, "COMFYUI_HOME", "Set to your ComfyUI folder (contains main.py).")
        from comfyui_remote.cli.main import main

        # temp minimal editor JSON + IO dirs
        tmp_dir = Path(tempfile.mkdtemp(prefix="cli_min_"))
        wf = tmp_dir / "io_min.json"
        _write_min_editor_json(wf)

        tmp_in = Path(tempfile.mkdtemp(prefix="comfy_in_"))
        tmp_out = Path(tempfile.mkdtemp(prefix="comfy_out_"))
        shutil.copy2(RES_IMG, tmp_in / "tiny.png")

        old_env = dict(os.environ)
        os.environ["COMFY_INPUT_DIR"] = str(tmp_in)   # picked up by server manager if you wired it
        os.environ["COMFY_OUTPUT_DIR"] = str(tmp_out)

        old = sys.argv
        try:
            sys.argv = ["prog","run","--workflow",str(wf),"--mode","local","--verbose"]
            code = main(); self.assertEqual(code, 0)
        finally:
            sys.argv = old
            os.environ.clear(); os.environ.update(old_env)

if __name__ == "__main__":
    unittest.main(verbosity=2)
