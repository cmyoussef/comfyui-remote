# tests/e2e/run_demo_txt2img.py
from __future__ import annotations
import argparse, json, os, sys, time, tempfile, uuid
from pathlib import Path

# Repo bootstrap
REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
if str(SRC) not in sys.path: sys.path.insert(0, str(SRC))
if str(REPO) not in sys.path: sys.path.insert(0, str(REPO))

# Our module pieces
from comfyui_remote.connectors.comfy.server_manager import ComfyServerManager
from comfyui_remote.connectors.comfy.connector import ComfyConnector
from comfyui_remote.connectors.comfy.rest_client import ComfyRestClient
from comfyui_remote.nodes.core.node_registry import NodeRegistry
from comfyui_remote.nodes.core.node_core_api import NodeCoreAPI
from comfyui_remote.workflows.loader.workflow_loader import WorkflowLoader
from comfyui_remote.workflows.compiler.comfy_compiler import ComfyCompiler
from comfyui_remote.core.types import RunState

WF_DEFAULT = REPO / "tests" / "resources" / "workflows" / "txt2img.json"

def _log(step: str, msg: str):
    print(f"[DEMO][{step}] {msg}", flush=True)

def _patch_clip_text(editor: dict, node_id: int, new_text: str) -> bool:
    nodes = editor.get("nodes", [])
    for n in nodes:
        if n.get("id") == node_id and n.get("type") == "CLIPTextEncode":
            w = n.get("widgets_values", [])
            if w:
                w[0] = new_text
                n["widgets_values"] = w
                return True
    return False

def _wait_until(conn: ComfyConnector, pid: str, timeout_s: float = 120.0) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        st = conn.status(pid)
        s = st.get("state", "")
        if s in (RunState.success.value, RunState.error.value, "success", "error"):
            return st
        time.sleep(0.25)
    return {"state": "timeout"}

def main() -> int:
    ap = argparse.ArgumentParser(
        description="E2E: start server → open txt2img editor JSON → set CLIPTextEncode(id=6) text → compile → run → save"
    )
    ap.add_argument("--workflow", "-w", default=str(WF_DEFAULT), help="Editor JSON path (txt2img.json)")
    ap.add_argument("--text", "-t", help="New text for CLIPTextEncode (id=6) widgets_values[0]", default='A small glass bottle in a meadow, Pyramid of giza inside')
    ap.add_argument("--timeout", type=float, default=120.0, help="Run timeout seconds")
    ap.add_argument("--prefix", default="E2E_DEMO", help="filename_prefix fallback if loader/compiler needs it")
    args = ap.parse_args()

    if "COMFYUI_HOME" not in os.environ:
        print("[DEMO] Please set COMFYUI_HOME to the folder containing ComfyUI/main.py")
        return 2

    wf_path = Path(args.workflow)
    if not wf_path.exists():
        print(f"[DEMO] Workflow not found: {wf_path}")
        return 2

    # 1) Read and patch editor JSON
    editor = json.loads(wf_path.read_text(encoding="utf-8"))
    patched = _patch_clip_text(editor, node_id=6, new_text=args.text)
    if not patched:
        print("[DEMO] Could not find CLIPTextEncode node with id=6 in the editor JSON.")
        return 2

    tmp_dir = Path(tempfile.mkdtemp(prefix="demo_txt2img_"))
    wf_patched = tmp_dir / "txt2img_patched.json"
    wf_patched.write_text(json.dumps(editor, ensure_ascii=False, indent=2), encoding="utf-8")
    _log("1/7", f"Patched workflow saved → {wf_patched}")

    # 2) Start server with ephemeral IO
    input_dir = Path(tempfile.mkdtemp(prefix="demo_in_"))
    output_dir = Path(tempfile.mkdtemp(prefix="demo_out_"))
    srv = ComfyServerManager()
    handle = srv.start({"input_dir": str(input_dir), "output_dir": str(output_dir)})
    base = f"http://127.0.0.1:{handle.port}"
    _log("2/7", f"Server: pid={handle.pid} url={base} log={handle.log_path}")

    # 3) Build graph from editor JSON (module loader), compile payload
    reg = NodeRegistry()
    api = NodeCoreAPI(reg)
    WorkflowLoader(api).load_from_json(str(wf_patched))
    _log("3/7", f"Loaded workflow: {wf_patched.name} → nodes={sum(1 for _ in api.graph_ref().iter_nodes())}")

    payload = ComfyCompiler().compile(api.graph_ref(), None)
    # Sanity: ensure SaveImage has a filename_prefix (newer Comfy requires it)
    # If your compiler already does this from widgets_values, this is just a safety net.
    for k, node in payload.items():
        if node.get("class_type") == "SaveImage":
            node.setdefault("inputs", {}).setdefault("filename_prefix", args.prefix)
    _log("4/7", f"Compiled prompt: {len(payload)} nodes")

    # 4) Connect
    conn = ComfyConnector(base_url=base)
    conn.open()
    _log("5/7", "Connector opened (HTTP+WS)")

    try:
        # Optional: observe WS 'executing' messages
        def _obs(e):
            if isinstance(e, dict) and e.get("type") == "executing":
                d = e.get("data", {})
                _log("WS", f"executing: node={d.get('node')} prompt={d.get('prompt_id')}")
        client_id = "demo-" + uuid.uuid4().hex[:8]

        # 5) Submit & wait
        pid = conn.post_workflow(payload, client_id=client_id)
        conn.subscribe(pid, type("Obs", (), {"update": staticmethod(_obs)}))
        _log("6/7", f"Submitted prompt_id={pid}")

        st = _wait_until(conn, pid, timeout_s=args.timeout)
        _log("6/7", f"Run status: {st}")

        if st.get("state") == "timeout":
            print("[DEMO] Run timed out.")
            return 3

        # 6) Fetch outputs & download first image
        outs = conn.fetch_outputs(pid)
        if not outs:
            print("[DEMO] No outputs returned by server.")
            return 4

        try:
            node = next(iter(outs.values()))
            url = node["images"][0]
            content = ComfyRestClient(base).get_bytes(url)
            proof = output_dir / "txt2img_output.png"
            proof.write_bytes(content)
            _log("7/7", f"Downloaded output → {proof}")
            return 0
        except Exception as e:
            print(f"[DEMO] Could not download image: {e}\nOutputs: {json.dumps(outs)[:400]}...")
            return 5

    finally:
        try:
            conn.close()
        except Exception:
            pass
        # Stop the server we started
        try:
            ComfyServerManager().stop()
        except Exception:
            pass
        _log("CLEANUP", "Server stopped")

if __name__ == "__main__":
    raise SystemExit(main())
