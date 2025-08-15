import unittest
from pathlib import Path
from tests.utils.bootstrap import add_src_to_path
add_src_to_path()

from comfyui_remote.nodes.core.node_registry import NodeRegistry
from comfyui_remote.nodes.core.node_core_api import NodeCoreAPI
from comfyui_remote.workflows.loader.workflow_loader import WorkflowLoader

RES = Path(__file__).resolve().parents[2] / "tests" / "resources" / "workflows"

class TestLoaderParams(unittest.TestCase):
    def test_loader_and_override(self):
        api=NodeCoreAPI(NodeRegistry())
        WorkflowLoader(api).load_from_json(str(RES/"img2img.json"))
        hits=0
        for n in api.graph_ref().iter_nodes():
            if "denoise" in n.params(): n.set_param("denoise",0.25); hits+=1
        self.assertGreaterEqual(hits,1)

if __name__ == "__main__":
    unittest.main(verbosity=2)
