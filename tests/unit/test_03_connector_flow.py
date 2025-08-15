# tests/unit/test_05_validation_output_handler.py
import unittest, tempfile, json
from pathlib import Path
from tests.utils.bootstrap import add_src_to_path
add_src_to_path()

from comfyui_remote.nodes.core.node_registry import NodeRegistry
from comfyui_remote.nodes.core.node_core_api import NodeCoreAPI
from comfyui_remote.workflows.loader.workflow_loader import WorkflowLoader
from comfyui_remote.services.validation_service import ValidationService
from comfyui_remote.handlers.output.output_handler import OutputHandler

RES = Path(__file__).resolve().parents[2] / "tests" / "resources" / "workflows"

class TestValidationOutput(unittest.TestCase):
    def test_validate_and_manifest(self):
        api = NodeCoreAPI(NodeRegistry())
        WorkflowLoader(api).load_from_json(str(RES / "zdepth.json"))
        errs = ValidationService().validate_graph(api.graph_ref())
        self.assertIsInstance(errs, list)

        tmp = Path(tempfile.mkdtemp())
        out = OutputHandler(root=str(tmp)).store("H", {"files": ["a.png"]})
        # Current handler uses 'manifest' (no underscore); fall back defensively.
        manifest_path = out.get("manifest") or out.get("_manifest")
        self.assertTrue(manifest_path, "manifest path not returned by OutputHandler")
        path = Path(manifest_path)
        self.assertTrue(path.exists())

        data = json.loads(path.read_text(encoding="utf-8"))
        # Minimal contract: the manifest at least echoes artifacts
        self.assertIn("files", data)
        # If your handler writes handle_id, also check it (optional)
        if "handle_id" in data:
            self.assertEqual(data["handle_id"], "H")

if __name__ == "__main__":
    unittest.main(verbosity=2)
