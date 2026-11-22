#!/usr/bin/env python3
"""Validate the product version across desktop, backend, and hosted package metadata."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


tauri = read_json("blackmarket-desktop/src-tauri/tauri.conf.json")
product_version = tauri.get("version")
if not isinstance(product_version, str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", product_version):
    raise SystemExit("Tauri product version is missing or invalid.")

checks: dict[str, str] = {
    "desktop npm package": read_json("blackmarket-desktop/package.json").get("version", ""),
    "desktop npm lock root": read_json("blackmarket-desktop/package-lock.json").get("packages", {}).get("", {}).get("version", ""),
    "hosted web package": read_json("blackmarket-web/package.json").get("version", ""),
}
cargo = (ROOT / "blackmarket-desktop/src-tauri/Cargo.toml").read_text(encoding="utf-8")
cargo_match = re.search(r"(?m)^version\s*=\s*\"([^\"]+)\"", cargo)
checks["Tauri Cargo package"] = cargo_match.group(1) if cargo_match else ""
cargo_lock = (ROOT / "blackmarket-desktop/src-tauri/Cargo.lock").read_text(encoding="utf-8")
app_package = re.search(r'(?m)^name = "app"\nversion = "([^"]+)"', cargo_lock)
checks["Cargo.lock app package"] = app_package.group(1) if app_package else ""

backend = (ROOT / "src_tauri/backend/main.py").read_text(encoding="utf-8")
backend_versions = set(re.findall(r'"?version"?\\s*:\\s*"([0-9]+\\.[0-9]+\\.[0-9]+)"', backend))
if backend_versions != {product_version}:
    checks["backend health version(s)"] = ", ".join(sorted(backend_versions)) or "missing"

mismatches = {name: value for name, value in checks.items() if value != product_version}
if mismatches:
    for name, value in mismatches.items():
        print(f"{name}: {value!r} (expected {product_version!r})", file=sys.stderr)
    raise SystemExit("Product version metadata is inconsistent.")

print(f"Product version metadata verified: {product_version}")
