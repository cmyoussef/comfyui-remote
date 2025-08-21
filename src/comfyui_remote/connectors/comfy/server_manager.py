# src/comfyui_remote/connectors/comfy/server_manager.py
from __future__ import annotations

import os
import sys
import time
import socket
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List

from ...config.manager import ConfigManager, RuntimeConfig
from ...config.types import ComfyConfig
from .server_registry import ServerRegistry


def _find_free_port(host: str) -> int:
    """
    Bind to (host, 0) to let the OS assign a free port on that host's interface.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def _env_get_home() -> Optional[Path]:
    """Resolve COMFYUI_HOME (if present) to the folder that contains main.py."""
    env = os.getenv("COMFYUI_HOME")
    if not env:
        return None
    p = Path(env)
    if (p / "main.py").exists():
        return p
    if (p / "ComfyUI" / "main.py").exists():
        return p / "ComfyUI"
    return None


def _locate_main_py(home_hint: str) -> Path:
    """
    Choose a folder with ComfyUI/main.py using (in order):
      1) explicit config.paths.home (if valid)
      2) COMFYUI_HOME env (if valid)
      3) current working directory (if it's a ComfyUI dir)
    """
    if home_hint:
        hp = Path(home_hint)
        if (hp / "main.py").exists():
            return hp
        if (hp / "ComfyUI" / "main.py").exists():
            return hp / "ComfyUI"

    env_home = _env_get_home()
    if env_home:
        return env_home

    cwd = Path.cwd()
    if (cwd / "main.py").exists():
        return cwd
    if (cwd / "ComfyUI" / "main.py").exists():
        return cwd / "ComfyUI"

    raise FileNotFoundError(
        "Could not find ComfyUI/main.py. "
        "Set COMFY_CONFIG.paths.home or COMFYUI_HOME to the ComfyUI folder."
    )


class _ProcHandle:
    __slots__ = ("id", "pid", "host", "port", "base_url", "log_path", "proc")

    def __init__(self, sid: str, pid: int, host: str, port: int, log_path: str, proc: subprocess.Popen):
        self.id = sid
        self.pid = pid
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.log_path = log_path
        self.proc = proc


class ComfyServerManager:
    """
    Robust process manager for ComfyUI:
      - Host-aware (not hardcoded to 127.0.0.1)
      - Registry-backed (JSONL + lockfile) so other tools can discover servers
      - YAML/JSON config via ConfigManager (COMFY_CONFIG)
      - Emits extra_model_paths.yaml when needed
      - Spawns ComfyUI, waits until /object_info responds, then registers "running"
      - Graceful stop registers "stopped"
    """

    def __init__(self, config_manager: Optional[ConfigManager] = None,
                 registry: Optional[ServerRegistry] = None,
                 registry_path: Optional[str] = None) -> None:
        self._cfg_mgr = config_manager or ConfigManager()
        self._registry = registry or ServerRegistry(registry_path)
        self._handle: Optional[_ProcHandle] = None

    # --------------- public API ---------------

    @property
    def handle(self) -> Optional[_ProcHandle]:
        return self._handle

    def start(
        self,
        opts: Optional[Dict[str, Any]] = None,
        timeout: float = 45.0,
    ) -> _ProcHandle:
        """
        Start ComfyUI with resolved configuration.

        :param opts: optional per‑run overrides:
                     {
                       "host": "...", "port": 0|int,
                       "input_dir": "...", "output_dir": "...",
                       "temp_dir": "...", "user_dir": "...",
                       "tags": ["farm"]   # recorded in the registry,
                       "meta": {...}      # arbitrary metadata to store in the registry
                     }
        :param timeout: seconds to wait for /object_info
        :return: process handle
        """
        if self._handle is not None:
            raise RuntimeError("ComfyUI server already started")

        opts = dict(opts or {})
        tags: List[str] = list(opts.pop("tags", []) or [])
        meta: Dict[str, Any] = dict(opts.pop("meta", {}) or {})

        # 1) Resolve config
        cfg = self._cfg_mgr.finalize()

        # Overrides: host/port
        host_override = str(opts.pop("host", "") or "").strip()
        if host_override:
            cfg.server.host = host_override
        if not cfg.server.host:
            cfg.server.host = "127.0.0.1"

        port_override = opts.pop("port", None)
        if isinstance(port_override, int):
            cfg.server.port = port_override

        # Per‑run IO overrides (commonly used in tests/e2e demo)
        if "input_dir" in opts:
            cfg.io.input_dir = str(opts["input_dir"])
        if "output_dir" in opts:
            cfg.io.output_dir = str(opts["output_dir"])
        if "temp_dir" in opts:
            cfg.io.temp_dir = str(opts["temp_dir"])
        if "user_dir" in opts:
            cfg.io.user_dir = str(opts["user_dir"])

        # Ensure port is chosen
        if not cfg.server.port or cfg.server.port == 0:
            cfg.server.port = _find_free_port(cfg.server.host)

        # 2) Locate Comfy main.py
        home_dir = _locate_main_py(cfg.paths.home)
        main_py = home_dir / "main.py"
        if not main_py.exists():
            alt = home_dir / "ComfyUI" / "main.py"
            if alt.exists():
                main_py = alt
            else:
                raise FileNotFoundError(f"main.py not found under: {home_dir}")

        # 3) Build runtime (argv/env + extra paths yaml)
        rt = self._cfg_mgr.build_runtime(cfg)

        # Compose final argv: python -u main.py + rt.argv + extra-model-paths-config
        argv: List[str] = [sys.executable, "-u", str(main_py)]
        argv += rt.argv
        if rt.extra_paths_file:
            argv += ["--extra-model-paths-config", rt.extra_paths_file]

        # 4) Prepare logs and environment
        log_dir = Path(tempfile.gettempdir()) / "comfyui-remote"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = str(log_dir / f"comfy-{cfg.server.host.replace(':','_')}-{cfg.server.port}.log")
        log_f = open(log_path, "w", encoding="utf-8", buffering=1)

        env = os.environ.copy()
        env.update(rt.env or {})

        # 5) Launch process
        proc = subprocess.Popen(
            argv,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            cwd=str(home_dir),
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )

        # 6) Wait until ready
        self._wait_until_listening(cfg.server.host, cfg.server.port, log_path, timeout=timeout)

        base = f"http://{cfg.server.host}:{cfg.server.port}"
        print(f"[comfyui-remote] Started ComfyUI pid={proc.pid} url={base} log={log_path}")

        # 7) Register as running
        sid = self._registry.register_start(
            base_url=base,
            host=cfg.server.host,
            port=cfg.server.port,
            pid=proc.pid,
            log_path=log_path,
            tags=tags,
            meta=meta,
        )

        self._handle = _ProcHandle(sid, proc.pid, cfg.server.host, cfg.server.port, log_path, proc)
        return self._handle

    def stop(self) -> None:
        """
        Gracefully stop the spawned ComfyUI process (if any), and mark registry 'stopped'.
        """
        if not self._handle:
            return
        try:
            self._handle.proc.terminate()
            self._handle.proc.wait(timeout=8.0)
        except Exception:
            try:
                self._handle.proc.kill()
            except Exception:
                pass
        finally:
            try:
                self._registry.register_stop(self._handle.id)
            except Exception:
                pass
            print(f"[comfyui-remote] Stopped ComfyUI pid={self._handle.pid} log={self._handle.log_path}")
            self._handle = None

    # --------------- discovery helpers ---------------

    def list_known(self) -> List[Dict[str, Any]]:
        """Return a simple dict view of known servers (latest state)."""
        return [rec.to_dict() for rec in self._registry.list_latest()]

    # --------------- internals ---------------

    def _wait_until_listening(self, host: str, port: int, log_path: str, timeout: float) -> None:
        """
        Poll http://{host}:{port}/object_info until the server becomes responsive, or dump log tail on timeout.
        """
        import requests

        base = f"http://{host}:{port}"
        start = time.time()
        while time.time() - start < timeout:
            try:
                r = requests.get(base + "/object_info", timeout=0.75)
                if r.ok:
                    return
            except Exception:
                time.sleep(0.25)

        # On failure, print a short tail of the Comfy log to help diagnose
        try:
            tail = Path(log_path).read_text(errors="ignore").splitlines()[-120:]
            print("\n--- Comfy log (tail) ---")
            print("\n".join(tail))
        except Exception:
            pass
        raise TimeoutError(f"ComfyUI did not respond on {base} within {timeout}s")

    # -------- utility for CLI 'stop --url' on local host --------
    @staticmethod
    def kill_local_pid(pid: int) -> bool:
        try:
            if os.name == "nt":
                import psutil  # optional; fallback below if unavailable
                try:
                    p = psutil.Process(pid)
                    p.terminate()
                    p.wait(8)
                    return True
                except Exception:
                    pass
            # portable fallback
            os.kill(pid, 15)  # SIGTERM on posix, ignored on windows (won't raise)
            return True
        except Exception:
            try:
                os.kill(pid, 9)  # SIGKILL posix; on Windows this will error; ignore
                return True
            except Exception:
                return False
