from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from fastapi import HTTPException

from src_tauri.backend.bridge.orchestrator_bridge import OrchestratorBridge


def test_settings_report_telegram_configuration_without_exposing_credentials(monkeypatch):
    import config

    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "test-secret-token")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "test-chat-id")
    bridge = object.__new__(OrchestratorBridge)
    bridge.simulator = SimpleNamespace(initial_spot_balance=123.0, initial_futures_balance=321.0)
    bridge.risk_manager = SimpleNamespace(
        max_risk_pct=0.5,
        max_daily_loss_pct=2.0,
        max_open_risk_pct=2.25,
        max_leverage=3.0,
        max_spot_positions=5,
        max_futures_positions=5,
    )

    settings = bridge.get_settings()

    assert settings["spot_initial_balance"] == 123.0
    assert settings["futures_initial_balance"] == 321.0
    assert settings["risk_max_total_open_pct"] == 2.25
    assert settings["telegram_bot_token_configured"] is True
    assert settings["telegram_chat_id_configured"] is True
    assert "telegram_bot_token" not in settings
    assert "telegram_chat_id" not in settings
    assert "test-secret-token" not in repr(settings)
    assert "test-chat-id" not in repr(settings)


def test_portfolio_uses_configured_baselines_and_utc_periods():
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    previous_month = month_start - timedelta(days=1)
    simulator = SimpleNamespace(
        initial_spot_balance=100.0,
        initial_futures_balance=250.0,
        spot_positions={"spot": {"unrealized_pnl": 5.0}},
        futures_positions={"futures": {"unrealized_pnl": 10.0}},
        get_balance=lambda market: 115.0 if market == "SPOT" else 255.0,
    )
    bridge = object.__new__(OrchestratorBridge)
    bridge.simulator = simulator
    bridge._all_closed_trades = lambda: [
        {"pnl": 7.0, "closed_at": now},
        {"pnl": 5.0, "closed_at": month_start},
        {"pnl": 2.0, "closed_at": previous_month},
    ]
    bridge.get_trade_statistics = lambda: {"max_drawdown_pct": 1.5}

    portfolio = bridge.get_portfolio_summary()

    assert portfolio["spot_pnl"] == 20.0
    assert portfolio["futures_pnl"] == 15.0
    assert portfolio["total_pnl"] == 35.0
    assert portfolio["spot_return_pct"] == 20.0
    assert portfolio["futures_return_pct"] == 6.0
    assert portfolio["daily_pnl"] == 7.0
    assert portfolio["monthly_pnl"] == 12.0
    assert portfolio["realized_pnl"] == 14.0
    assert portfolio["unrealized_pnl"] == 15.0


@pytest.mark.asyncio
async def test_settings_update_returns_explicit_unsupported_response(monkeypatch):
    from src_tauri.backend.api.routes import settings as settings_routes
    from src_tauri.backend.api.routes.schemas import SettingsRequest

    bridge = object.__new__(OrchestratorBridge)
    monkeypatch.setattr(settings_routes, "get_bridge", lambda: bridge)

    with pytest.raises(HTTPException) as error:
        await settings_routes.update_settings(SettingsRequest(risk_max_total_open_pct=1000))

    assert error.value.status_code == 501
    assert error.value.detail == "Settings updates are not supported."
