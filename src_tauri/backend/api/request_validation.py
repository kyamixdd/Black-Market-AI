"""Helpers for validating bounded JSON request bodies."""
from __future__ import annotations

import json
from typing import Any


def validate_json_payload_size(value: Any, *, label: str, max_bytes: int = 500_000) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain finite JSON values") from exc
    if len(encoded.encode("utf-8")) > max_bytes:
        raise ValueError(f"{label} exceeds the {max_bytes}-byte limit")
    return value
