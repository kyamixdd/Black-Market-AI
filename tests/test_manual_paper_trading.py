"""Validation tests for manual paper-trading API payloads."""
from datetime import datetime, timezone

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


def test_missing_limit_price_returns_validation_error_instead_of_type_error():
    from fastapi import HTTPException
    from src_tauri.backend.api.routes.trades import _validated_manual_signal

    order = ManualOrderRequest(
        symbol="BTCUSDT",
        market="FUTURES",
        side="LONG",
        order_type="LIMIT",
        quantity=0.001,
        stop_loss=90000,
    )

    class FakeBridge:
        @staticmethod
        def get_market_snapshot(_symbol, _market):
            return {"price": 100000.0, "data_freshness": "LIVE"}

    with pytest.raises(HTTPException) as error:
        _validated_manual_signal(order, FakeBridge())

    assert error.value.status_code == 422
    assert error.value.detail == "Limit orders require a price."


@pytest.mark.parametrize("field", ["quantity", "price", "stop_loss", "take_profit", "leverage"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_manual_order_rejects_non_finite_numeric_values(field, value):
    payload = {
        "symbol": "BTCUSDT",
        "market": "FUTURES",
        "side": "LONG",
        "quantity": 0.001,
        "stop_loss": 90000,
    }
    payload[field] = value
    with pytest.raises(ValidationError):
        ManualOrderRequest(**payload)


@pytest.mark.parametrize("market_price", [None, "not-a-price", float("nan"), float("inf"), 0, -1])
def test_manual_trade_rejects_invalid_market_snapshot_without_server_error(market_price):
    from fastapi import HTTPException
    from src_tauri.backend.api.routes.trades import _validated_manual_signal

    order = ManualOrderRequest(
        symbol="BTCUSDT", market="SPOT", side="BUY",
        quantity=0.001, stop_loss=90000,
    )

    class FakeBridge:
        @staticmethod
        def get_market_snapshot(_symbol, _market):
            return {"price": market_price}

    with pytest.raises(HTTPException) as error:
        _validated_manual_signal(order, FakeBridge())
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_cancel_inflight_order_returns_conflict_not_not_found(monkeypatch):
    from fastapi import HTTPException
    from src_tauri.backend.api.routes import trades

    class FakeSimulator:
        open_orders = {"ORD-FILLING": {"order_id": "ORD-FILLING", "status": "FILLING"}}

        async def cancel_limit_order(self, _order_id):
            raise AssertionError("A filling order must not be sent to cancellation.")

    class FakeBridge:
        simulator = FakeSimulator()

    monkeypatch.setattr(trades, "get_bridge", lambda: FakeBridge())
    with pytest.raises(HTTPException) as error:
        await trades.cancel_order("ORD-FILLING")
    assert error.value.status_code == 409


@pytest.mark.parametrize("snapshot", [
    None,
    {"price": 100000, "data_freshness": "STALE", "data_age_seconds": 600},
    {"price": 100000, "data_freshness": "UNKNOWN", "data_age_seconds": None},
    {"price": 100000, "data_freshness": "LIVE", "data_age_seconds": float("inf")},
    {"price": float("nan"), "data_freshness": "LIVE", "data_age_seconds": 1},
])
def test_manual_trade_rejects_stale_or_invalid_market_snapshots(snapshot):
    from fastapi import HTTPException
    from src_tauri.backend.api.routes.trades import _validated_manual_signal

    order = ManualOrderRequest(
        symbol="BTCUSDT", market="SPOT", side="BUY",
        quantity=0.001, stop_loss=90000,
    )

    class FakeBridge:
        @staticmethod
        def get_market_snapshot(_symbol, _market):
            return snapshot

        class simulator:
            @staticmethod
            def get_balance(_market):
                return 500.0

            class risk_manager:
                @staticmethod
                def calculate_position_size(balance, risk):
                    return 1.0

    with pytest.raises(HTTPException) as error:
        _validated_manual_signal(order, FakeBridge())
    assert error.value.status_code == 409


def test_position_risk_update_persists_trailing_stop_and_rolls_back_on_failure(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src_tauri.backend.api.routes import positions

    saved = []

    class FakeSimulator:
        spot_positions = {
            "POS-TRAIL": {
                "position_id": "POS-TRAIL",
                "symbol": "BTCUSDT",
                "market": "SPOT",
                "side": "LONG",
                "entry_price": 100.0,
                "current_price": 120.0,
                "stop_loss": 90.0,
                "take_profit": 140.0,
                "status": "OPEN",
            }
        }
        futures_positions = {}

        @staticmethod
        def persist_position_callback(position):
            saved.append(dict(position))

    class FakeBridge:
        simulator = FakeSimulator()

    monkeypatch.setattr(positions, "get_bridge", lambda: FakeBridge())
    app = FastAPI()
    app.include_router(positions.router, prefix="/api")

    with TestClient(app) as client:
        response = client.patch("/api/positions/POS-TRAIL", json={"stop_loss": 110.0})
        assert response.status_code == 200
        assert FakeBridge.simulator.spot_positions["POS-TRAIL"]["stop_loss"] == 110.0
        assert saved[-1]["stop_loss"] == 110.0

        FakeBridge.simulator.persist_position_callback = lambda _position: (_ for _ in ()).throw(RuntimeError("db down"))
        response = client.patch("/api/positions/POS-TRAIL", json={"stop_loss": 115.0})
        assert response.status_code == 503
        assert FakeBridge.simulator.spot_positions["POS-TRAIL"]["stop_loss"] == 110.0


def test_open_orders_endpoint_returns_typed_order_contract(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src_tauri.backend.api.routes import trades

    class FakeSimulator:
        open_orders = {
            "ORD-TYPED": {
                "order_id": "ORD-TYPED",
                "symbol": "BTCUSDT",
                "market": "SPOT",
                "side": "BUY",
                "entry_price": 100.0,
                "amount": 0.01,
                "stop_loss": 95.0,
                "take_profit": 110.0,
                "leverage": 1.0,
                "order_type": "LIMIT",
                "status": "RECOVERY_REVIEW",
                "created_at": datetime.now(timezone.utc),
                "signal_id": "MANUAL",
                "filled_amount": 0.0,
                "avg_fill_price": 0.0,
                "fee": 0.0,
                "strategy": "MANUAL",
            }
        }

    class FakeBridge:
        simulator = FakeSimulator()

    monkeypatch.setattr(trades, "get_bridge", lambda: FakeBridge())
    app = FastAPI()
    app.include_router(trades.router, prefix="/api")

    with TestClient(app) as client:
        response = client.get("/api/trades/orders")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["orders"][0]["order_id"] == "ORD-TYPED"
        assert payload["orders"][0]["status"] == "RECOVERY_REVIEW"


@pytest.mark.parametrize("payload", [
    {"quantity": 0},
    {"quantity": -1},
    {"quantity": float("nan")},
    {"quantity": float("inf")},
])
def test_partial_close_request_rejects_invalid_quantity(payload):
    from src_tauri.backend.api.routes.schemas import PartialCloseRequest
    with pytest.raises(ValidationError):
        PartialCloseRequest(**payload)


def test_position_update_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        PositionUpdateRequest(stop_loss=90.0, trailing_mode=True)
