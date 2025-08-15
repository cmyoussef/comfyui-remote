"""
Cross-platform ComfyUI launcher (single source of truth).

- Resolves COMFYUI_HOME (folder containing main.py or ComfyUI/main.py)
- Handles Electron/desktop shapes on Windows/macOS
- Ensures output/input/temp/user dirs exist
- Picks port (--port N, or auto when 0)
- Runs ComfyUI in foreground; exits with same code
"""

from __future__ import annotations
import argparse
import os
import socket
import subprocess
import sys
from pathlib import Path


class ComfyServerLauncher:
    """Start a local ComfyUI process."""

    # --- public entrypoint ---
    def run(self, argv: list[str] | None = None) -> int:
        args = self._parse_args(argv or sys.argv[1:])
        home = self._resolve_home(args.home)
        home = self._normalize_home_for_bundles(home)
        main_py = self._find_main_py(home)
        if not main_py:
            tried = "\n  - ".join(map(str, self._candidate_main_paths(home)))
            print(
                "[ERROR] Could not find ComfyUI main.py.\n"
                f"  COMFYUI_HOME resolved to: {home}\n"
                "  Tried:\n"
                f"  - {tried}\n\n"
                "Set --home or COMFYUI_HOME to the folder that contains ComfyUI.\n"
                "Examples:\n"
                "  --home C:\\path\\to\\ComfyUI\n"
                "  --home C:\\Users\\<you>\\AppData\\Local\\Programs\\@comfyorgcomfyui-electron\\resources\\ComfyUI\n"
                "  --home /Applications/ComfyUI.app/Contents/Resources/ComfyUI\n",
                file=sys.stderr,
            )
            return 2

        out_dir, in_dir, tmp_dir, usr_dir = self._resolve_dirs(
            args.output_dir, args.input_dir, args.temp_dir, args.user_dir
        )
        port = self._choose_port(args.port)
        cmd = self._build_command(
            main_py=main_py,
            host=args.host,
            port=port,
            out_dir=out_dir,
            in_dir=in_dir,
            tmp_dir=tmp_dir,
            usr_dir=usr_dir,
            disable_cuda_malloc=args.disable_cuda_malloc,
            extra=args.extra,
        )
        print(f"[INFO] COMFYUI_HOME={home}")
        print(f"[INFO] Using main.py   ={main_py}")
        print(f"[INFO] Starting ComfyUI on http://{args.host}:{port}")
        return self._exec(cmd)

    # -------- internals --------

    def _parse_args(self, argv: list[str]) -> argparse.Namespace:
        p = argparse.ArgumentParser(
            prog="comfy-remote",
            description="Start a local ComfyUI server.",
            add_help=True,
        )
        p.add_argument("--home", type=str, default=None, help="COMFYUI_HOME path.")
        p.add_argument("--host", type=str, default=os.getenv("COMFY_LISTEN", "127.0.0.1"))
        p.add_argument("--port", type=int, default=int(os.getenv("COMFY_PORT", "8188")))
        p.add_argument("--output-dir", type=str, default=os.getenv("COMFY_OUTPUT", None))
        p.add_argument("--input-dir", type=str, default=os.getenv("COMFY_INPUT", None))
        p.add_argument("--temp-dir", type=str, default=os.getenv("COMFY_TEMP", None))
        p.add_argument("--user-dir", type=str, default=os.getenv("COMFY_USER", None))
        p.add_argument(
            "--disable-cuda-malloc",
            action="store_true",
            default=True,
            help="Disable CUDA memory pool (default ON).",
        )
        p.add_argument(
            "--no-disable-cuda-malloc",
            dest="disable_cuda_malloc",
            action="store_false",
            help=argparse.SUPPRESS,
        )
        args, unknown = p.parse_known_args(argv)
        args.extra = unknown
        return args

    def _resolve_home(self, cli_home: str | None) -> Path:
        if cli_home:
            return Path(cli_home).expanduser().resolve()
        env = os.getenv("COMFYUI_HOME")
        if env:
            return Path(env).expanduser().resolve()
        # Try sibling "ComfyUI" next to repo root
        here = Path(__file__).resolve()
        guess = here.parents[3] / "ComfyUI" if len(here.parents) >= 4 else None
        if guess and guess.exists():
            return guess.resolve()
        return Path.cwd()

    def _normalize_home_for_bundles(self, home: Path) -> Path:
        """
        If user pointed to Desktop/Electron app roots, normalize to Resources/ComfyUI folder.
        Handles:
          - Windows:   <App>\ComfyUI.exe  -> <App>\resources\ComfyUI
          - macOS:     ComfyUI.app        -> ComfyUI.app/Contents/Resources/ComfyUI
        """
        # Windows .exe given directly
        if home.is_file() and home.name.lower() == "comfyui.exe":
            maybe = home.parent / "resources" / "ComfyUI"
            if (maybe / "main.py").exists():
                return maybe

        # Windows app folder that contains ComfyUI.exe
        exe = home / "ComfyUI.exe"
        if exe.exists():
            maybe = home / "resources" / "ComfyUI"
            if (maybe / "main.py").exists():
                return maybe

        # macOS .app root
        if home.suffix.lower() == ".app":
            maybe = home / "Contents" / "Resources" / "ComfyUI"
            if (maybe / "main.py").exists():
                return maybe

        return home

    def _candidate_main_paths(self, home: Path) -> list[Path]:
        """
        All common shapes we support:
          - <home>/main.py
          - <home>/ComfyUI/main.py
          - <home>/resources/ComfyUI/main.py (Windows Desktop)
          - <home>/Contents/Resources/ComfyUI/main.py (macOS Desktop)
        """
        return [
            home / "main.py",
            home / "ComfyUI" / "main.py",
            home / "resources" / "ComfyUI" / "main.py",
            home / "Contents" / "Resources" / "ComfyUI" / "main.py",
        ]

    def _find_main_py(self, home: Path) -> Path | None:
        for cand in self._candidate_main_paths(home):
            if cand.is_file():
                return cand
        return None

    def _resolve_dirs(
        self,
        out_dir: str | None,
        in_dir: str | None,
        tmp_dir: str | None,
        usr_dir: str | None,
    ) -> tuple[Path, Path, Path, Path]:
        base = Path.home() / "comfyui"
        out_p = Path(out_dir or (base / "output")).resolve()
        in_p = Path(in_dir or (base / "input")).resolve()
        tmp_p = Path(tmp_dir or (base / "temp")).resolve()
        usr_p = Path(usr_dir or (base / "user")).resolve()
        for p in (out_p, in_p, tmp_p, usr_p):
            p.mkdir(parents=True, exist_ok=True)
        return out_p, in_p, tmp_p, usr_p

    def _choose_port(self, requested: int) -> int:
        if requested and requested != 0:
            return requested
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def _build_command(
        self,
        *,
        main_py: Path,
        host: str,
        port: int,
        out_dir: Path,
        in_dir: Path,
        tmp_dir: Path,
        usr_dir: Path,
        disable_cuda_malloc: bool,
        extra: list[str],
    ) -> list[str]:
        cmd = [
            sys.executable,
            "-W",
            "ignore::DeprecationWarning",
            str(main_py),
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

    def _exec(self, cmd: list[str]) -> int:
        try:
            return subprocess.call(cmd)
        except KeyboardInterrupt:
            return 130


def main(argv: list[str] | None = None) -> int:
    return ComfyServerLauncher().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
