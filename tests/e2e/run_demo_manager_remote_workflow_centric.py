# tests/e2e/run_demo_manager_remote_workflow_centric.py
from __future__ import annotations

import random
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
if str(SRC) not in sys.path: sys.path.insert(0, str(SRC))
if str(REPO) not in sys.path: sys.path.insert(0, str(REPO))

from comfyui_remote.workflows.manager.workflow_manager import WorkflowManager
from comfyui_remote.connectors.comfy.server_manager import ComfyServerManager
from comfyui_remote.core.base.workflow import ExecutionContext

WF = REPO / "tests" / "resources" / "workflows" / "txt2img.json"


def main():
    # 1) Explicit, long output/input/user dirs
    base_runs = Path("../.comfy_outputs")
    (base_runs / "out").mkdir(parents=True, exist_ok=True)
    (base_runs / "in").mkdir(parents=True, exist_ok=True)
    (base_runs / "user").mkdir(parents=True, exist_ok=True)

    srv = ComfyServerManager()
    handle = srv.start({
        "input_dir": str((base_runs / "in").resolve()),
        "output_dir": str((base_runs / "out").resolve()),
        "user_dir": str((base_runs / "user").resolve()),
    })
    base = f"http://127.0.0.1:{handle.port}"
    print("[DEMO] Server:", base, "log:", handle.log_path)

    try:
        # 2) Manager workflow
        wm = WorkflowManager()  # uses default NodeRegistry/NodeCoreAPI/Loader/etc
        wm.load(WF)  # robust loader (editor JSON)
        # Adjust the node by human-friendly title (added by loader into _meta.title)
        changed = wm.set_param_by_title("Main_prompt", "text",
                                        "A photoreal glass bottle in an ocean, pyramids inside, cinematic lighting, cinematic")
        print("[DEMO] Title patches:", changed)

        seed = random.randint(0, 2 ** 31 - 1)
        changed = wm.set_param_by_type("KSampler", {"seed": seed})
        print("[DEMO] Type patches:", changed)

        # 3) Execute remotely against the server we just started
        wm.set_execution_context(ExecutionContext(mode="remote", base_url=base))
        wm.save_prompt(base_runs / "prompt.json")
        result = wm.execute()

        print("[DEMO] STATE:", result.get("state"))
        print("[DEMO] ARTIFACTS:", result.get("artifacts"))
        # In remote mode, wm.execute() returns view URLs in artifacts (when available).
        # You can also use the connector directly to fetch bytes if you want to save a copy elsewhere.

        # Give filesystem a breath (Windows indexing)
        time.sleep(0.2)

        print("[DEMO] Done.")
        return 0
    finally:
        # pass
        try:
            srv.stop()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
