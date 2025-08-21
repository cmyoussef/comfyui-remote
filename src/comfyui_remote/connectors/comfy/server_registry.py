# src/comfyui_remote/connectors/comfy/server_registry.py
from __future__ import annotations

import json
import os
import socket
import time
import uuid
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
    state: str                 # "running" | "stopped"
    base_url: str              # e.g. http://HOST:PORT
    host: str                  # listen host
    port: int
    pid: int
    started_at: str
    stopped_at: Optional[str] = None
    owner_user: str = ""
    owner_host: str = ""
    log_path: str = ""
    tags: List[str] = None     # e.g. ["farm"] or ["local"]
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
