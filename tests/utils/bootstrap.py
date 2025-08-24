# tests/utils/bootstrap.py
from __future__ import annotations

# tests/utils/bootstrap.py
import json
import os
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


@contextmanager
def maybe_local_comfy():
    """
    Context that starts a local Comfy server if COMFY_REMOTE_URL is not set.
    Yields (base_url, mgr_or_None). Caller is responsible for only using mgr.stop() if mgr is not None.
    """
    base = os.getenv("COMFY_REMOTE_URL")
    if base:
        yield base, None
        return

    # Fallback: spin up a local server if COMFYUI_HOME is available
    from comfyui_remote.connectors.comfy.server_manager import ComfyServerManager
    from .bootstrap import ensure_env  # reuse your existing ensure_env
    ensure_env(None, "COMFYUI_HOME", "Set to your ComfyUI folder (contains main.py).")

    mgr = ComfyServerManager()
    handle = mgr.start({})
    try:
        base = f"http://127.0.0.1:{handle.port}"
        yield base, mgr
    finally:
        mgr.stop()


def _apply_object_info_to_registry(reg, object_info: dict) -> None:
    """
    Be flexible about the API surface: try common entry points to push object_info into the registry.
    Adjusts to whatever naming your project uses.
    """
    try:
        # Preferred path: dedicated resolver
        from comfyui_remote.connectors.comfy.schema_resolver import SchemaResolver
        resolver = SchemaResolver(reg)
        for meth in ("prime", "load_from_object_info", "merge", "apply", "seed"):
            if hasattr(resolver, meth):
                getattr(resolver, meth)(object_info)
                return
    except Exception:
        pass

    # Try pushing directly to registry if it exposes a method
    for meth in ("prime_from_object_info", "apply_object_info", "load_from_object_info", "seed", "merge"):
        if hasattr(reg, meth):
            getattr(reg, meth)(object_info)
            return

    # Last resort: set an attribute that your registry may read from
    for attr in ("schema", "_schema", "object_info", "_object_info"):
        if hasattr(reg, attr):
            setattr(reg, attr, object_info)
            return

    raise RuntimeError("Could not apply object_info to NodeRegistry; please map method name used by your project.")


def prime_registry_or_skip(testcase, registry, schema_path_env: str = "COMFY_SCHEMA_JSON"):
    """
    Ensure NodeRegistry has named parameters by loading Comfy's object_info.
    Priority:
      1) COMFY_SCHEMA_JSON -> load from file (offline)
      2) COMFY_REMOTE_URL  -> fetch from remote server
      3) COMFYUI_HOME      -> start ephemeral local server and fetch
    If none available, skip the test.
    """
    # 1) schema file
    schema_file = os.getenv(schema_path_env)
    if schema_file and Path(schema_file).is_file():
        obj = _read_json(Path(schema_file))
        if obj:
            _apply_object_info_to_registry(registry, obj)
            return

    # 2/3) remote or local
    try:
        from comfyui_remote.connectors.comfy.rest_client import ComfyRestClient
    except Exception as e:
        testcase.skipTest(f"Cannot import ComfyRestClient: {e}")

    with maybe_local_comfy() as (base, mgr):
        if not base:
            testcase.skipTest(
                "No COMFY_SCHEMA_JSON, COMFY_REMOTE_URL, or COMFYUI_HOME; "
                "cannot prime NodeRegistry for editor JSON."
            )
        rc = ComfyRestClient(base)
        obj = rc.get("/object_info")
        if not isinstance(obj, dict) or not obj:
            testcase.skipTest("Failed to fetch /object_info; cannot prime NodeRegistry.")
        _apply_object_info_to_registry(registry, obj)


def add_src_to_path():
    """Ensure src/ is importable regardless of how the test is invoked."""
    root = Path(__file__).resolve().parents[2]  # repo root
    src = root / "src"
    if str(src) not in sys.path and src.exists():
        sys.path.insert(0, str(src))
    # Also ensure repo root on sys.path so `tests.*` imports work when running a single file
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def ensure_env(testcase: unittest.TestCase, var: str, hint: str):
    """Skip this test if env var is missing."""
    if not os.getenv(var):
        testcase.skipTest(f"Missing env '{var}'. {hint}")


def offscreen_qt():
    """Force Qt to render offscreen if not on a desktop session."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
