# tests/e2e/run_demo_manager_remote.py
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tempfile
import uuid
from pathlib import Path

# Make src importable when run directly
REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
if str(SRC) not in sys.path: sys.path.insert(0, str(SRC))
if str(REPO) not in sys.path: sys.path.insert(0, str(REPO))

from comfyui_remote.connectors.comfy.server_manager import ComfyServerManager
from comfyui_remote.connectors.comfy.rest_client import ComfyRestClient
from comfyui_remote.workflows.loader.workflow_loader import WorkflowLoader
from comfyui_remote.nodes.core.node_registry import NodeRegistry
from comfyui_remote.nodes.core.node_core_api import NodeCoreAPI
from comfyui_remote.workflows.manager.workflow_manager import WorkflowManager
from comfyui_remote.services.validation_service import ValidationService
from comfyui_remote.services.progress_service import ProgressService
from comfyui_remote.services.config_manager import ConfigManager
from comfyui_remote.handlers.output.output_handler import OutputHandler
from comfyui_remote.core.base.workflow import ExecutionContext
from comfyui_remote.core.types import RunState


WF_DEFAULT = REPO / "tests" / "resources" / "workflows" / "txt2img.json"

def _log(step: str, msg: str) -> None:
    print(f"[DEMO][{step}] {msg}", flush=True)

def _patch_clip_text_in_api(api: NodeCoreAPI, new_text: str) -> int:
    """
    Update 'text' param on CLIPTextEncode nodes in the in-memory graph (loaded from editor JSON).
    Returns number of nodes updated.
    """
    hits = 0
    for n in api.graph_ref().iter_nodes():
        # loader sets node type to editor 'type' (e.g., 'CLIPTextEncode'), and maps widgets_values → params
        if n.meta().type == "CLIPTextEncode":
            params = n.params()
            # typical param key is 'text' (from widgets_values[0]); adjust if your loader uses a different key
            if "text" in params:
                n.set_param("text", new_text); hits += 1
    return hits

