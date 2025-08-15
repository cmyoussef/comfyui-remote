import unittest
from pathlib import Path
from tests.utils.bootstrap import add_src_to_path
add_src_to_path()

from comfyui_remote.nodes.core.node_registry import NodeRegistry
from comfyui_remote.nodes.core.node_core_api import NodeCoreAPI
from comfyui_remote.workflows.loader.workflow_loader import WorkflowLoader
from comfyui_remote.workflows.compiler.comfy_compiler import ComfyCompiler

RES = Path(__file__).resolve().parents[2] / "tests" / "resources" / "workflows"

class TestStep06Compile(unittest.TestCase):
    def test_compile_txt2img(self):
        api = NodeCoreAPI(NodeRegistry())
        WorkflowLoader(api).load_from_json(str(RES / "txt2img.json"))
        payload = ComfyCompiler().compile(api.graph_ref(), None)
        self.assertIsInstance(payload, dict)
        node = next(iter(payload.values()))
        self.assertIn("class_type", node); self.assertIn("inputs", node)

if __name__ == "__main__":
    unittest.main(verbosity=2)
