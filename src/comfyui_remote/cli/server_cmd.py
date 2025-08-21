# src/comfyui_remote/cli/server_cmd.py
from __future__ import annotations

import argparse
import json
import os
import socket

from ..connectors.comfy.server_manager import ComfyServerManager
from ..connectors.comfy.server_registry import ServerRegistry


class ServerCommand:
    @staticmethod
    def _add_start_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--host", default=os.getenv("COMFY_LISTEN", "127.0.0.1"))
        p.add_argument("--port", type=int, default=int(os.getenv("COMFY_PORT", "0")))
        p.add_argument("--input-dir")
        p.add_argument("--output-dir")
        p.add_argument("--temp-dir")
        p.add_argument("--user-dir")
        p.add_argument("--use-farm", action="store_true", help="Tag this instance as 'farm' in the registry")
        p.add_argument("--registry", help="Path to registry JSONL (defaults to COMFY_REGISTRY or ~/.comfyui-remote/servers.jsonl)")
        p.add_argument("--meta", help="Arbitrary JSON string to record in registry", default="")
        p.add_argument("--verbose", action="store_true")

    @staticmethod
    def _add_stop_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--url", help="http://host:port or host:port or id")
        p.add_argument("--registry", help="Registry path (optional)")

    @staticmethod
    def _add_list_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--registry", help="Registry path (optional)")
        p.add_argument("--json", action="store_true", help="Print raw JSON")

    # -------- Nested 'server' group (kept for compatibility) --------
    @staticmethod
    def configure(p: argparse.ArgumentParser) -> None:
        sub = p.add_subparsers(dest="action", required=True)

        ps = sub.add_parser("start", help="Start a ComfyUI server")
        ServerCommand._add_start_args(ps)

        pk = sub.add_parser("stop", help="Stop a server by URL or id (local host only)")
        ServerCommand._add_stop_args(pk)

        pl = sub.add_parser("list", help="List known servers from registry")
        ServerCommand._add_list_args(pl)

    # -------- Top-level aliases: start/stop/list --------
    @staticmethod
    def add_top_level_aliases(sp: argparse._SubParsersAction) -> None:
        self = ServerCommand()

        ps = sp.add_parser("start", help="Start a ComfyUI server (alias of 'server start')")
        ServerCommand._add_start_args(ps)
        ps.set_defaults(_cmd=self._alias_run, _alias_action="start")

        pk = sp.add_parser("stop", help="Stop a server by URL or id (alias of 'server stop')")
        ServerCommand._add_stop_args(pk)
        pk.set_defaults(_cmd=self._alias_run, _alias_action="stop")

        pl = sp.add_parser("list", help="List known servers (alias of 'server list')")
        ServerCommand._add_list_args(pl)
        pl.set_defaults(_cmd=self._alias_run, _alias_action="list")

    # -------- Execution --------
    def run(self, args: argparse.Namespace) -> int:
        action = args.action
        if action == "start":
            return self._start(args)
        if action == "stop":
            return self._stop(args)
        if action == "list":
            return self._list(args)
        print("Unknown action:", action)
        return 2

    def _alias_run(self, args: argparse.Namespace) -> int:
        # Inject action for top-level aliases and delegate to run()
        setattr(args, "action", getattr(args, "_alias_action", ""))
        return self.run(args)

    def _start(self, args: argparse.Namespace) -> int:
        try:
            meta = {}
            if args.meta:
                try:
                    meta = json.loads(args.meta)
                except Exception:
                    meta = {"raw": args.meta}

            mgr = ComfyServerManager(registry_path=args.registry)
            opts = {
                "host": args.host,
                "port": args.port,
                "input_dir": args.input_dir,
                "output_dir": args.output_dir,
                "temp_dir": args.temp_dir,
                "user_dir": args.user_dir,
                "tags": (["farm"] if args.use_farm else ["local"]),
                "meta": meta,
            }
            # prune Nones
            opts = {k: v for k, v in opts.items() if v not in (None, "")}

            handle = mgr.start(opts)
            info = {
                "id": handle.id,
                "pid": handle.pid,
                "base_url": handle.base_url,
                "host": handle.host,
                "port": handle.port,
                "log": handle.log_path,
            }
            if getattr(args, "verbose", False):
                print("[server] started:", json.dumps(info, indent=2))
            else:
                print(handle.base_url)
            return 0
        except Exception as e:
            print("[server] start error:", e)
            return 1

    def _stop(self, args: argparse.Namespace) -> int:
        reg = ServerRegistry(args.registry) if args.registry else ServerRegistry()
        key = (args.url or "").strip()
        if not key:
            print("[server] stop: --url (or id) is required")
            return 2

        rec = reg.find_by_url_or_id(key)
        if not rec:
            print("[server] stop: not found in registry:", key)
            return 3

        # Only allow stopping if it's on this host (safety)
        target_host = rec.host or "127.0.0.1"
        local_hosts = {socket.gethostname(), "localhost", "127.0.0.1"}
        try:
            local_hosts.add(socket.gethostbyname(socket.gethostname()))
        except Exception:
            pass

        if target_host not in local_hosts:
            print(f"[server] stop: refusing to terminate remote host '{target_host}'.")
            print("          Run this command on the host that owns the process.")
            return 4

        ok = ComfyServerManager.kill_local_pid(rec.pid)
        if ok:
            try:
                reg.register_stop(rec.id)
            except Exception:
                pass
            print(f"[server] stopped pid={rec.pid} url={rec.base_url}")
            return 0
        print(f"[server] could not stop pid={rec.pid} url={rec.base_url}")
        return 5

    def _list(self, args: argparse.Namespace) -> int:
        reg = ServerRegistry(args.registry) if args.registry else ServerRegistry()
        recs = reg.list_latest()
        if getattr(args, "json", False):
            print(json.dumps([r.to_dict() for r in recs], indent=2))
            return 0

        if not recs:
            print("(no servers)")
            return 0

        def pad(s, n): return (s or "")[:n].ljust(n)
        print(pad("STATE", 9), pad("ID", 12), pad("HOST", 16), pad("PORT", 6), pad("PID", 8), "URL")
        for r in recs:
            print(pad(r.state, 9), pad(r.id[:12], 12), pad(r.host, 16), pad(str(r.port), 6), pad(str(r.pid), 8), r.base_url)
        return 0
