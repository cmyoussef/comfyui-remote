import unittest, os, tempfile, shutil, json
from pathlib import Path
from tests.utils.bootstrap import add_src_to_path, ensure_env
add_src_to_path()

from comfyui_remote.core.base.workflow import ExecutionContext
from comfyui_remote.nodes.core.node_registry import NodeRegistry
from comfyui_remote.nodes.core.node_core_api import NodeCoreAPI
from comfyui_remote.nodes.base.node_base import NodeBase, NodeMetadata
from comfyui_remote.executors.local.local_executor import LocalExecutor

RES = Path(__file__).resolve().parents[2] / "tests" / "resources" / "images"
RES_IMG = RES / "tiny.png"

class _Node(NodeBase): pass

class TestStep07SubmitLocal(unittest.TestCase):
    def test_submit(self):
        ensure_env(self, "COMFYUI_HOME", "Set to your ComfyUI folder (contains main.py).")

        # Build a minimal, model-free graph: LoadImage -> SaveImage
        api = NodeCoreAPI(NodeRegistry())

        load_meta = NodeMetadata(type="LoadImage", label="LoadImage")
        n_load = _Node(load_meta)
        n_load.set_param("class_type", "LoadImage")
        n_load.set_param("image", "tiny.png")
        # output index map for compiler
        n_load.set_param("_ui_out_name_to_index", {"IMAGE": 0})

        save_meta = NodeMetadata(type="SaveImage", label="SaveImage")
        n_save = _Node(save_meta)
        n_save.set_param("class_type", "SaveImage")
        n_save.set_param("filename_prefix", "ComfyUI")

        api.graph_ref().add_node(n_load)
        api.graph_ref().add_node(n_save)
        api.graph_ref().connect(n_load.get_id(), "IMAGE", n_save.get_id(), "images")

        # IO folders with the resource image
        tmp_in = Path(tempfile.mkdtemp(prefix="comfy_in_"))
        tmp_out = Path(tempfile.mkdtemp(prefix="comfy_out_"))
        tmp_in.mkdir(parents=True, exist_ok=True)
        tmp_out.mkdir(parents=True, exist_ok=True)
        print(RES_IMG, tmp_in / "tiny.png")
        shutil.copy2(RES_IMG, tmp_in / "tiny.png")

        ctx = ExecutionContext(mode="local", extras={"input_dir": str(tmp_in), "output_dir": str(tmp_out)})

        exe = LocalExecutor()
        exe.prepare(api.graph_ref(), ctx)
        handle = exe.submit(api.graph_ref(), ctx)
        self.assertTrue(handle)

        # We don't assert outputs; just ensure POST succeeded and status is accessible
        _ = exe.poll(handle)
        _ = exe.collect(handle)

if __name__ == "__main__":
    unittest.main(verbosity=2)
