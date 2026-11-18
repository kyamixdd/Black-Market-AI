"""Test Phase 7 Telegram and Terminal Dashboard."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from notifications.telegram_client import TelegramClient
from terminal.dashboard import DashboardApp


class TestTelegramClient:
    """Test Telegram notification client."""

    def test_init_without_config(self):
        """Test client init without token/chat_id."""
        client = TelegramClient(token="", chat_id="")
        assert client._enabled is False

    def test_init_with_config(self):
        """Test client init with token/chat_id."""
        client = TelegramClient(token="test_token", chat_id="12345")
        assert client._enabled is True
        assert client.token == "test_token"
        assert client.chat_id == "12345"

    def test_deduplication_hash(self):
        """Test message hash generation for deduplication."""
        client = TelegramClient(token="test", chat_id="123")
        h1 = client._make_hash("test message")
        h2 = client._make_hash("test message")
        h3 = client._make_hash("different message")
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 16

    def test_duplicate_detection(self):
        """Test duplicate message detection."""
        client = TelegramClient(token="test", chat_id="123")
        msg = "Test message"

        # First time - not duplicate
        assert client._is_duplicate(msg) is False
        # Second time - duplicate
        assert client._is_duplicate(msg) is True

    def test_format_duration(self):
        """Test duration formatting."""
        opened = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        closed = datetime(2024, 1, 1, 10, 30, 0, tzinfo=timezone.utc)
        duration = TelegramClient._format_duration(opened, closed)
        assert "30m" in duration or "0.5h" in duration

        # Hours
        closed2 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        duration2 = TelegramClient._format_duration(opened, closed2)
        assert "2h" in duration2 or "2.0h" in duration2

        # Days
        closed3 = datetime(2024, 1, 3, 10, 0, 0, tzinfo=timezone.utc)
        duration3 = TelegramClient._format_duration(opened, closed3)
        assert "2d" in duration3 or "2.0d" in duration3


class TestDashboardApp:
    """Test terminal dashboard app."""

    def test_dashboard_init(self):
        """Test dashboard initialization."""
        app = DashboardApp()
        assert app._paused is False
        assert app.orchestrator is None

    def test_dashboard_with_orchestrator(self):
        """Test dashboard with mock orchestrator."""
        mock_orch = MagicMock()
        mock_orch.simulator = MagicMock()
        mock_orch.simulator.get_balance.side_effect = lambda m: 500.0
        mock_orch.simulator.spot_positions = {}
        mock_orch.simulator.futures_positions = {}
        mock_orch.simulator.closed_trades = []
        mock_orch.simulator.daily_pnl = 0.0
        mock_orch.simulator.risk_manager = MagicMock()
        mock_orch.simulator.risk_manager.max_spot_positions = 5
        mock_orch.simulator.risk_manager.max_futures_positions = 5
        mock_orch.simulator.risk_manager.max_daily_loss_pct = 2.0
        mock_orch.intelligence = MagicMock()
        mock_orch.intelligence.strategy_selector = MagicMock()
        mock_orch.intelligence.strategy_selector.weights = {}
        mock_orch.intelligence.strategy_selector.regime_prefs = {}
        mock_orch.intelligence._last_signals = {}
        mock_orch.health_monitor = MagicMock()
        mock_orch.health_monitor.get_status.return_value = {"components": {}, "metrics": {}}
        mock_orch._scanning = True
        mock_orch._ws_connected = True
        mock_orch._tracked_symbols = ["BTCUSDT", "ETHUSDT"]
        mock_orch._recent_snapshots = []
        mock_orch._current_regime = "BULL_TREND"
        mock_orch._repo = MagicMock()
        mock_orch._repo.get_all_strategy_metrics.return_value = []
        mock_orch._repo.get_predictions_history.return_value = []

        app = DashboardApp(orchestrator=mock_orch)
        assert app.orchestrator is mock_orch

    def test_calc_rr(self):
        """Test risk:reward calculation."""
        mock_orch = MagicMock()
        app = DashboardApp(orchestrator=mock_orch)

        signal = {"entry": 50000, "stop_loss": 49000, "take_profit": [52000]}
        rr = app._calc_rr(signal)
        assert abs(rr - 2.0) < 0.01  # (52000-50000) / (50000-49000) = 2.0

    def test_get_signal_stats_empty(self):
        """Test signal stats with empty list."""
        mock_orch = MagicMock()
        app = DashboardApp(orchestrator=mock_orch)
        table = app._get_signal_stats([])
        # Just verify it returns a table without error
        assert table is not None


class TestTelegramNotificationTypes:
    """Test all Telegram notification type methods."""

    @pytest.mark.asyncio
    async def test_send_strong_setup(self):
        """Test strong setup notification formatting."""
        client = TelegramClient(token="test", chat_id="123")
        client._enabled = True
        client._bot = AsyncMock()

        signal = {
            "symbol": "BTCUSDT",
            "market": "SPOT",
            "direction": "LONG",
            "entry": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": [52000.0, 54000.0],
            "confidence": 0.85,
            "strategy": "momentum",
            "timeframe": "15m",
            "regime": "BULL_TREND",
        }

        with patch.object(client, '_ensure_bot', return_value=True):
            result = await client.send_strong_setup(signal)
            assert result is True
            client._bot.send_message.assert_called_once()
            call_args = client._bot.send_message.call_args
            assert "BTCUSDT" in call_args.kwargs["text"]
            assert "LONG" in call_args.kwargs["text"]
            assert "PAPER ONLY" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_send_position_opened(self):
        """Test position opened notification."""
        client = TelegramClient(token="test", chat_id="123")
        client._enabled = True
        client._bot = AsyncMock()

        position = {
            "position_id": "POS-ABC123",
            "symbol": "BTCUSDT",
            "market": "FUTURES",
            "side": "LONG",
            "entry_price": 50000.0,
            "amount": 0.1,
            "stop_loss": 49000.0,
            "take_profit": 52000.0,
            "leverage": 3.0,
            "fees_paid": 7.5,
        }

        with patch.object(client, '_ensure_bot', return_value=True):
            result = await client.send_position_opened(position)
            assert result is True
            call_args = client._bot.send_message.call_args
            assert "POSITION OPENED" in call_args.kwargs["text"]
            assert "BTCUSDT" in call_args.kwargs["text"]
            assert "3.0x" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_send_position_closed_profit(self):
        """Test position closed with profit."""
        client = TelegramClient(token="test", chat_id="123")
        client._enabled = True
        client._bot = AsyncMock()

        trade = {
            "position_id": "POS-ABC123",
            "symbol": "BTCUSDT",
            "market": "SPOT",
            "side": "LONG",
            "entry_price": 50000.0,
            "exit_price": 52000.0,
            "amount": 0.1,
            "pnl": 200.0,
            "pnl_pct": 4.0,
            "fee": 5.0,
            "close_reason": "TAKE_PROFIT",
            "opened_at": datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            "closed_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        }

        with patch.object(client, '_ensure_bot', return_value=True):
            result = await client.send_position_closed(trade)
            assert result is True
            call_args = client._bot.send_message.call_args
            assert "POSITION CLOSED" in call_args.kwargs["text"]
            assert "+200" in call_args.kwargs["text"] or "+200.0" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_send_daily_risk_warning(self):
        """Test daily risk warning."""
        client = TelegramClient(token="test", chat_id="123")
        client._enabled = True
        client._bot = AsyncMock()

        with patch.object(client, '_ensure_bot', return_value=True):
            result = await client.send_daily_risk_warning(-15.0, 500.0, 2.0)
            assert result is True
            call_args = client._bot.send_message.call_args
            assert "DAILY RISK WARNING" in call_args.kwargs["text"]
            assert "-15.0" in call_args.kwargs["text"] or "-15.00" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_send_learning_report(self):
        """Test learning report."""
        client = TelegramClient(token="test", chat_id="123")
        client._enabled = True
        client._bot = AsyncMock()

        report = {
            "status": "trained",
            "samples": 1000,
            "validation": {
                "rf": {"aggregated": {"mean_f1": 0.55}},
                "xgb": {"aggregated": {"mean_f1": 0.58}},
            },
            "promoted": "20240101_120000",
            "outcomes_labeled": 50,
        }

        with patch.object(client, '_ensure_bot', return_value=True):
            result = await client.send_learning_report(report)
            assert result is True
            call_args = client._bot.send_message.call_args
            assert "LEARNING REPORT" in call_args.kwargs["text"]
            assert "trained" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_send_system_error(self):
        """Test system error notification (forced send)."""
        client = TelegramClient(token="test", chat_id="123")
        client._enabled = True
        client._bot = AsyncMock()

        with patch.object(client, '_ensure_bot', return_value=True):
            result = await client.send_system_error("Test error message", "TEST_COMPONENT")
            assert result is True
            call_args = client._bot.send_message.call_args
            assert "SYSTEM ERROR" in call_args.kwargs["text"]
            assert "Test error message" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_send_connection_status(self):
        """Test connection status notification."""
        client = TelegramClient(token="test", chat_id="123")
        client._enabled = True
        client._bot = AsyncMock()

        with patch.object(client, '_ensure_bot', return_value=True):
            result = await client.send_connection_status("WebSocket", "connected", "Reconnected after 5s")
            assert result is True
            call_args = client._bot.send_message.call_args
            assert "CONNECTION STATUS" in call_args.kwargs["text"]
            assert "WebSocket" in call_args.kwargs["text"]
            assert "connected" in call_args.kwargs["text"].lower()

    @pytest.mark.asyncio
    async def test_send_early_warning(self):
        """Test early warning notification."""
        client = TelegramClient(token="test", chat_id="123")
        client._enabled = True
        client._bot = AsyncMock()

        with patch.object(client, '_ensure_bot', return_value=True):
            result = await client.send_early_warning("Unusual volume spike", "BTCUSDT", "SPOT")
            assert result is True
            call_args = client._bot.send_message.call_args
            assert "EARLY WARNING" in call_args.kwargs["text"]
            assert "Unusual volume spike" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_send_daily_summary(self):
        """Test daily summary notification."""
        client = TelegramClient(token="test", chat_id="123")
        client._enabled = True
        client._bot = AsyncMock()

        stats = {
            "spot_balance": 520.0,
            "futures_balance": 480.0,
            "realized_pnl": 50.0,
            "unrealized_pnl": -10.0,
            "win_rate": 65.0,
            "profit_factor": 1.8,
            "max_drawdown": 5.2,
            "trades_today": 10,
        }

        with patch.object(client, '_ensure_bot', return_value=True):
            result = await client.send_daily_summary(stats)
            assert result is True
            call_args = client._bot.send_message.call_args
            assert "DAILY SUMMARY" in call_args.kwargs["text"]
            assert "520" in call_args.kwargs["text"]
            assert "65.0" in call_args.kwargs["text"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])