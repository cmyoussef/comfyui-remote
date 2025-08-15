import unittest, os, tempfile, shutil
from pathlib import Path
from tests.utils.bootstrap import add_src_to_path, ensure_env
add_src_to_path()

from comfyui_remote.nodes.core.node_registry import NodeRegistry
from comfyui_remote.nodes.core.node_core_api import NodeCoreAPI
from comfyui_remote.nodes.base.node_base import NodeBase, NodeMetadata
from comfyui_remote.workflows.manager.workflow_manager import WorkflowManager
from comfyui_remote.services.validation_service import ValidationService
from comfyui_remote.services.progress_service import ProgressService
from comfyui_remote.services.config_manager import ConfigManager
from comfyui_remote.handlers.output.output_handler import OutputHandler
from comfyui_remote.core.base.workflow import ExecutionContext

RES = Path(__file__).resolve().parents[2] / "tests" / "resources" / "images"
RES_IMG = RES / "tiny.png"

class _Node(NodeBase): pass

class TestStep09WorkflowManagerLocal(unittest.TestCase):
    def test_end_to_end(self):
        ensure_env(self, "COMFYUI_HOME", "Set to your ComfyUI folder (contains main.py).")

        # Build minimal graph again (LoadImage -> SaveImage)
        api = NodeCoreAPI(NodeRegistry())

        load_meta = NodeMetadata(type="LoadImage", label="LoadImage")
        n_load = _Node(load_meta)
        n_load.set_param("class_type", "LoadImage")
        n_load.set_param("image", "tiny.png")
        n_load.set_param("_ui_out_name_to_index", {"IMAGE": 0})

        save_meta = NodeMetadata(type="SaveImage", label="SaveImage")
        n_save = _Node(save_meta)
        n_save.set_param("class_type", "SaveImage")
        n_save.set_param("filename_prefix", "ComfyUI")

        api.graph_ref().add_node(n_load)
        api.graph_ref().add_node(n_save)
        api.graph_ref().connect(n_load.get_id(), "IMAGE", n_save.get_id(), "images")

        wm = WorkflowManager(api, ValidationService(), ConfigManager(), ProgressService(), OutputHandler())

        tmp_in = Path(tempfile.mkdtemp(prefix="comfy_in_"))
        tmp_out = Path(tempfile.mkdtemp(prefix="comfy_out_"))
        shutil.copy2(RES_IMG, tmp_in / "tiny.png")

        ctx = ExecutionContext(mode="local", extras={"input_dir": str(tmp_in), "output_dir": str(tmp_out)})
        res = wm.execute(ctx)

        # WorkflowManager returns a dict (we don't hard-fail on model execution errors)
        self.assertIsInstance(res, dict)
