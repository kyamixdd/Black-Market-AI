"""Validated intelligence-mode configuration with safe runtime loading."""
from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .runtime_settings_store import load_runtime_settings, save_runtime_settings


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
    response_detail: str = "normal"

    @field_validator("response_detail")
    @classmethod
    def validate_response_detail(cls, value: str) -> str:
        if value not in {"brief", "normal", "detailed"}:
            raise ValueError("response_detail must be brief, normal, or detailed")
        return value


_MODE_DEFAULTS: dict[IntelligenceMode, dict[str, Any]] = {
    IntelligenceMode.BALANCED: {"max_tool_calls": 3, "memory_enabled": True, "feedback_enabled": True, "provider_enabled": True, "response_detail": "normal"},
    IntelligenceMode.FAST: {"max_tool_calls": 1, "memory_enabled": False, "feedback_enabled": True, "provider_enabled": False, "response_detail": "brief"},
    IntelligenceMode.RESEARCH: {"max_tool_calls": 3, "memory_enabled": True, "feedback_enabled": True, "provider_enabled": True, "response_detail": "detailed"},
    IntelligenceMode.CONSERVATIVE: {"max_tool_calls": 1, "memory_enabled": True, "feedback_enabled": False, "provider_enabled": False, "response_detail": "normal"},
}


def config_for_mode(mode: IntelligenceMode | str) -> IntelligenceConfig:
    parsed_mode = IntelligenceMode(mode)
    return IntelligenceConfig(mode=parsed_mode, **_MODE_DEFAULTS[parsed_mode])


def load_intelligence_config(overrides: dict[str, Any] | None = None) -> IntelligenceConfig:
    """Precedence: explicit overrides > environment > persisted values > preset."""
    persisted = load_runtime_settings()
    persisted_mode = persisted.get("intelligence_mode", "balanced")
    env_mode = os.environ.get("BLACKMARKET_INTELLIGENCE_MODE")
    explicit_mode = (overrides or {}).get("mode")
    raw_mode = explicit_mode if explicit_mode is not None else env_mode if env_mode is not None else persisted_mode
    try:
        mode = IntelligenceMode(raw_mode)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Unsupported intelligence mode configuration.") from exc

    values = _MODE_DEFAULTS[mode].copy()
    values["mode"] = mode
    persisted_config = persisted.get("intelligence_config", {})
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


def save_intelligence_config(config: IntelligenceConfig) -> IntelligenceConfig:
    """Persist a validated profile and refresh the process cache."""
    current = load_runtime_settings()
    current["intelligence_mode"] = config.mode.value
    current["intelligence_config"] = config.model_dump(mode="json", exclude={"mode"})
    save_runtime_settings(current)
    return reload_runtime_intelligence_config()


@lru_cache(maxsize=1)
def get_runtime_intelligence_config() -> IntelligenceConfig:
    return load_intelligence_config()


def reload_runtime_intelligence_config() -> IntelligenceConfig:
    get_runtime_intelligence_config.cache_clear()
    return get_runtime_intelligence_config()
