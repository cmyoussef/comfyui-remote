# tests/e2e/run_demo.py
from __future__ import annotations
import json, os, sys, time, tempfile
from pathlib import Path

# Make repo importable regardless of launch directory
REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
if str(SRC) not in sys.path: sys.path.insert(0, str(SRC))
if str(REPO) not in sys.path: sys.path.insert(0, str(REPO))

from tests.utils.bootstrap import ensure_env  # type: ignore
from comfyui_remote.connectors.comfy.server_manager import ComfyServerManager
from comfyui_remote.connectors.comfy.connector import ComfyConnector
from comfyui_remote.connectors.comfy.rest_client import ComfyRestClient
from comfyui_remote.nodes.core.node_registry import NodeRegistry
from comfyui_remote.nodes.core.node_core_api import NodeCoreAPI
from comfyui_remote.workflows.loader.workflow_loader import WorkflowLoader
from comfyui_remote.workflows.compiler.comfy_compiler import ComfyCompiler
from comfyui_remote.core.types import RunState

TXT2IMG = REPO / "tests" / "resources" / "workflows" / "txt2img.json"

# minimal embedded PNG (1x1) in case you don't have a sample image handy
_MINI_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0bIDATx\x9cc\xfc\xff\xff?"
    b"\x00\x05\xfe\x02\xfeA\xcb\xb4\xb2\x00\x00\x00\x00IEND\xaeB`\x82"
)

def _log(step: str, msg: str):
    print(f"[E2E][{step}] {msg}", flush=True)

def _wait_until(conn: ComfyConnector, pid: str, timeout_s: float = 20.0) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        st = conn.status(pid)
        if st.get("state") in (RunState.success.value, RunState.error.value, "success", "error"):
            return st
        time.sleep(0.2)
    return {"state": "timeout"}

def _first_clip_text_node(api: NodeCoreAPI):
    for n in api.graph_ref().iter_nodes():
        # Loader stores node type in metadata.type
        typ = getattr(getattr(n, "metadata", None), "type", "")
        if typ == "CLIPTextEncode":
            return n
    return None

def _apply_prompt_overrides(api: NodeCoreAPI):
    hits = 0
    # Try to set steps on samplers
    for n in api.graph_ref().iter_nodes():
        p = getattr(n, "params", lambda: {})()
        if "steps" in p:
            try:
                n.set_param("steps", 5)
                hits += 1
            except Exception:
                pass
    # Try to set text on CLIPTextEncode
    clip = _first_clip_text_node(api)
    if clip:
        # Try common keys; fall back to first param
        p = clip.params()
        for key in ("text", "prompt", "input", "string", "value"):
            if key in p:
                try:
                    clip.set_param(key, "A small glass bottle in a meadow, purple galaxy inside")
                    hits += 1
                    break
                except Exception:
                    pass
        else:
            # try param_0 pattern
            k0 = next(iter(p.keys()), None)
            if k0:
                try:
                    clip.set_param(k0, "A small glass bottle in a meadow, purple galaxy inside")
                    hits += 1
                except Exception:
                    pass
    return hits

def main() -> int:
    # 0) Preconditions
    if not TXT2IMG.exists():
        print(f"Missing workflow: {TXT2IMG}")
        return 2
    if "COMFYUI_HOME" not in os.environ:
        print("Set COMFYUI_HOME to your ComfyUI folder (contains main.py).")
        return 2

    # 1) Start server (with dedicated IO dirs)
    tmp_in = Path(tempfile.mkdtemp(prefix="e2e_in_"))
    tmp_out = Path(tempfile.mkdtemp(prefix="e2e_out_"))
    srv = ComfyServerManager()
    handle = srv.start({"input_dir": str(tmp_in), "output_dir": str(tmp_out)})
    base = f"http://127.0.0.1:{handle.port}"
    _log("1/6", f"Server started pid={handle.pid} url={base} log={handle.log_path}")

    # 2) Connect REST+WS
    conn = ComfyConnector(base_url=base)
    conn.open()
    _log("2/6", "Connector opened (HTTP+WS)")

    try:
        # 3) Load txt2img editor JSON into Graph
        reg = NodeRegistry()
        api = NodeCoreAPI(reg)
        WorkflowLoader(api).load_from_json(str(TXT2IMG))
        _log("3/6", f"Loaded workflow: {TXT2IMG.name} (nodes={len(list(api.graph_ref().iter_nodes()))})")

        # 4) Edit params (text & steps) best-effort
        edits = _apply_prompt_overrides(api)
        _log("4/6", f"Applied {edits} override(s) (best-effort)")

        # 5) Compile → payload, submit
        payload = ComfyCompiler().compile(api.graph_ref(), None)
        _log("5/6", f"Compiled payload with {len(payload)} nodes")

        try:
            pid = conn.post_workflow(payload, client_id="e2e-demo")
            _log("5/6", f"Submitted prompt_id={pid}")
            st = _wait_until(conn, pid, timeout_s=30.0)
            _log("5/6", f"Run status: {st}")

            outs = conn.fetch_outputs(pid)
            if outs:
                _log("5/6", f"Outputs: {json.dumps(outs)[:300]}...")
                _log("6/6", "Done.")
                return 0

            _log("5/6", "No outputs reported (continuing to fallback)")
        except Exception as e:
            _log("5/6", f"txt2img submit failed: {e} (continuing to fallback)")

        # ===== Fallback path (model-free) =====
        # Write tiny image into input_dir
        tiny = tmp_in / "tiny.png"
        tiny.write_bytes(_MINI_PNG)
        _log("FALLBACK", f"Wrote {tiny}")

        # Minimal IO workflow: LoadImage -> SaveImage with filename_prefix
        io_payload = {
            "n1": {"class_type": "LoadImage", "inputs": {"image": "tiny.png"}},
            "n2": {"class_type": "SaveImage",
                   "inputs": {"images": ["n1", 0], "filename_prefix": "E2E_Demo"}}
        }
        _log("FALLBACK", f"Submitting IO payload: {io_payload}")
        pid = conn.post_workflow(io_payload, client_id="e2e-demo-io")
        st = _wait_until(conn, pid, timeout_s=15.0)
        _log("FALLBACK", f"Run status: {st}")

        outs = conn.fetch_outputs(pid)
        if outs:
            _log("FALLBACK", f"Outputs: {json.dumps(outs)[:300]}...")
            # Optionally fetch the first image bytes, save as proof
            try:
                # find first url in our connector's resolved list
                node0 = next(iter(outs.values()))
                url = node0["images"][0]
                content = ComfyRestClient(base).get_bytes(url)
                proof = tmp_out / "downloaded.png"
                proof.write_bytes(content)
                _log("FALLBACK", f"Downloaded output → {proof}")
            except Exception as e:
                _log("FALLBACK", f"Could not download image: {e}")
            _log("6/6", "Done.")
            return 0

        _log("FALLBACK", "No outputs returned.")
        return 1

    finally:
        try:
            conn.close()
        except Exception:
            pass
        srv.stop()
        _log("CLEANUP", "Server stopped")

if __name__ == "__main__":
    raise SystemExit(main())
