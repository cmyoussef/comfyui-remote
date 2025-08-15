"""Template repository."""
import os
import json
from typing import List
from .model import WorkflowTemplate


class TemplateRepository:
    def __init__(self, root_dir: str) -> None:
        self._root = root_dir

    def list(self) -> List[WorkflowTemplate]:
        out = []
        if not os.path.isdir(self._root):
            return out
        for fn in os.listdir(self._root):
            if not fn.endswith(".json"): continue
            p = os.path.join(self._root, fn)
            meta = {"source": "fs"}
            defaults = {}
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                defaults = data.get("_defaults", {})
            except Exception:
                pass
            out.append(WorkflowTemplate(
                id=os.path.splitext(fn)[0], name=os.path.splitext(fn)[0],
                meta=meta, defaults=defaults, path=p
            ))
        return out

    def get(self, template_id: str) -> WorkflowTemplate:
        p = os.path.join(self._root, f"{template_id}.json")
        with open(p, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception:
                data = {}
        defaults = data.get("_defaults", {})
        return WorkflowTemplate(
            id=template_id, name=template_id, meta={"source":"fs"},
            defaults=defaults, path=p
        )
