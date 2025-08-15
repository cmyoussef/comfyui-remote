"""Output handler."""
from __future__ import annotations
import json, time
from pathlib import Path
from typing import Dict, Any, Optional

class OutputHandler:
    def __init__(self, root: Optional[str] = None) -> None:
        self._root = Path(root) if root else Path.cwd() / ".comfy_outputs"
        self._root.mkdir(parents=True, exist_ok=True)

    def plan_outputs(self, graph) -> dict:
        return {}

    def store(self, handle_id: str, artifacts: Dict[str, Any]) -> Dict[str, Any]:
        """Write a manifest and return paths + basic echo of artifacts."""
        stamp = time.strftime("%Y%m%d-%H%M%S")
        manifest = {
            "handle_id": handle_id,
            "timestamp": stamp,
            **artifacts,
        }
        path = self._root / f"{handle_id}.json"
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return {"manifest": str(path), **artifacts}

    def paths(self, handle_id: str) -> Dict[str, Any]:
        path = self._root / f"{handle_id}.json"
        return {"manifest": str(path)}
