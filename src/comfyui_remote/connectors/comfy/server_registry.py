# src/comfyui_remote/connectors/comfy/server_registry.py
from __future__ import annotations

import json
import os
import socket
import time
import uuid
import requests
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, List, Optional, Iterable


def _now_iso() -> str:
    import datetime as _dt
    return _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc).isoformat()


class _FileMutex:
    """Cross-platform best-effort lock based on an atomic .lock file."""

    def __init__(self, lock_path: Path, poll_interval: float = 0.05) -> None:
        self._lock_path = str(lock_path)
        self._fd: Optional[int] = None
        self._poll = poll_interval

    def __enter__(self):
        while True:
            try:
                self._fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                break
            except FileExistsError:
                time.sleep(self._poll)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._fd is not None:
                os.close(self._fd)
        finally:
            try:
                os.unlink(self._lock_path)
            except Exception:
                pass


@dataclass
class ServerRecord:
    id: str
    state: str  # "running" | "stopped"
    base_url: str  # e.g. http://HOST:PORT
    host: str  # listen host
    port: int
    pid: int
    started_at: str
    stopped_at: Optional[str] = None
    owner_user: str = ""
    owner_host: str = ""
    log_path: str = ""
    tags: List[str] = None  # e.g. ["farm"] or ["local"]
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # normalize None fields
        d["tags"] = self.tags or []
        d["meta"] = self.meta or {}
        return d


class ServerRegistry:
    """
    Append-only JSONL registry (one JSON per line) with a simple lockfile.
    Use a network/shared path (via COMFY_REGISTRY) to make it visible to other hosts.
    Now includes validation to detect crashed/killed servers.
    """

    def __init__(self, path: Optional[str] = None) -> None:
        env_path = os.getenv("COMFY_REGISTRY", "")
        base = Path(path or env_path or (Path.home() / ".comfyui-remote" / "servers.jsonl"))
        base.parent.mkdir(parents=True, exist_ok=True)
        self._file = base
        self._lock = base.with_suffix(base.suffix + ".lock")

    # ------------ low-level IO ------------
    def _append_event(self, event: Dict[str, Any]) -> None:
        with _FileMutex(self._lock):
            with self._file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _read_all(self) -> List[Dict[str, Any]]:
        if not self._file.exists():
            return []
        with self._file.open("r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        out: List[Dict[str, Any]] = []
        for ln in lines:
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
        return out

    # ------------ public API ------------
    def register_start(self, *, base_url: str, host: str, port: int, pid: int,
                       log_path: str = "", tags: Optional[List[str]] = None,
                       meta: Optional[Dict[str, Any]] = None) -> str:
        sid = uuid.uuid4().hex
        ev = {
            "type": "start",
            "id": sid,
            "base_url": base_url,
            "host": host,
            "port": port,
            "pid": pid,
            "started_at": _now_iso(),
            "owner_user": os.getenv("USERNAME") or os.getenv("USER") or "",
            "owner_host": socket.gethostname(),
            "log_path": log_path,
            "tags": tags or [],
            "meta": meta or {},
        }
        self._append_event(ev)
        return sid

    def register_stop(self, server_id: str) -> None:
        ev = {"type": "stop", "id": server_id, "stopped_at": _now_iso()}
        self._append_event(ev)

    def list_latest(self) -> List[ServerRecord]:
        """
        Return the latest state per id. Active servers are those with state == 'running'.
        """
        events = self._read_all()
        latest: Dict[str, Dict[str, Any]] = {}
        for ev in events:
            t = ev.get("type")
            sid = ev.get("id")
            if not sid:
                continue
            if t == "start":
                latest[sid] = {
                    "id": sid,
                    "state": "running",
                    "base_url": ev.get("base_url", ""),
                    "host": ev.get("host", ""),
                    "port": int(ev.get("port", 0)),
                    "pid": int(ev.get("pid", 0)),
                    "started_at": ev.get("started_at", ""),
                    "stopped_at": None,
                    "owner_user": ev.get("owner_user", ""),
                    "owner_host": ev.get("owner_host", ""),
                    "log_path": ev.get("log_path", ""),
                    "tags": list(ev.get("tags", [])),
                    "meta": dict(ev.get("meta", {})),
                }
            elif t == "stop" and sid in latest:
                latest[sid]["state"] = "stopped"
                latest[sid]["stopped_at"] = ev.get("stopped_at", _now_iso())

        return [ServerRecord(**rec) for rec in latest.values()]

    def find_by_url_or_id(self, key: str) -> Optional[ServerRecord]:
        key = (key or "").strip()
        if not key:
            return None
        recs = self.list_latest()
        # Accept http://host:port, host:port, or a bare id
        norm_key = key
        if norm_key.startswith("http://") or norm_key.startswith("https://"):
            pass
        elif ":" in norm_key:
            norm_key = "http://" + norm_key
        for r in recs:
            if r.id == key or r.base_url == norm_key:
                return r
        return None

    # ------------ NEW: Validation methods ------------
    def validate_server(self, server: ServerRecord, timeout: float = 1.0) -> bool:
        """
        Validate if a server is actually running by:
        1. Checking if it's on the local machine and the PID exists
        2. Attempting to connect to its /object_info endpoint

        Returns True if server is reachable, False otherwise.
        """
        # First check: Is this a local server?
        local_hosts = {"localhost", "127.0.0.1", socket.gethostname()}
        try:
            local_hosts.add(socket.gethostbyname(socket.gethostname()))
        except Exception:
            pass

        is_local = server.host in local_hosts

        # For local servers, check if PID exists
        if is_local and server.pid:
            if not self._is_pid_running(server.pid):
                return False

        # Second check: Try to reach the server's API
        try:
            response = requests.get(
                f"{server.base_url}/object_info",
                timeout=timeout
            )
            return response.ok
        except Exception:
            return False

    def _is_pid_running(self, pid: int) -> bool:
        """Check if a PID is running on the local system"""
        if os.name == 'nt':
            # Windows
            try:
                import psutil
                return psutil.pid_exists(pid)
            except ImportError:
                # Fallback for Windows without psutil
                import subprocess
                try:
                    result = subprocess.run(
                        ['tasklist', '/FI', f'PID eq {pid}'],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    return str(pid) in result.stdout
                except Exception:
                    return True  # Assume running if we can't check
        else:
            # Unix/Linux/Mac
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False
            except Exception:
                return True  # Assume running if we can't check

    def validate_and_update(self, timeout: float = 1.0) -> int:
        """
        Validate all 'running' servers and update their state if they're not reachable.
        Returns the number of servers that were marked as stopped.
        """
        servers = self.list_latest()
        stopped_count = 0

        for server in servers:
            if server.state != "running":
                continue

            # Validate the server
            if not self.validate_server(server, timeout=timeout):
                # Server is not reachable, mark it as stopped
                self.register_stop(server.id)
                stopped_count += 1
                print(f"[Registry] Server {server.id[:8]} ({server.base_url}) is not reachable, marking as stopped")

        return stopped_count

    def validate_specific(self, server_id: str, timeout: float = 1.0) -> bool:
        """
        Validate a specific server and update its state if needed.
        Returns True if the server is running, False if it was marked as stopped.
        """
        server = None
        for s in self.list_latest():
            if s.id == server_id:
                server = s
                break

        if not server:
            return False

        if server.state != "running":
            return False

        is_valid = self.validate_server(server, timeout=timeout)

        if not is_valid:
            self.register_stop(server_id)
            print(f"[Registry] Server {server_id[:8]} is not reachable, marking as stopped")

        return is_valid