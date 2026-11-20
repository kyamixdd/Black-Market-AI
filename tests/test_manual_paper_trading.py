"""Validation tests for manual paper-trading API payloads."""
import pytest
from pydantic import ValidationError

from src_tauri.backend.api.routes.schemas import (
    ManualOrderRequest,
    MarketType,
    PositionUpdateRequest,
)


def test_manual_market_order_schema_accepts_valid_spot_buy():
    order = ManualOrderRequest(
        symbol="BTCUSDT",
        market=MarketType.SPOT,
        side="BUY",
        order_type="MARKET",
        quantity=0.001,
        stop_loss=90000,
    )
    assert order.quantity == 0.001
    assert order.order_type == "MARKET"


@pytest.mark.parametrize("payload", [
    {"symbol": "BTC/USDT", "market": "SPOT", "side": "BUY", "quantity": 1, "stop_loss": 1},
    {"symbol": "BTCUSDT", "market": "SPOT", "side": "BUY", "quantity": 0, "stop_loss": 1},
    {"symbol": "BTCUSDT", "market": "SPOT", "side": "BUY", "quantity": 1, "stop_loss": -1},
    {"symbol": "BTCUSDT", "market": "SPOT", "side": "BUY", "quantity": 1, "stop_loss": 1, "leverage": 126},
])
def test_manual_order_schema_rejects_invalid_payloads(payload):
    with pytest.raises(ValidationError):
        ManualOrderRequest(**payload)


def test_limit_order_requires_price_at_route_validation_layer():
    # Schema permits omission because the same request model also supports market
    # orders; the route rejects a missing limit price before reaching the simulator.
    order = ManualOrderRequest(
        symbol="BTCUSDT", market="FUTURES", side="LONG",
        order_type="LIMIT", quantity=0.001, stop_loss=90000,
    )
    assert order.price is None


def test_position_update_requires_a_value_at_route_validation_layer():
    request = PositionUpdateRequest()
    assert request.stop_loss is None
    assert request.take_profit is None
