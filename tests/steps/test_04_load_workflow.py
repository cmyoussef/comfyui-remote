import unittest
from pathlib import Path
from tests.utils.bootstrap import add_src_to_path
add_src_to_path()

from comfyui_remote.nodes.core.node_registry import NodeRegistry
from comfyui_remote.nodes.core.node_core_api import NodeCoreAPI
from comfyui_remote.workflows.loader.workflow_loader import WorkflowLoader

RES = Path(__file__).resolve().parents[2] / "tests" / "resources" / "workflows"

class TestStep04LoadWorkflow(unittest.TestCase):
    def test_load_txt2img(self):
        api = NodeCoreAPI(NodeRegistry())
        WorkflowLoader(api).load_from_json(str(RES / "txt2img.json"))
        nodes = list(api.graph_ref().iter_nodes())
        print(nodes)
        self.assertGreater(len(nodes), 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
