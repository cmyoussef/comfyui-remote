import unittest
from pathlib import Path

from comfyui_remote.connectors.comfy.server_manager import ComfyServerManager
from comfyui_remote.workflows.manager.workflow_manager import WorkflowManager
from tests.utils.bootstrap import add_src_to_path
add_src_to_path()

from comfyui_remote.nodes.core.node_registry import NodeRegistry
from comfyui_remote.nodes.core.node_core_api import NodeCoreAPI
from comfyui_remote.workflows.loader.workflow_loader import WorkflowLoader
from comfyui_remote.config.config_manager import ConfigManager
RES = Path(__file__).resolve().parents[2] / "tests" / "resources" / "workflows"

class TestStep05UpdateParams(unittest.TestCase):
    def test_override_steps(self):
        wm = WorkflowManager()
        wm.load(str(RES / "txt2img.json"))

        # Set a runtime override on all KSampler nodes
        hits = wm.set_param_by_type("KSampler", {"steps": 3})
        self.assertGreaterEqual(hits, 1)

        # Optional: assert compiled payload carries the override
        payload = wm.export_prompt()
        ks = [n for n in payload.values() if n["class_type"] == "KSampler"]
        self.assertTrue(any(n["inputs"].get("steps") == 3 for n in ks))


if __name__ == "__main__":
    unittest.main(verbosity=2)
