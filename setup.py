"""Package metadata specification."""

import os
import sys
from glob import glob

from setuptools import find_packages, setup

PACKAGE_VERSION_NAME = os.getenv("PACKAGE_VERSION_NAME", "0.0-dev0")


def read(file_name):
    """Get the contents of a file at the root of the package.

    Args:
        file_name (str): The name of the file at the root of the package
            to get the contents of.

    Returns:
        str: The contents of the file.

    """
    with open(file_name) as file_:
        contents = file_.read()
    return contents


python_version = "python{}.{}".format(sys.version_info[0], sys.version_info[1])
project_name = read("PROJECT").strip()
project_dir = "lib/{}/site-packages/{}".format(python_version, project_name)
resources_dir = os.path.join(project_dir, "ui", "resources")

setup(
    name="comfy-remote",
    version=PACKAGE_VERSION_NAME,
    description="User facing tool to launch the ComfyUI workflows on the farm.",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    author="platform-nuke-developers",
    author_email="platform-nuke-developers@dneg.com",
    url="http://stash/projects/ADG/repos/comfyui-remote",
    # Package contents
    python_requires=">=3.7",
    packages=find_packages("src"),
    package_dir={"": "src"},
    package_data={project_name: ["VERSION"]},
    data_files=[
        (project_dir, ["VERSION", "PROJECT"]),
        (
            "bin",
            [
                "bin/comfy-remote",
                "bin/comfyui",
            ],
        ),
        (resources_dir, glob("src/comfyui_remote/ui/resources/[a-zA-Z]*.*")),
    ],
    classifiers=[
        "Operating System :: Unix",
        "Programming Language :: Python :: 3.7",
    ],
    platforms=["Unix", "Darwin"],
    # scripts=[
    #     "bin/comfy-remote",
    #     "bin/comfyui",
    #     "src/comfyui_remote/runner.py"
    # ],
    # Package dependencies (use the devpi pkg name)
    install_requires=[
        "apitrack",
        "astrohub",
        "cards",
        "dnexception",
        "dnlogging",
        "ivyengine",
        "pipefuncs",
        "spider",
        "venom",
    ],
    extras_require={
        # packages required to build the package go in the "bob_setup" extra
        # (use the bob pkg name)
        "bob_setup": [],
        # non-devpi packages required to run the package go in the "bob_runtime" extra
        # (use the bob pkg name)
        "bob_runtime": ["dneg_dnsitedata", "dneg_dnpath"],
        # packages required to run the tests go in the "test" extra
        # (use the devpi pkg name)
        "test": [
            "pytest>4",
            "pytest-cov",
        ],
    },
)
