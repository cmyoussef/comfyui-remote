"""Version information."""
import pkg_resources
import logging


PACKAGE_NAME = "comfyui-remote"


try:
    __version__ = pkg_resources.get_distribution(PACKAGE_NAME).version

except pkg_resources.DistributionNotFound as error:
    logging.warning(
        "%s - so could not get the version",
        error
    )
    __version__ = "unknown"
