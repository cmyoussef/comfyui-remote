"""CLI entry point."""
from __future__ import annotations

import argparse
import sys

from .run_cmd import RunCommand
from .validate_cmd import ValidateCommand
from .templates_cmd import TemplatesCommand


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="comfy", description="ComfyUI Remote CLI")
    sp = p.add_subparsers(dest="cmd", required=True)

    pr = sp.add_parser("run", help="Run a workflow")
    RunCommand.configure(pr)

    pv = sp.add_parser("validate", help="Validate a workflow")
    ValidateCommand.configure(pv)

    pt = sp.add_parser("templates", help="List/show templates")
    TemplatesCommand.configure(pt)

    # Lazy GUI (avoid importing Qt if not used)
    sp.add_parser("gui", help="Launch GUI")

    return p


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "run":
        return RunCommand().run(args) or 0
    if args.cmd == "validate":
        return ValidateCommand().run(args) or 0
    if args.cmd == "templates":
        return TemplatesCommand().run(args) or 0
    if args.cmd == "gui":
        from .gui_cmd import GuiCommand  # lazy
        return GuiCommand().run(args) or 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
