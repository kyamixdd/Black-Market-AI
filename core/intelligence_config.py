"""Validated intelligence-mode configuration with safe runtime loading.

Modes tune assistant reasoning depth and bounded tool planning only. They do not
change exchange permissions or enable live trading.
"""
from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .runtime_settings_store import load_runtime_settings


class IntelligenceMode(str, Enum):
    BALANCED = "balanced"
    FAST = "fast"
    RESEARCH = "research"
    CONSERVATIVE = "conservative"


class IntelligenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: IntelligenceMode = IntelligenceMode.BALANCED
    max_tool_calls: int = Field(default=3, ge=1, le=3)
    memory_enabled: bool = True
    feedback_enabled: bool = True
    provider_enabled: bool = True
    response_detail: str = Field(default="normal")

    @field_validator("response_detail")
    @classmethod
    def validate_response_detail(cls, value: str) -> str:
        allowed = {"brief", "normal", "detailed"}
        if value not in allowed:
            raise ValueError("response_detail must be brief, normal, or detailed")
        return value


_MODE_DEFAULTS: dict[IntelligenceMode, dict[str, Any]] = {
    IntelligenceMode.BALANCED: {
        "max_tool_calls": 3, "memory_enabled": True, "feedback_enabled": True,
        "provider_enabled": True, "response_detail": "normal",
    },
    IntelligenceMode.FAST: {
        "max_tool_calls": 1, "memory_enabled": False, "feedback_enabled": True,
        "provider_enabled": False, "response_detail": "brief",
    },
    IntelligenceMode.RESEARCH: {
        "max_tool_calls": 3, "memory_enabled": True, "feedback_enabled": True,
        "provider_enabled": True, "response_detail": "detailed",
    },
    IntelligenceMode.CONSERVATIVE: {
        "max_tool_calls": 1, "memory_enabled": True, "feedback_enabled": False,
        "provider_enabled": False, "response_detail": "normal",
    },
}


def config_for_mode(mode: IntelligenceMode | str) -> IntelligenceConfig:
    """Return the validated preset for a supported mode."""
    parsed_mode = IntelligenceMode(mode)
    return IntelligenceConfig(mode=parsed_mode, **_MODE_DEFAULTS[parsed_mode])


def load_intelligence_config(
    overrides: dict[str, Any] | None = None,
) -> IntelligenceConfig:
    """Load validated config from persisted runtime settings and env overrides.

    Precedence: explicit overrides > environment > persisted settings > preset.
    Invalid persisted configuration raises RuntimeError instead of silently
    changing the active mode. Environment mode is intentionally allow-listed.
    """
    persisted = load_runtime_settings()
    raw_mode = os.environ.get(
        "BLACKMARKET_INTELLIGENCE_MODE",
        (overrides or {}).get("mode", persisted.get("intelligence_mode", "balanced")),
    )
    try:
        mode = IntelligenceMode(raw_mode)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Unsupported intelligence mode configuration.") from exc

    values = _MODE_DEFAULTS[mode].copy()
    values["mode"] = mode
    persisted_config = persisted.get("intelligence_config", {})
    if persisted_config:
        if not isinstance(persisted_config, dict):
            raise RuntimeError("Persisted intelligence_config must be an object.")
        values.update(persisted_config)
    if overrides:
        values.update(overrides)
    values["mode"] = mode
    try:
        return IntelligenceConfig.model_validate(values)
    except Exception as exc:
        raise RuntimeError("Invalid intelligence configuration.") from exc


@lru_cache(maxsize=1)
def get_runtime_intelligence_config() -> IntelligenceConfig:
    """Cached process-level configuration; clear cache to reload after changes."""
    return load_intelligence_config()


def reload_runtime_intelligence_config() -> IntelligenceConfig:
    get_runtime_intelligence_config.cache_clear()
    return get_runtime_intelligence_config()
