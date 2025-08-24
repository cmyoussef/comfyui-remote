# tests/e2e/test_config_controller_presence_and_minified_outputs.py
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

def _ensure_src_on_path() -> Path:
    here = Path(__file__).resolve()
    repo = here.parents[2]
    src = repo / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return src

_ = _ensure_src_on_path()

try:
    import yaml  # type: ignore
    HAVE_YAML = True
except Exception:
    HAVE_YAML = False

import comfyui_remote as _pkg  # type: ignore
from comfyui_remote.config.config_manager import ConfigManager  # type: ignore


def _pp(title: str, value: Any) -> None:
    print(f"\n=== {title} ===")
    print(value)


@pytest.mark.skipif(not HAVE_YAML, reason="PyYAML is required for YAML-side merge/debug.")
def test_controller_presence_and_minified(monkeypatch: pytest.MonkeyPatch) -> None:
    pkg_dir = Path(_pkg.__file__).resolve().parent
    controller = pkg_dir / "config" / "defaults" / "default.json"
    if not controller.exists():
        pytest.skip(f"default.json not found at {controller}")

    monkeypatch.setenv("COMFY_CONFIG", str(controller))
    monkeypatch.setenv("PKG", str(pkg_dir))
    monkeypatch.setenv("OS", "windows" if os.name == "nt" else "linux")
    monkeypatch.setenv("HOME", str(Path.home().resolve()))

    mgr = ConfigManager()
    cfg = mgr.finalize()

    # Presence listing for JSON/YAML stacks
    listing = mgr.debug_controller_listing()
    print("\n--- JSON layers (Remote-side) ---")
    for r in listing["json"]:
        status = "FOUND" if r["exists"] else "MISSING"
        print(f"[JSON] {r['name']:<8} | {status} | pattern={r['pattern']!s}"
              f"{' | path=' + str(r['resolved']) if r['exists'] else ''}")

    print("\n--- YAML layers (Comfy-side) ---")
    for r in listing["yaml"]:
        status = "FOUND" if r["exists"] else "MISSING"
        print(f"[YAML] {r['name']:<8} | {status} | pattern={r['pattern']!s}"
              f"{' | path=' + str(r['resolved']) if r['exists'] else ''}")

    # Sanity: base layer should exist on both sides in the repo
    assert any((r["name"] == "base" and r["exists"]) for r in listing["json"]), "Expected base JSON layer to exist."
    assert any((r["name"] == "base" and r["exists"]) for r in listing["yaml"]), "Expected base YAML layer to exist."

    # Compressed/minified merged views
    merged_json = mgr._last_merged_remote_json  # internal snapshot; read-only in tests
    merged_yaml = mgr.debug_comfy_yaml_dict(expand=False)

    json_min = json.dumps(merged_json, separators=(",", ":"), ensure_ascii=False, indent=2)
    yaml_min = yaml.safe_dump(merged_yaml, default_flow_style=False, sort_keys=False, indent=2)

    _pp("COMPRESSED JSON (Remote merged)", json_min)
    _pp("COMPRESSED YAML (Comfy merged)", yaml_min.strip())

    assert isinstance(merged_json, dict)
    assert isinstance(merged_yaml, dict)

    # Expanded ComfyConfig snapshot includes expected top-level sections
    snap = mgr.debug_expanded_yaml_text(cfg)
    assert "paths:" in snap
    assert "server:" in snap
