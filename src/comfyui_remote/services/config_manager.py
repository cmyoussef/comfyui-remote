"""Config."""
import os
from typing import Any


class ConfigManager:
    def __init__(self) -> None:
        self._profile = os.environ.get("COMFY_PROFILE", "default")

    def get(self, key: str, default_value: Any = None) -> Any:
        return os.environ.get(key, default_value)

    def profile(self) -> str:
        return self._profile
