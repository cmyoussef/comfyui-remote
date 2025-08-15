"""
DNEG-specific launcher. Wraps enroot when outside container, runs inside otherwise.
Inherits core flow; overrides command construction and execution.
"""

from __future__ import annotations
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from .comfy_server import ComfyServerLauncher


class DnegComfyServerLauncher(ComfyServerLauncher):
    """Start ComfyUI using DNEG's container conventions."""

    # Defaults (can be overridden by env)
    DN_DEFAULT_VERSION = os.getenv("DN_COMFYUI_VERSION", "1.0.11")
    COMFY_BASE_PATH = os.getenv("COMFY_BASE_PATH", "/tools/SITE/rnd/comfyUI")
    ENROOT_IMAGE = os.getenv("ENROOT_IMAGE", "/jobs/ADGRE/2D/nvidia_pytorch_comfyui_podman:latest.sqsh")

    def _in_container(self) -> bool:
        if os.path.exists("/.dockerenv"):
            return True
        if any(os.getenv(k) for k in ("container", "PODMAN_CONTAINER", "ENROOT_CONTAINER")):
            return True
        try:
            with open("/proc/1/cgroup", "r", encoding="utf-8") as f:
                text = f.read()
            return any(x in text for x in ("docker", "lxc", "podman", "containerd", "crio"))
        except Exception:
            return False

    def _resolve_dirs(
        self,
        out_dir: str | None,
        in_dir: str | None,
        tmp_dir: str | None,
        usr_dir: str | None,
    ):
        # DNEG defaults are under /user_data
        base = Path("/user_data/comfyui")
        out_p = Path(out_dir or (base / "output")).resolve()
        in_p = Path(in_dir or (base / "input")).resolve()
        tmp_p = Path(tmp_dir or (base / "temp")).resolve()
        usr_p = Path(usr_dir or (base / "user")).resolve()
        for p in (out_p, in_p, tmp_p, usr_p):
            p.mkdir(parents=True, exist_ok=True)
        return out_p, in_p, tmp_p, usr_p

    def _container_main_py(self) -> Path:
        # e.g. /tools/SITE/rnd/comfyUI/comfyui-1.0.11/ComfyUI/main.py
        return Path(self.COMFY_BASE_PATH) / f"comfyui-{self.DN_DEFAULT_VERSION}" / "ComfyUI" / "main.py"

    def _build_command(  # type: ignore[override]
        self,
        *,
        main_py: Path,  # ignored in DNEG (we use container main)
        host: str,
        port: int,
        out_dir: Path,
        in_dir: Path,
        tmp_dir: Path,
        usr_dir: Path,
        disable_cuda_malloc: bool,
        extra: list[str],
    ) -> list[str]:
        # Build the command that runs *inside* the container.
        c_main = self._container_main_py()
        cmd = [
            "python",
            "-W",
            "ignore::DeprecationWarning",
            str(c_main),
            "--listen",
            host,
            "--port",
            str(port),
            "--output-directory",
            str(out_dir),
            "--input-directory",
            str(in_dir),
            "--temp-directory",
            str(tmp_dir),
            "--user-directory",
            str(usr_dir),
        ]
        if disable_cuda_malloc:
            cmd.append("--disable-cuda-malloc")
        if extra:
            cmd.extend(extra)
        return cmd

    def _exec(self, cmd_inside_container: list[str]) -> int:  # type: ignore[override]
        if self._in_container():
            # Already in container → run directly
            os.environ.setdefault("PYTHONWARNINGS", "ignore::DeprecationWarning")
            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
            try:
                return subprocess.call(cmd_inside_container)
            except KeyboardInterrupt:
                return 130

        # Host → wrap with enroot
        if not shutil.which("enroot"):
            print("[ERROR] enroot not found in PATH.", file=sys.stderr)
            return 2
        if not Path(self.ENROOT_IMAGE).exists():
            print(f"[ERROR] ENROOT image not found: {self.ENROOT_IMAGE}", file=sys.stderr)
            return 2

        os.environ.setdefault("ENROOT_CACHE_PATH", "/user_data/.tmp")

        volumes: list[str] = []
        def mnt(host: str, guest: str | None = None):
            guest = guest or host
            volumes.extend(["--mount", f"{host}:{guest}"])

        # Standard mounts for studio environment
        mnt("/jobs"); mnt("/hosts"); mnt("/user_data"); mnt("/usr/share/fonts/truetype")
        mnt(self.COMFY_BASE_PATH, self.COMFY_BASE_PATH)

        enroot_cmd: list[str] = [
            "enroot", "start", "--rw", "--root",
            *volumes,
            self.ENROOT_IMAGE,
            *cmd_inside_container,
        ]
        print("[INFO] Launching via enroot:")
        print("      " + " ".join(map(self._quote, enroot_cmd)))
        try:
            return subprocess.call(enroot_cmd)
        except KeyboardInterrupt:
            return 130

    @staticmethod
    def _quote(x: str) -> str:
        if any(c in x for c in ' \t"\''):
            return '"' + x.replace('"', '\\"') + '"'
        return x


def main(argv: list[str] | None = None) -> int:
    return DnegComfyServerLauncher().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
