"""Durable UTC-day opening equity baseline for daily risk protection."""
from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from config import DATA_DIR

STATE_PATH = Path(DATA_DIR) / "daily_equity_state.json"


def load_daily_equity_state(path: Path = STATE_PATH) -> dict[str, Any] | None:
    """Load a validated baseline; malformed persisted risk state fails startup."""
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
        state_date = date.fromisoformat(state["date"])
        equity = float(state["equity"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise RuntimeError(f"Could not load daily equity risk state: {exc}") from exc
    if not math.isfinite(equity) or equity <= 0:
        raise RuntimeError("Persisted daily equity baseline must be finite and positive.")
    return {"date": state_date, "equity": equity}


def save_daily_equity_state(day: str, equity: float, path: Path = STATE_PATH) -> None:
    """Atomically persist the daily baseline with private file permissions."""
    parsed_day = date.fromisoformat(day)
    value = float(equity)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Daily equity baseline must be finite and positive.")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".daily-equity-", suffix=".tmp", dir=path.parent)
    try:
        try:
            os.fchmod(fd, 0o600)
        except (AttributeError, OSError):
            pass
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"date": parsed_day.isoformat(), "equity": value}, handle, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
