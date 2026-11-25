"""Verify development-only websocket origins stay out of packaged CSP."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _csp(config_path: Path) -> str:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    return config["app"]["security"]["csp"]


def test_production_csp_excludes_vite_development_websocket_origins():
    csp = _csp(ROOT / "blackmarket-desktop" / "src-tauri" / "tauri.conf.json")

    assert "ws://localhost:3000" not in csp
    assert "ws://127.0.0.1:3000" not in csp
    assert "ws://127.0.0.1:8765" in csp


def test_development_csp_allows_vite_hmr_websocket_origins():
    csp = _csp(ROOT / "blackmarket-desktop" / "src-tauri" / "tauri.dev.conf.json")

    assert "ws://localhost:3000" in csp
    assert "ws://127.0.0.1:3000" in csp
