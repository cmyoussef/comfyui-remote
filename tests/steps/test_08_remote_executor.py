import unittest, os
from pathlib import Path
from tests.utils.bootstrap import add_src_to_path
add_src_to_path()

from comfyui_remote.core.base.workflow import ExecutionContext
from comfyui_remote.nodes.core.node_registry import NodeRegistry
from comfyui_remote.nodes.core.node_core_api import NodeCoreAPI
from comfyui_remote.workflows.loader.workflow_loader import WorkflowLoader
from comfyui_remote.executors.remote.remote_executor import RemoteExecutor

RES = Path(__file__).resolve().parents[2] / "tests" / "resources" / "workflows"

class TestStep08Remote(unittest.TestCase):
    def test_remote_submit(self):
        base = os.getenv("COMFY_REMOTE_URL")
        if not base:
            self.skipTest("Set COMFY_REMOTE_URL to run this step.")
        api = NodeCoreAPI(NodeRegistry())
        WorkflowLoader(api).load_from_json(str(RES / "txt2img.json"))
        exe = RemoteExecutor()
        handle = exe.submit(api.graph_ref(), ExecutionContext(mode="remote", base_url=base))
        self.assertTrue(handle)

if __name__ == "__main__":
    unittest.main(verbosity=2)
