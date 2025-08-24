# src/comfyui_remote/connectors/comfy/server_manager.py
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List

from .server_registry import ServerRegistry
from ...config.manager import ConfigManager
from ...connectors.comfy.schema_resolver import SchemaResolverRegistry


def _find_free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def _env_get_home() -> Optional[Path]:
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
    print(f"[ServerManager] Locating ComfyUI main.py (hint={home_hint})")
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


def _dbg_on() -> bool:
    v = os.getenv("COMFY_DEBUG_SERVER") or os.getenv("COMFY_DEBUG")
    return str(v).lower() in ("1", "true", "yes", "on")


def _dbg(title: str, payload: Any) -> None:
    if not _dbg_on():
        return
    print(f"\n[ServerManager] {title}")
    try:
        import json
        if isinstance(payload, (dict, list)):
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(payload)
    except Exception:
        print(payload)


@dataclass
class _ProcHandle:
    id: str
    pid: int
    host: str
    port: int
    base_url: str
    log_path: str
    proc: subprocess.Popen


@dataclass
class LaunchPlan:
    """
    A pre-flight launch plan for ComfyUI. Useful for debugging without spawning.
    """
    home_dir: Path
    main_py: Path
    argv: List[str]  # full argv to pass after python -u main.py
    env: Dict[str, str]  # merged environment
    extra_yaml: Optional[str]  # path to the generated extra-model-paths YAML (if any)
    host: str
    port: int
    log_path: str  # where we will log if started


class ComfyServerManager:
    """
    Process manager for ComfyUI with registry support and layering-aware config.
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

    # New: generate a plan without launching (debug-friendly)
    def prepare(self, opts: Optional[Dict[str, Any]] = None) -> LaunchPlan:
        """
        Compute argv/env/home/main and the extra-model-paths YAML path
        without spawning the process. Use this for debugging the exact
        values passed to Comfy.
        """
        opts = dict(opts or {})

        # 1) Resolve config via ConfigManager (layering-aware)
        cfg = self._cfg_mgr.finalize()

        # CLI/opts overrides: host/port/io dirs/tags/meta are start()-only; we honor host/port/io here
        host_override = str(opts.pop("host", "") or "").strip()
        if host_override:
            cfg.server.host = host_override
        if not cfg.server.host:
            cfg.server.host = "127.0.0.1"

        port_override = opts.pop("port", None)
        if isinstance(port_override, int):
            cfg.server.port = port_override

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
        print(cfg.paths.home)
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
        argv: List[str] = []
        argv += ["--listen", cfg.server.host, "--port", str(cfg.server.port)]
        # build_runtime already included these, but the caller of prepare
        # wants to see the exact list that will be appended after main.py.
        # So we take rt.argv directly (it contains all flags).
        argv = list(rt.argv)
        if rt.extra_paths_file:
            argv += ["--extra-model-paths-config", rt.extra_paths_file]

        # 4) Plan log path
        log_dir = Path(tempfile.gettempdir()) / "comfyui-remote"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = str(log_dir / f"comfy-{cfg.server.host.replace(':', '_')}-{cfg.server.port}.log")

        plan = LaunchPlan(
            home_dir=home_dir,
            main_py=main_py,
            argv=argv,
            env=os.environ.copy() | (rt.env or {}),
            extra_yaml=rt.extra_paths_file,
            host=cfg.server.host,
            port=cfg.server.port,
            log_path=log_path,
        )

        if _dbg_on():
            _dbg("LaunchPlan.home_dir", str(plan.home_dir))
            _dbg("LaunchPlan.main_py", str(plan.main_py))
            _dbg("LaunchPlan.argv", plan.argv)
            _dbg("LaunchPlan.extra_yaml", plan.extra_yaml)
            if plan.extra_yaml and Path(plan.extra_yaml).exists():
                try:
                    txt = Path(plan.extra_yaml).read_text(encoding="utf-8")
                except Exception:
                    txt = "<unreadable>"
                _dbg("LaunchPlan.extra_yaml_content", txt)

        return plan

    def ensure_schema(self, base_url: Optional[str] = None) -> Optional[str]:
        """
        Ensure compiler can resolve node arg names/types. Delegates to
        SchemaResolverRegistry.ensure(...), then updates self._ctx.base_url
        with the returned key (url | file:<abs> | inline:<token>).
        """
        try:
            key = SchemaResolverRegistry.ensure(base_url=base_url or None)
            self._schema_key = key
            self._ctx.base_url = key
            return key
        except Exception:
            return None

    def start(
            self,
            opts: Optional[Dict[str, Any]] = None,
            timeout: float = 45.0,
    ) -> _ProcHandle:
        """
        Start ComfyUI with resolved configuration.
        """
        if self._handle is not None:
            raise RuntimeError("ComfyUI server already started")

        tags: List[str] = list((opts or {}).pop("tags", []) or [])
        meta: Dict[str, Any] = dict((opts or {}).pop("meta", {}) or {})

        # Prepare plan (argv/env/etc.)
        plan = self.prepare(opts or {})

        # Compose full argv for process launch
        full_argv: List[str] = [sys.executable, "-u", str(plan.main_py)]
        full_argv += plan.argv

        # Prepare logs
        log_f = open(plan.log_path, "w", encoding="utf-8", buffering=1)

        # Launch
        env = os.environ.copy()
        env.update(plan.env or {})

        if _dbg_on():
            _dbg("Spawning argv", full_argv)
            _dbg("Log path", plan.log_path)
            if plan.extra_yaml and Path(plan.extra_yaml).exists():
                try:
                    txt = Path(plan.extra_yaml).read_text(encoding="utf-8")
                except Exception:
                    txt = "<unreadable>"
                _dbg("extra-model-paths YAML (final, before spawn)", txt)

        proc = subprocess.Popen(
            full_argv,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            cwd=str(plan.home_dir),
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )

        # Wait until ready
        self._wait_until_listening(plan.host, plan.port, plan.log_path, timeout=timeout)

        base = f"http://{plan.host}:{plan.port}"
        print(f"[comfyui-remote] Started ComfyUI pid={proc.pid} url={base} log={plan.log_path}")

        sid = self._registry.register_start(
            base_url=base,
            host=plan.host,
            port=plan.port,
            pid=proc.pid,
            log_path=plan.log_path,
            tags=tags,
            meta=meta,
        )

        self._handle = _ProcHandle(sid, proc.pid, plan.host, plan.port, plan.log_path, base, proc)
        return self._handle

    def stop(self) -> None:
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

    def list_known(self) -> List[Dict[str, Any]]:
        return [rec.to_dict() for rec in self._registry.list_latest()]

    # --------------- internals ---------------

    def _wait_until_listening(self, host: str, port: int, log_path: str, timeout: float) -> None:
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
            os.kill(pid, 15)
            return True
        except Exception:
            try:
                os.kill(pid, 9)
                return True
            except Exception:
                return False
