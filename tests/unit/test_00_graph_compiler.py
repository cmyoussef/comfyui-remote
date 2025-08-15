import unittest
from tests.utils.bootstrap import add_src_to_path
add_src_to_path()

from comfyui_remote.nodes.core.node_core_api import NodeCoreAPI
from comfyui_remote.nodes.core.node_registry import NodeRegistry
from comfyui_remote.nodes.base.node_base import NodeBase
from comfyui_remote.workflows.compiler.comfy_compiler import ComfyCompiler

class DummyNode(NodeBase): pass

class TestGraphCompiler(unittest.TestCase):
    def test_graph_compile(self):
        reg = NodeRegistry(); reg.register("DummyNode", DummyNode)
        api = NodeCoreAPI(reg)
        a = api.create_node("DummyNode", label="A", foo=1)
        b = api.create_node("DummyNode", label="B")
        api.connect(a.get_id(), "out", b.get_id(), "in")
        payload = ComfyCompiler().compile(api.graph_ref(), None)
        self.assertIsInstance(payload, dict); self.assertEqual(len(payload), 2)

if __name__ == "__main__":
    unittest.main(verbosity=2)
