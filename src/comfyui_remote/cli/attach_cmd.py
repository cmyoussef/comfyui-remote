# src/comfyui_remote/cli/attach_cmd.py
from __future__ import annotations

import argparse
import json
import time
from typing import Optional, List

import requests

from ..connectors.comfy.server_registry import ServerRegistry, ServerRecord


class AttachConnectCommand:
    @staticmethod
    def _resolve_target(reg: ServerRegistry, url_or_id: Optional[str]) -> Optional[ServerRecord]:
        if url_or_id:
            rec = reg.find_by_url_or_id(url_or_id)
            return rec
        # pick most recent 'running'
        recs: List[ServerRecord] = [r for r in reg.list_latest() if r.state == "running"]
        if not recs:
            return None
        # started_at is ISO, safe to sort lexicographically
        recs.sort(key=lambda r: r.started_at or "", reverse=True)
        return recs[0]

    # -------- Attach --------
    @staticmethod
    def configure_attach(p: argparse.ArgumentParser) -> None:
        p.add_argument("--url", help="http://host:port or host:port or registry id (optional; picks latest running if omitted)")
        p.add_argument("--registry", help="Path to registry JSONL (defaults to COMFY_REGISTRY or ~/.comfyui-remote/servers.jsonl)")
        p.add_argument("--json", action="store_true", help="Emit JSON with connection details")

    def run_attach(self, args: argparse.Namespace) -> int:
        reg = ServerRegistry(args.registry) if args.registry else ServerRegistry()
        rec = self._resolve_target(reg, args.url)
        if not rec:
            print("[attach] no running servers found in registry")
            return 4
        payload = {
            "id": rec.id,
            "base_url": rec.base_url,
            "host": rec.host,
            "port": rec.port,
            "pid": rec.pid,
            "state": rec.state,
            "tags": rec.tags or [],
            "log": rec.log_path,
            "owner": f"{rec.owner_user}@{rec.owner_host}",
            "started_at": rec.started_at,
            "stopped_at": rec.stopped_at,
            "export": {
                "COMFY_REMOTE_URL": rec.base_url
            }
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(rec.base_url)
        return 0

    # -------- Connect (probe /object_info) --------
    @staticmethod
    def configure_connect(p: argparse.ArgumentParser) -> None:
        p.add_argument("--url", help="http://host:port or host:port or registry id (optional; picks latest running if omitted)")
        p.add_argument("--registry", help="Registry path (optional)")
        p.add_argument("--timeout", type=float, default=8.0, help="Connection timeout seconds")
        p.add_argument("--json", action="store_true", help="Emit JSON with probe result")

    def run_connect(self, args: argparse.Namespace) -> int:
        reg = ServerRegistry(args.registry) if args.registry else ServerRegistry()
        rec = self._resolve_target(reg, args.url)
        if not rec:
            print("[connect] no running servers found in registry")
            return 4
        base = rec.base_url.rstrip("/")
        t0 = time.time()
        ok = False
        status = 0
        content = None
        try:
            r = requests.get(base + "/object_info", timeout=args.timeout)
            status = r.status_code
            ok = r.ok
            if args.json:
                try:
                    content = r.json()
                except Exception:
                    content = r.text
        except Exception as e:
            if args.json:
                content = {"error": str(e)}
        dt = time.time() - t0

        if args.json:
            print(json.dumps({
                "url": base,
                "ok": bool(ok),
                "status": status,
                "elapsed_s": round(dt, 3),
                "payload": content,
            }, indent=2))
        else:
            print("OK" if ok else f"ERR {status}", base)
        return 0 if ok else 5

    # -------- Wiring --------
    @staticmethod
    def configure_top_level(sp: argparse._SubParsersAction) -> None:
        self = AttachConnectCommand()

        pa = sp.add_parser("attach", help="Resolve a server (by URL/id/latest) and print connection info")
        AttachConnectCommand.configure_attach(pa)
        pa.set_defaults(_cmd=self.run_attach)

        pc = sp.add_parser("connect", help="Probe a server's /object_info endpoint by URL/id/latest")
        AttachConnectCommand.configure_connect(pc)
        pc.set_defaults(_cmd=self.run_connect)
