"""ComfyUI Remote Launcher - Execute workflows remotely with CLI and GUI support."""

from __future__ import absolute_import

import argparse
import os
import sys

from comfyui_remote.job_runner import ExecuteWorkflow
from .dispatch import dispatch
from .logging_config import setup_logging

logger = setup_logging(debug=os.environ.get("DEBUG", False))


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Execute ComfyUI workflows remotely with CLI and GUI support"
    )

    parser.add_argument(
        "workflow",
        nargs="?",
        help="Path to the ComfyUI workflow JSON file",
    )

    parser.add_argument(
        "--gui", action="store_true", help="Launch the graphical user interface"
    )

    parser.add_argument(
        "--run",
        action="store_true",
        default=False,
        help="Submit to the farm",
    )

    parser.add_argument(
        "-b",
        "--batch-size",
        type=int,
        default=1,
        help="Number of times to execute the workflow (default: 1)",
    )

    parser.add_argument(
        "-F",
        "--frame-range",
        type=str,
        default=None,
        help="Frame range to process (e.g., '1001-1010'). If not specified, processes all images in input directory",
    )

    parser.add_argument(
        "--int-args",
        type=str,
        default=None,
        help='JSON string of integer parameters (e.g., \'{"param1": 10, "param2": 20}\')',
    )

    parser.add_argument(
        "--float-args",
        type=str,
        default=None,
        help='JSON string of float parameters (e.g., \'{"param1": 1.5, "param2": 2.0}\')',
    )

    parser.add_argument(
        "--str-args",
        type=str,
        default=None,
        help='JSON string of string parameters (e.g., \'{"param1": "value1", "param2": "value2"}\')',
    )

    parser.add_argument(
        "--no-farm",
        action="store_false",
        dest="on_farm",
        default=True,
        help="run the baking and rendering locally",
    )

    return parser.parse_args()


def launch_gui():
    """Launch the ComfyUI Remote GUI."""
    try:
        from .ui import gui
        from PyQt5 import QtWidgets
        try:
            import pipetheme.palettes
            pipetheme.palettes.setPalette("ivy")
        except ImportError:
            pass
        import signal

        # Allow ctrl-c to exit
        signal.signal(signal.SIGINT, signal.SIG_DFL)


        app = QtWidgets.QApplication(sys.argv)
        mainWindow = gui.comfyRemote_UI()
        mainWindow.show()
        sys.exit(app.exec_())
    except Exception:
        import traceback

        traceback.print_exc()
        return sys.exit(-1)


def main():
    """Run the Comfy Remote launcher.

    Returns:
        int: Non-zero value on failure, this will sys.exit using the
            value as an exit code.
    """
    args = parse_args()

    try:
        if hasattr(args, "run") and args.run:
            logger.info("Submitting Job")
            executor = ExecuteWorkflow(
                json_file=args.workflow,
                batch_size=args.batch_size,
                frame_range=args.frame_range,
                int_args=args.int_args,
                float_args=args.float_args,
                str_args=args.str_args,
            )
            executor.execute(False)
            return sys.exit()

        # If GUI is requested or no workflow is provided, launch GUI
        if hasattr(args, "gui") and args.gui or not args.workflow:
            launch_gui()
            return

        logger.info("Executing workflow in CLI mode...")
        if not os.path.exists(args.workflow):
            logger.error(f"Workflow file not found: {args.workflow}")
            return sys.exit(-1)

        dispatch(workflow=args.workflow, on_farm=args.on_farm)

    except KeyboardInterrupt:
        return sys.exit(1)
    except Exception:
        import traceback

        traceback.print_exc()
        return sys.exit(-1)


if __name__ == "__main__":
    main()
