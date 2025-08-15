# src/comfyui_remote/config/types.py
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any


@dataclass
class ServerConfig:
    """
    Server process options.
    - host: listen interface passed to Comfy (--listen)
    - port: port to bind; 0 means 'auto choose a free port'
    - disable_cuda_malloc / dont_print_server: mirrors Comfy CLI toggles
    - extra_args: any additional CLI args to pass through verbatim
    """
    host: str = "127.0.0.1"
    port: int = 0
    disable_cuda_malloc: bool = False
    dont_print_server: bool = False
    extra_args: List[str] = field(default_factory=list)


@dataclass
class IOConfig:
    """
    I/O directories Comfy uses.
    - Leave blank to use Comfy's defaults.
    - These may be overridden at runtime by the server manager's `opts` argument.
    """
    input_dir: str = ""
    output_dir: str = ""
    temp_dir: str = ""
    user_dir: str = ""


@dataclass
class PathsConfig:
    """
    Filesystem paths.
    - home: folder containing ComfyUI/main.py (or its parent that has ComfyUI/main.py)
    - models_root: a *single* root (e.g., E:/comfyui/comfyui) under which we auto-map
      models/<category> for categories not explicitly overridden.
    - models: explicit per-category list of paths; these take precedence over the root expansion.
    - custom_nodes: one or more custom_nodes folders
    """
    home: str = ""
    models_root: str = ""
    models: Dict[str, List[str]] = field(default_factory=dict)
    custom_nodes: List[str] = field(default_factory=list)


@dataclass
class ComfyConfig:
    """
    Full resolved config snapshot.
    """
    server: ServerConfig = field(default_factory=ServerConfig)
    io: IOConfig = field(default_factory=IOConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    env: Dict[str, str] = field(default_factory=dict)

    # Helpful convenience method for logging/introspection
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
