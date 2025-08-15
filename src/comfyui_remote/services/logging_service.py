"""Logging."""
import logging
import sys


class LoggingService:
    def __init__(self, level=logging.INFO) -> None:
        self._level = level

    def get_logger(self, name: str) -> logging.Logger:
        logger = logging.getLogger(name)
        if not logger.handlers:
            h = logging.StreamHandler(sys.stdout)
            fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
            h.setFormatter(fmt)
            logger.addHandler(h)
        logger.setLevel(self._level)
        return logger
