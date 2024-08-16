import os
from setuptools import find_packages, setup


PACKAGE_VERSION_NAME = os.getenv("PACKAGE_VERSION_NAME", "0.0-dev0")


setup(
    name="comfyui-remote",
    version=PACKAGE_VERSION_NAME,
    package_dir={"": "src"},
    packages=find_packages("src"),
)
