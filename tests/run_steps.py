# tests/run_steps.py
from __future__ import annotations
import argparse, os, sys, time
from pathlib import Path

def _bootstrap():
    repo = Path(__file__).resolve().parents[1]
    src = repo / "src"
    if str(src) not in sys.path: sys.path.insert(0, str(src))
    if str(repo) not in sys.path: sys.path.insert(0, str(repo))

class InlineReporter:
    """Small inline pytest plugin to print one-line status per test."""
    def pytest_runtest_logstart(self, nodeid, location):
        print(f"▶ START {nodeid}", flush=True)

    def pytest_runtest_logreport(self, report):
        # Only print the 'call' phase outcome summary
        if report.when != "call":
            return
        dur_ms = int(getattr(report, "duration", 0) * 1000)
        if report.passed:
            print(f"  ✓ PASS {report.nodeid}  ({dur_ms} ms)", flush=True)
        elif report.failed:
            print(f"  ✗ FAIL {report.nodeid}  ({dur_ms} ms)", flush=True)
        elif report.skipped:
            print(f"  ↷ SKIP {report.nodeid}  ({dur_ms} ms)", flush=True)

    def pytest_sessionstart(self, session):
        print(f"[steps] Session start: {len(session.items)} tests discovered", flush=True)

    def pytest_sessionfinish(self, session, exitstatus):
        print(f"[steps] Session finished with exit status {exitstatus}", flush=True)

def _env_snapshot() -> str:
    keys = [
        "COMFYUI_HOME", "COMFY_INPUT_DIR", "COMFY_OUTPUT_DIR",
        "COMFY_PORT", "COMFY_REMOTE_URL"
    ]
    out = []
    for k in keys:
        v = os.environ.get(k, "")
        if v:
            out.append(f"  {k} = {v}")
    return "\n".join(out) if out else "  (no relevant env set)"

def main() -> int:
    _bootstrap()
    parser = argparse.ArgumentParser(description="Run all step tests (incremental bring-up)")
    parser.add_argument("--extra", nargs=argparse.REMAINDER, help="Extra args passed through to pytest")
    args = parser.parse_args()

    try:
        import pytest  # type: ignore
    except ImportError:
        print("pytest not installed. pip install pytest")
        return 1

    steps_dir = str(Path(__file__).parent / "steps")
    print("\n[steps] ===============================================")
    print(f"[steps] Python: {sys.executable}")
    print(f"[steps] Repo:   {Path(__file__).resolve().parents[1]}")
    print(f"[steps] Suite:  {steps_dir}")
    print("[steps] Env:\n" + _env_snapshot())
    print("[steps] ===============================================\n", flush=True)

    # Default to very verbose with prints shown
    pytest_args = [steps_dir, "-vv", "-s", "-r", "a"]

    if args.extra:
        pytest_args += args.extra

    t0 = time.time()
    code = pytest.main(pytest_args, plugins=[InlineReporter()])
    dur = time.time() - t0
    print(f"\n[steps] Completed in {dur:.2f}s with exit code {code}")
    return code

if __name__ == "__main__":
    raise SystemExit(main())
