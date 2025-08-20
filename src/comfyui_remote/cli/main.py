from __future__ import annotations
import argparse, json

from ..workflows.manager.workflow_manager import WorkflowManager
from ..core.base.workflow import ExecutionContext

def _load_params(path):
    if not path: return {}
    txt = open(path, "r", encoding="utf-8").read()
    try:
        return json.loads(txt)
    except Exception:
        try:
            import yaml  # optional
            return yaml.safe_load(txt) or {}
        except Exception:
            return {}

class RunCommand:
    @staticmethod
    def configure(p):
        p.add_argument("--workflow","-w", required=True, help="Path to Comfy editor or prompt JSON")
        p.add_argument("--params","-p", help="YAML/JSON overrides (simple name=value mapping)")
        p.add_argument("--mode", choices=("local","remote"), default="local")
        p.add_argument("--url", help="Remote base URL for --mode=remote")
        p.add_argument("--token", help="Auth token")
        p.add_argument("--verbose", action="store_true")

    def run(self, args) -> int:
        try:
            wm = WorkflowManager()  # NEW: defaults inside
            wm.load(args.workflow)
            overrides = _load_params(args.params)
            if overrides:
                wm.apply_params(overrides)

            ctx = ExecutionContext(
                mode=args.mode,
                base_url=args.url or "",
                auth={"token": args.token} if args.token else {},
            )
            result = wm.execute(ctx)
            if args.verbose:
                print("payload", wm.get_compiled_prompt(ctx))
                print("[run] result:", result)
            return 0
        except Exception as e:
            print("[run] error:", e)
            return 1

class ValidateCommand:
    @staticmethod
    def configure(p):
        p.add_argument("--workflow","-w", required=True, help="Path to Comfy editor or prompt JSON")
    def run(self, args) -> int:
        try:
            wm = WorkflowManager()  # defaults
            wm.load(args.workflow)
            errs = list(wm.validate())
            if errs:
                print("[validate] ERRORS:", errs)
                return 1
            print("[validate] OK")
            return 0
        except Exception as e:
            print("[validate] error:", e)
            return 1

def _build_parser():
    p = argparse.ArgumentParser(prog="comfy", description="ComfyUI Remote CLI")
    sp = p.add_subparsers(dest="cmd", required=True)

    pr = sp.add_parser("run", help="Run a workflow")
    RunCommand.configure(pr)
    pr.set_defaults(_cmd=RunCommand().run)

    pv = sp.add_parser("validate", help="Validate a workflow")
    ValidateCommand.configure(pv)
    pv.set_defaults(_cmd=ValidateCommand().run)

    return p

def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return args._cmd(args)
