"""Regression coverage for timestamp-bounded backtesting behavior."""
from datetime import datetime, timezone, timedelta

from learning.backtest_engine import BacktestConfig, BacktestTrade, HistoricalBacktester
from market.candle_manager import CandleManager


def _time(minutes: int) -> datetime:
    return datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minutes)


def _candle(manager, minute, open_, high, low, close):
    open_ms = int(_time(minute).timestamp() * 1000)
    manager.add_candle("SPOT", "BTCUSDT", "1m", open_ms, open_, high, low, close, 1.0)


def test_candle_manager_returns_only_timestamp_bounded_closed_candles():
    manager = CandleManager()
    for minute in range(3):
        _candle(manager, minute, 100 + minute, 102 + minute, 99 + minute, 101 + minute)

    end_ms = int(_time(2).timestamp() * 1000)
    candles = manager.get_series_until("SPOT", "BTCUSDT", "1m", end_time_ms=end_ms)
    assert [c["open_time"] for c in candles] == [int(_time(0).timestamp()*1000), int(_time(1).timestamp()*1000)]
    assert all(c["close_time"] <= end_ms for c in candles)


def test_exit_uses_historical_candle_and_conservative_stop_when_both_hit():
    manager = CandleManager()
    _candle(manager, 0, 100, 105, 98, 101)
    _candle(manager, 1, 100, 115, 90, 108)
    backtester = HistoricalBacktester.__new__(HistoricalBacktester)
    backtester.candles = manager
    backtester.liquidation = type("Liquidation", (), {"check_liquidation": lambda *_: False})()
    trade = BacktestTrade(
        trade_id="t1", symbol="BTCUSDT", market="SPOT", strategy="test", side="LONG",
        entry_time=_time(0), entry_price=100, exit_time=None, exit_price=None,
        amount=1, leverage=1, stop_loss=95, take_profit=110, timeframe="1m",
    )
    result = backtester._check_exit(trade, _time(2), BacktestConfig(_time(0), _time(3)))
    assert result == (95, "STOP_LOSS")


def test_open_position_is_checked_even_at_max_position_limit_and_counted_once():
    backtester = HistoricalBacktester.__new__(HistoricalBacktester)
    backtester.candles = CandleManager()
    config = BacktestConfig(
        start_date=_time(0), end_date=_time(3), timeframes=["1m"],
        symbols=["BTCUSDT"], markets=["SPOT"], max_positions=1,
    )
    trade = BacktestTrade(
        trade_id="once", symbol="BTCUSDT", market="SPOT", strategy="test", side="LONG",
        entry_time=_time(0), entry_price=100, exit_time=None, exit_price=None,
        amount=1, leverage=1, stop_loss=90, take_profit=120, timeframe="1m",
    )
    generated = {"count": 0}
    checks = {"count": 0}
    backtester._get_eligible_symbols = lambda _config: ["BTCUSDT"]
    def signal(*_args):
        if generated["count"]:
            return None
        generated["count"] += 1
        return {"symbol": "BTCUSDT", "market": "SPOT", "direction": "LONG", "entry": 100,
                "stop_loss": 90, "take_profit": [120], "strategy": "test", "timeframe": "1m"}
    backtester._generate_signal = signal
    backtester._should_take_signal = lambda *_: True
    backtester._execute_trade = lambda *_: trade
    def check(_trade, current_time, _config):
        checks["count"] += 1
        return (105, "TAKE_PROFIT") if current_time >= _time(2) else None
    backtester._check_exit = check
    def close(_trade, price, reason, exit_time, _config):
        _trade.exit_price, _trade.close_reason, _trade.exit_time, _trade.pnl = price, reason, exit_time, 5.0
    backtester._close_trade = close

    trades, _ = backtester._simulate_backtest(config)
    assert checks["count"] == 2
    assert len(trades) == 1
    assert trades[0].trade_id == "once"
    assert trades[0].pnl == 5.0
