"""Atomic, private persistence for non-secret runtime settings."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from config import DATA_DIR

SETTINGS_PATH = Path(DATA_DIR) / "runtime_settings.json"


def load_runtime_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        with SETTINGS_PATH.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read persisted runtime settings: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Persisted runtime settings must be a JSON object.")
    return value


def save_runtime_settings(settings: dict[str, Any]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".runtime-settings-", suffix=".tmp", dir=SETTINGS_PATH.parent)
    try:
        try:
            os.fchmod(fd, 0o600)
        except (AttributeError, OSError):
            pass
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, SETTINGS_PATH)
        try:
            os.chmod(SETTINGS_PATH, 0o600)
        except OSError:
            pass
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
