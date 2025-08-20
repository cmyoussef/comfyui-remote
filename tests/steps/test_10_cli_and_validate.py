import os
import sys
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.utils.bootstrap import add_src_to_path, ensure_env
add_src_to_path()

# Reuse the same resource image you already have in tests/resources/images/
RES_IMG = Path(__file__).resolve().parents[2] / "tests" / "resources" / "images" / "tiny.png"


def _write_min_prompt_json(path: Path):
    """
    Minimal *prompt JSON* using NUMERIC keys and references.
    LoadImage ("1") -> SaveImage ("2")
    """
    payload = {
        "1": {
            "class_type": "LoadImage",
            "inputs": {
                "image": "tiny.png"
            }
        },
        "2": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "ComfyUI",
                "images": ["1", 0]   # <— IMPORTANT: numeric key, not "n1"
            }
        }
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class TestStep10CLI(unittest.TestCase):
    def test_validate(self):
        ensure_env(self, "COMFYUI_HOME", "Set to your ComfyUI folder (contains main.py).")
        from comfyui_remote.cli.main import main

        tmp_dir = Path(tempfile.mkdtemp(prefix="cli_min_"))
        wf = tmp_dir / "io_min.prompt.json"
        _write_min_prompt_json(wf)

        old = list(sys.argv)
        try:
            sys.argv = ["prog", "validate", "--workflow", str(wf)]
            code = main()
            self.assertEqual(code, 0)
        finally:
            sys.argv = old

    def test_run_local_best_effort(self):
        ensure_env(self, "COMFYUI_HOME", "Set to your ComfyUI folder (contains main.py).")
        from comfyui_remote.cli.main import main

        # Write a minimal *prompt JSON*
        tmp_dir = Path(tempfile.mkdtemp(prefix="cli_min_"))
        wf = tmp_dir / "io_min.prompt.json"
        _write_min_prompt_json(wf)

        # IO dirs + resource
        tmp_in = Path(tempfile.mkdtemp(prefix="comfy_in_"))
        tmp_out = Path(tempfile.mkdtemp(prefix="comfy_out_"))
        shutil.copy2(RES_IMG, tmp_in / "tiny.png")

        # Ensure the server started by the CLI picks these up
        old_env = dict(os.environ)
        os.environ["COMFY_INPUT_DIR"] = str(tmp_in)
        os.environ["COMFY_OUTPUT_DIR"] = str(tmp_out)

        old = list(sys.argv)
        try:
            sys.argv = ["prog", "run", "--workflow", str(wf), "--mode", "local", "--verbose"]
            code = main()
            # The CLI returns 0 on completion
            self.assertEqual(code, 0, "run should return 0 on completion")

            # Sanity check: an output PNG should exist
            outs = list(tmp_out.glob("*.png"))
            self.assertTrue(outs, f"No .png outputs found in {tmp_out}")
        finally:
            sys.argv = old
            os.environ.clear()
            os.environ.update(old_env)


if __name__ == "__main__":
    unittest.main(verbosity=2)
