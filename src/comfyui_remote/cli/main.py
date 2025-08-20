from __future__ import annotations
import argparse

from .run_cmd import RunCommand
from .validate_cmd import ValidateCommand

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="comfy", description="ComfyUI Remote CLI")
    sp = p.add_subparsers(dest="cmd", required=True)

    # run
    run = RunCommand()
    pr = sp.add_parser("run", help="Run a workflow")
    RunCommand.configure(pr)
    pr.set_defaults(_cmd=run.run)

    # validate
    val = ValidateCommand()
    pv = sp.add_parser("validate", help="Validate a workflow")
    ValidateCommand.configure(pv)
    pv.set_defaults(_cmd=val.run)

    # optional GUI subcommand (best-effort)
    try:
        from .gui_cmd import GuiCommand
        gui = GuiCommand()
        gui.build_parser(sp)  # adds 'gui'
    except Exception:
        pass

    return p

def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    if hasattr(args, "_cmd"):
        return args._cmd(args)
    if hasattr(args, "func"):  # for the GUI command style
        args.func(args)
        return 0
    parser.print_help()
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
