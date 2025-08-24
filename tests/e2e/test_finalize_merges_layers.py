# tests/e2e/test_finalize_merges_layers.py
from pathlib import Path
import os
import comfyui_remote as _pkg  # type: ignore
from comfyui_remote.config.config_manager import ConfigManager

def test_finalize_merges_layers(monkeypatch):
    pkg_dir = Path(_pkg.__file__).resolve().parent
    controller = pkg_dir / "config" / "defaults" / "default.json"

    monkeypatch.setenv("COMFY_CONFIG", str(controller))

    mgr = ConfigManager()
    cfg = mgr.finalize()

    sources = mgr.debug_controller_sources()
    assert sources["controller"], "expected a controller to be used"
    assert len(sources["yaml_layers"]) >= 1, "expected at least one YAML layer"
    assert len(sources["json_layers"]) >= 1, "expected at least one JSON layer"

    merged_yaml = mgr.debug_comfy_yaml_dict(expand=False)
    assert isinstance(merged_yaml, dict)
    assert "server" in merged_yaml and "paths" in merged_yaml

    snap = mgr.debug_expanded_yaml_text(cfg)
    assert "paths:" in snap
    assert "server:" in snap
