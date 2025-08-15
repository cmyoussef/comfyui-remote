"""ComfyUI Remote Toolkit."""
__all__ = []
__version__ = "0.1.0"

# src/femtodb/__init__.py

import os

try:
    from dotenv import load_dotenv
    # Construct the path to the top-level directory (two levels up from here)
    THIS_DIR = os.path.dirname(os.path.abspath(__file__))
    ROOT_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", ".."))
    DOTENV_PATH = os.path.join(ROOT_DIR, ".env")

    if os.path.exists(DOTENV_PATH):
        load_dotenv(DOTENV_PATH)
        print(
            f"[femtocore] Loaded environment variables from {DOTENV_PATH}")
except ImportError:
    # If python-dotenv is not installed, either fail silently or log a warning
    pass

# (Any other package-initialization logic can go here)
