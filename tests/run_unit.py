# tests/run_unit.py
from __future__ import annotations
import argparse, sys, time
from pathlib import Path

def _bootstrap():
    repo = Path(__file__).resolve().parents[1]
    src = repo / "src"
    if str(src) not in sys.path: sys.path.insert(0, str(src))
    if str(repo) not in sys.path: sys.path.insert(0, str(repo))

class InlineReporter:
    def pytest_runtest_logstart(self, nodeid, location):
        print(f"▶ START {nodeid}", flush=True)

    def pytest_runtest_logreport(self, report):
        if report.when != "call":
            return
        dur_ms = int(getattr(report, "duration", 0) * 1000)
        if report.passed:
            print(f"  ✓ PASS {report.nodeid}  ({dur_ms} ms)", flush=True)
        elif report.failed:
            print(f"  ✗ FAIL {report.nodeid}  ({dur_ms} ms)", flush=True)
        elif report.skipped:
            print(f"  ↷ SKIP {report.nodeid}  ({dur_ms} ms)", flush=True)

def main() -> int:
    _bootstrap()
    try:
        import pytest  # type: ignore
    except ImportError:
        print("pytest not installed. pip install pytest")
        return 1

    unit_dir = str(Path(__file__).parent / "unit")
    print("\n[unit] ===============================================")
    print(f"[unit] Python: {sys.executable}")
    print(f"[unit] Suite:  {unit_dir}")
    print("[unit] ===============================================\n", flush=True)

    # Very verbose with prints shown
    pytest_args = [unit_dir, "-vv", "-s", "-r", "a"]

    t0 = time.time()
    code = pytest.main(pytest_args, plugins=[InlineReporter()])
    dur = time.time() - t0
    print(f"\n[unit] Completed in {dur:.2f}s with exit code {code}")
    return code

if __name__ == "__main__":
    raise SystemExit(main())
