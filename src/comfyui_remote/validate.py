"""Validation functions for Nuke Remote Control CLI/GUI."""

import sys
import argparse
import logging

from .utils.string_utils import convert_string_to_dict

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ValidateOverrides(argparse.Action):
    """Validate and convert overrides parameter to dictionary."""

    def __call__(self, parser, namespace, values, option_string=None):
        overrides_dict = convert_string_to_dict(values)
        if overrides_dict is None:
            logger.error('Error while validating the `overrides`: "%s"', values)
            sys.exit(-1)

        logger.info("Setting overrides: %s", overrides_dict)
        setattr(namespace, self.dest, overrides_dict)