def _wait_until(manager: WorkflowManager, handle_id: str, timeout_s: float) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        st = manager.get_progress(handle_id) or {}
        state = st.get("state")
        if state in (RunState.success.value, RunState.error.value, "success", "error"):
            return st
        time.sleep(0.25)
    return {"state": "timeout"}

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Manager-centric E2E: start server → connect manager(remote) → load → patch text → (save) → execute → download image"
    )
    ap.add_argument("-w", "--workflow", default=str(WF_DEFAULT), help="Editor JSON path")
    ap.add_argument("-t", "--text", default="A photoreal glass bottle in a ocean, Pyramids of giza inside, cinematic lighting")
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--save-patched", action="store_true", help="Write patched editor JSON to a temp file")
    args = ap.parse_args()

    if "COMFYUI_HOME" not in os.environ:
        print("[DEMO] Please set COMFYUI_HOME to the folder containing ComfyUI/main.py")
        return 2

    wf_path = Path(args.workflow)
    if not wf_path.exists():
        print(f"[DEMO] Workflow not found: {wf_path}")
        return 2

    # 1) Start server (one-liner manager)
    input_dir  = Path(tempfile.mkdtemp(prefix="mgr_in_"))
    output_dir = Path(tempfile.mkdtemp(prefix="mgr_out_"))
    srv = ComfyServerManager()
    handle = srv.start({"input_dir": str(input_dir), "output_dir": str(output_dir)})
    base = f"http://127.0.0.1:{handle.port}"
    _log("1/8", f"Server started: {base}")

    try:
        # 2) Build manager bound to an API/graph
        reg = NodeRegistry()
        api = NodeCoreAPI(reg)
        wm = WorkflowManager(api, ValidationService(), ConfigManager(), ProgressService(), OutputHandler())

        # 3) Load editor JSON → in-memory graph
        WorkflowLoader(api).load_from_json(str(wf_path))
        _log("2/8", f"Loaded workflow: {wf_path.name}")

        # 4) Patch CLIP text in graph
        changed = _patch_clip_text_in_api(api, args.text)
        _log("3/8", f"Patched CLIPTextEncode nodes: {changed} changes")

        # 5) (Optional) save a patched editor JSON copy for auditing
        if args.save_patched:
            tmp_dir = Path(tempfile.mkdtemp(prefix="mgr_patched_"))
            patched = tmp_dir / "txt2img_patched.json"
            # Re-read original editor JSON, update the widgets_values text for each CLIPTextEncode
            ed = json.loads(wf_path.read_text("utf-8"))
            new_text = args.text
            for n in ed.get("nodes", []):
                if n.get("type") == "CLIPTextEncode":
                    ws = n.get("widgets_values", [])
                    if ws:
                        ws[0] = new_text
                        n["widgets_values"] = ws
            patched.write_text(json.dumps(ed, ensure_ascii=False, indent=2), encoding="utf-8")
            _log("4/8", f"Patched editor JSON saved → {patched}")

        # 6) Execute via manager in *remote* mode (connects to our running server)
        ctx = ExecutionContext(mode="remote", base_url=base)
        run = wm.execute(ctx)
        # `execute` should return a dict containing the 'handle_id' (prompt_id) or the final result.
        # If your implementation returns a handle, poll to completion:
        handle_id = run.get("handle_id") if isinstance(run, dict) else None
        if not handle_id:
            # If execute() returns an inline result, just show and exit
            _log("5/8", f"Execute() result: {run}")
            return 0

        _log("5/8", f"Submitted prompt_id={handle_id}")
        st = _wait_until(wm, handle_id, args.timeout)
        _log("6/8", f"Run status: {st}")

        if st.get("state") == "timeout":
            print("[DEMO] Run timed out.")
            return 3

        # 7) Fetch outputs via manager’s output handler/connector path. If not exposed,
        #    we can use the HTTP client directly as we did in the simpler demo.
        outs = wm.get_outputs(handle_id) if hasattr(wm, "get_outputs") else None
        if not outs:
            # fallback to raw connector REST call so demo remains functional
            outs = _fetch_outputs_via_rest(base, handle_id)
        if not outs:
            print("[DEMO] No outputs returned.")
            return 4

        # 8) Download first image
        img_url = _first_image_url(outs)
        if not img_url:
            print(f"[DEMO] Could not locate image URL in outputs: {outs}")
            return 5

        content = ComfyRestClient(base).get_bytes(img_url)
        proof = output_dir / f"manager_remote_output_{uuid.uuid4().hex[:4]}.png"
        proof.write_bytes(content)
        _log("7/8", f"Downloaded output → {proof}")

        _log("8/8", "Done.")
        return 0

    finally:
        try:
            srv.stop()
        except Exception:
            pass


def _fetch_outputs_via_rest(base: str, prompt_id: str) -> dict:
    """
    Minimal outputs fetcher compatible with Comfy’s /history endpoint schema.
    This mirrors the logic in ComfyConnector.fetch_outputs.
    """
    import requests
    r = requests.get(base + "/history", timeout=5)
    r.raise_for_status()
    data = r.json()
    if prompt_id not in data:
        return {}
    item = data[prompt_id]
    out = item.get("outputs", {})
    res = {}
    for nkey, nval in out.items():
        imgs = []
        for img in nval.get("images", []):
            # /view?filename=...&subfolder=...&type=output
            q = f"filename={img['filename']}&subfolder={img.get('subfolder','')}&type={img.get('type','')}"
            imgs.append(f"{base}/view?{q}")
        res[nkey] = {"images": imgs}
    return res


def _first_image_url(outs: dict) -> str | None:
    try:
        node = next(iter(outs.values()))
        if node and "images" in node and node["images"]:
            return node["images"][0]
    except Exception:
        pass
    return None


if __name__ == "__main__":
    raise SystemExit(main())
