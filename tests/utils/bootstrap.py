# tests/utils/bootstrap.py
from __future__ import annotations
import os, sys, unittest
from pathlib import Path

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
