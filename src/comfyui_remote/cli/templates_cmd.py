"""CLI: templates (minimal placeholder to satisfy CLI)."""
from __future__ import annotations


class TemplatesCommand:
    @staticmethod
    def configure(p):
        p.add_argument("action", choices=("list", "show"), nargs="?", default="list")
        p.add_argument("template_id", nargs="?", help="Template id for 'show'")

    def run(self, args) -> int:
        # Minimal, non-failing placeholder (you can wire a real repo later)
        if args.action == "list":
            print("[]")
            return 0
        if args.action == "show":
            print("{}")
            return 0
        return 0
