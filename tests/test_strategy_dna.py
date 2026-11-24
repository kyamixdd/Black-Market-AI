from datetime import datetime, timezone

from learning.strategy_dna import build_strategy_dna, evaluate_degradation


def metrics(n=40, win=60, dd=5, freq=1, hold=90):
    return {
        "sample_size": n, "win_rate_pct": win, "max_drawdown_pct": dd,
        "trade_frequency_per_day": freq, "average_holding_minutes": hold,
        "average_slippage_bps": None,
        "by_regime": {"BULL_TREND": {"trades": n, "win_rate_pct": win}},
    }


def test_degradation_requires_minimum_samples():
    result = evaluate_degradation(metrics(29), metrics(19, win=20, dd=30))
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["warnings"] == []


def test_material_win_rate_and_drawdown_changes_flag():
    result = evaluate_degradation(metrics(), metrics(win=35, dd=14))
    assert result["status"] == "DEGRADATION_DETECTED"
    assert "WIN_RATE_DECLINE" in result["warnings"]
    assert "DRAWDOWN_EXPANSION" in result["warnings"]


def test_small_changes_do_not_flag():
    result = evaluate_degradation(metrics(), metrics(win=57, dd=6, freq=1.2, hold=100))
    assert result["status"] == "STABLE"
    assert result["warnings"] == []


def test_regime_comparison_is_contextual():
    current = metrics()
    current["by_regime"] = {"BEAR_TREND": {"trades": 25, "win_rate_pct": 40}}
    result = evaluate_degradation(metrics(), current)
    assert "REGIME_MIX_CHANGED" in result["warnings"]
    assert "regime_change" in result["comparisons"]


def test_profile_reports_missing_history_without_fake_metrics():
    result = build_strategy_dna([], [], now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    momentum = next(item for item in result["profiles"] if item["strategy"] == "momentum")
    assert momentum["historical_behavior"]["sample_size"] == 0
    assert momentum["historical_behavior"]["win_rate_pct"] is None
    assert momentum["behavioral_differences"]["status"] == "INSUFFICIENT_DATA"


def test_profiles_use_actual_saved_backtest_and_paper_trade_records():
    report = {
        "strategy_name": "momentum", "status": "ok",
        "config": {"start_date": "2025-01-01T00:00:00Z", "end_date": "2025-02-01T00:00:00Z"},
        "report": {"status": "ok", "metrics": {"max_drawdown_pct": 4},
                   "trades": [{"status": "CLOSED", "net_pnl": 12, "entry_time": 1735689600000,
                               "exit_time": 1735693200000, "regime": "BULL_TREND"}]},
    }
    paper = [{"strategy": "momentum", "pnl": -5, "opened_at": "2026-01-01T00:00:00Z",
              "closed_at": "2026-01-01T01:00:00Z", "regime": "BEAR_TREND"}]
    result = build_strategy_dna([report], paper, now=datetime(2026, 1, 2, tzinfo=timezone.utc))
    momentum = next(item for item in result["profiles"] if item["strategy"] == "momentum")
    assert momentum["historical_behavior"]["net_pnl"] == 12
    assert momentum["current_paper_behavior"]["net_pnl"] == -5
