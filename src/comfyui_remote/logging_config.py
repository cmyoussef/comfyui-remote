"""Logging configuration module for Comfy Remote."""

import logging
import os
import sys

from dnlogging.formatters import DnFormatter, DEFAULT_LOG_FORMAT
from dnlogging.handlers import ColoredStreamHandler


def setup_logging(level=logging.INFO, debug=False, stdout=True, logfile=False):
    """Sets up Comfy Remote Logger.

    Sets the logger up for the specified program name and logging level
    with optional file logging support.

    Args:
        level (logging.LEVEL): The level to log at.
        debug (bool): Set log level to debug if level is not set.
        stdout (bool): Enable stdout logging.
        logfile (bool): Enable file logging as well as stdout.
    """
    # Get the logging level for the root logger
    log_level = logging.INFO
    if level:
        log_level = level
    elif debug or os.environ.get("COMFYUI_REMOTE_DEBUG") == "1":
        log_level = logging.DEBUG

    try:
        logger = logging.getLogger("comfyui_remote")

        # File logging
        if logfile:
            logger.addFileHandler(level=logging.DEBUG)

        # stdout logging
        if stdout:
            handler = ColoredStreamHandler(sys.stdout)
            handler.setLevel(log_level)
            handler.setFormatter(DnFormatter(DEFAULT_LOG_FORMAT))
            logger.addHandler(handler)

        logger.setLevel(log_level)
        # Turn off propagation to avoid double console prints
        logger.propagate = False

        return logger

    except Exception as exc:
        sys.stderr.write("Error initializing logger: {0}\n".format(str(exc)))
        # Return a basic logger as fallback
        logger = logging.getLogger("comfyui_remote")
        logger.setLevel(log_level)
        return logger
