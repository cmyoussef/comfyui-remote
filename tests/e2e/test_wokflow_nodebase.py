from pathlib import Path
from comfyui_remote.workflows.manager.workflow_manager import WorkflowManager
from comfyui_remote.nodes.base.node_base import NodeBase

RES = Path(__file__).resolve().parents[2] / "tests" / "resources" / "workflows"

def test_iteration_yields_nodebase():
    wm = WorkflowManager()
    wm.load(str(RES / "txt2img.json"))

    # iteration
    nodes = list(wm)
    assert len(nodes) > 0
    assert all(isinstance(n, NodeBase) for n in nodes)

    for n in wm:
        print(n)
        print(f'\t{n.params()}')

    # indexing by position
    first = wm[0]
    assert isinstance(first, NodeBase)

    # indexing by external id (if you know one)
    any_id = first.get_id()
    by_id = wm[any_id]
    assert by_id is first

    # membership
    assert first in wm
    assert any_id in wm
