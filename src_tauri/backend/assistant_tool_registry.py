"""Central allowlisted registry for assistant-accessible application tools.

The registry is the only runtime dispatch boundary for assistant tools. Tool
implementations remain in the existing deterministic application services.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from uuid import uuid4

from .assistant_intelligence import TOOL_NAMES, execute_tool


class ToolRegistryError(Exception):
    """Safe, structured tool registry failure."""

    def __init__(self, code: str, message: str, *, status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    required_permissions: frozenset[str]
    timeout_seconds: float
    read_only: bool
    changes_state: bool
    available: bool = True


_BASE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string", "minLength": 2, "maxLength": 20},
        "market": {"type": "string", "enum": ["SPOT", "FUTURES"]},
        "timeframe": {"type": "string", "enum": ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]},
    },
    "required": ["symbol", "market", "timeframe"],
    "additionalProperties": False,
}
_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["tool", "status", "data", "source"],
    "properties": {
        "tool": {"type": "string"},
        "status": {"type": "string", "enum": ["available", "unavailable"]},
        "data": {},
        "source": {"type": "string"},
    },
}


_TOOL_DESCRIPTIONS = {
    "market_snapshot": "Read the current local market snapshot and data freshness.",
    "historical_candles": "Read a bounded historical candle series for an asset.",
    "indicator_report": "Read existing backend technical indicator and analytics results.",
    "scanner_status": "Read the existing market scanner status.",
    "signal_report": "Read recent signals for one asset.",
    "strategy_report": "Read strategy metrics and configured strategy weights.",
    "paper_account": "Read the paper-trading account summary only.",
    "open_positions": "Read open paper-trading positions for one asset.",
    "trade_history": "Read recent closed paper-trading records for one asset.",
    "risk_status": "Read existing paper-trading risk metrics and limits.",
    "learning_evaluation": "Read model learning status and recent evaluation predictions.",
}


def _permission_for(tool_id: str) -> str:
    if tool_id in {"paper_account", "open_positions", "trade_history"}:
        return "paper:read"
    if tool_id in {"strategy_report", "learning_evaluation"}:
        return "analytics:read"
    if tool_id == "risk_status":
        return "risk:read"
    return "market:read"


def _build_default_specs() -> dict[str, ToolSpec]:
    specs = {}
    for tool_id in TOOL_NAMES:
        specs[tool_id] = ToolSpec(
            tool_id=tool_id,
            description=_TOOL_DESCRIPTIONS[tool_id],
            input_schema=_BASE_INPUT_SCHEMA,
            output_schema=_OUTPUT_SCHEMA,
            required_permissions=frozenset({_permission_for(tool_id)}),
            timeout_seconds=15.0,
            read_only=True,
            changes_state=False,
        )
    return specs


class AssistantToolRegistry:
    """Validated dispatch for registered, bounded, read-only assistant tools."""

    def __init__(
        self,
        executor: Callable[..., Awaitable[dict[str, Any]]] = execute_tool,
        specs: dict[str, ToolSpec] | None = None,
    ):
        self._executor = executor
        self._specs = dict(specs or _build_default_specs())

    def list_tools(self) -> list[dict[str, Any]]:
        """Return safe tool metadata without implementation details."""
        return [
            {
                "tool_id": spec.tool_id,
                "description": spec.description,
                "input_schema": spec.input_schema,
                "output_schema": spec.output_schema,
                "required_permissions": sorted(spec.required_permissions),
                "timeout_seconds": spec.timeout_seconds,
                "read_only": spec.read_only,
                "changes_state": spec.changes_state,
                "available": spec.available,
            }
            for spec in self._specs.values()
        ]

    def get_spec(self, tool_id: str) -> ToolSpec:
        spec = self._specs.get(tool_id)
        if spec is None:
            raise ToolRegistryError("unknown_tool", "Requested assistant tool is not registered.")
        if not spec.available:
            raise ToolRegistryError("tool_unavailable", "Requested assistant tool is currently unavailable.", status_code=503)
        return spec

    @staticmethod
    def validate_input(spec: ToolSpec, arguments: dict[str, Any]) -> dict[str, str]:
        if not isinstance(arguments, dict):
            raise ToolRegistryError("invalid_arguments", "Tool arguments must be an object.")
        properties = spec.input_schema.get("properties", {})
        required = set(spec.input_schema.get("required", []))
        if spec.input_schema.get("additionalProperties") is False and set(arguments) - set(properties):
            raise ToolRegistryError("invalid_arguments", "Tool arguments contain unsupported fields.")
        missing = required - set(arguments)
        if missing:
            raise ToolRegistryError("missing_parameters", "Required tool parameters are missing.")
        symbol = arguments.get("symbol")
        market = arguments.get("market")
        timeframe = arguments.get("timeframe")
        if not isinstance(symbol, str) or not 2 <= len(symbol.strip()) <= 20:
            raise ToolRegistryError("invalid_symbol", "Symbol must contain 2 to 20 characters.")
        if not isinstance(market, str) or market not in {"SPOT", "FUTURES"}:
            raise ToolRegistryError("invalid_market", "Market must be SPOT or FUTURES.")
        if not isinstance(timeframe, str) or timeframe not in {
            "1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"
        }:
            raise ToolRegistryError("invalid_timeframe", "Unsupported timeframe.")
        return {"symbol": symbol.strip().upper(), "market": market, "timeframe": timeframe}

    async def invoke(
        self,
        bridge: Any,
        tool_id: str,
        arguments: dict[str, Any],
        *,
        permissions: set[str] | frozenset[str] | None = None,
    ) -> dict[str, Any]:
        spec = self.get_spec(tool_id)
        # The current assistant API authenticates a local bearer session but does
        # not yet expose granular user scopes. Runtime grants only read scopes.
        granted = permissions if permissions is not None else {
            "market:read", "paper:read", "analytics:read", "risk:read"
        }
        if not spec.required_permissions.issubset(granted):
            raise ToolRegistryError("permission_denied", "Permission denied for this assistant tool.", status_code=403)
        if not spec.read_only or spec.changes_state:
            raise ToolRegistryError("unsafe_tool", "State-changing tools are not enabled for assistant execution.", status_code=403)
        validated = self.validate_input(spec, arguments)
        execution_id = uuid4().hex
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self._executor(bridge, tool_id, validated["symbol"], validated["market"], validated["timeframe"]),
                timeout=spec.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise ToolRegistryError("tool_timeout", "Assistant tool exceeded its execution timeout.", status_code=504) from exc
        except ValueError as exc:
            message = str(exc)
            lowered = message.lower()
            if "symbol" in lowered:
                code = "invalid_symbol"
            elif "market" in lowered:
                code = "invalid_market"
            elif "timeframe" in lowered:
                code = "invalid_timeframe"
            else:
                code = "tool_validation_failed"
            raise ToolRegistryError(code, message) from exc
        except Exception as exc:
            raise ToolRegistryError("tool_execution_failed", "Assistant tool execution failed safely.", status_code=502) from exc
        if not isinstance(result, dict):
            raise ToolRegistryError("invalid_tool_result", "Assistant tool returned an invalid result.", status_code=502)
        if result.get("tool") != tool_id or result.get("status") not in {"available", "unavailable"}:
            raise ToolRegistryError("invalid_tool_result", "Assistant tool returned a result that failed validation.", status_code=502)
        if "source" not in result or "data" not in result:
            raise ToolRegistryError("invalid_tool_result", "Assistant tool result is missing required fields.", status_code=502)
        return {
            **result,
            "execution": {
                "execution_id": execution_id,
                "tool_id": tool_id,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "read_only": spec.read_only,
                "changes_state": spec.changes_state,
            },
        }


def create_default_registry() -> AssistantToolRegistry:
    """Create the registry for the existing deterministic evidence functions."""
    return AssistantToolRegistry(executor=execute_tool)
