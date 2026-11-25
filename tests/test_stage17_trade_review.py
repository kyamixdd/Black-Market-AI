"""Tests for evidence-linked paper trade reviews."""
from learning.trade_review import build_trade_review


def test_profitable_trade_is_not_automatically_given_positive_quality():
    trade = {
        "position_id": "pos-1", "symbol": "BTCUSDT", "market": "SPOT",
        "side": "BUY", "entry_price": 100, "exit_price": 120,
        "amount": 1, "leverage": 1, "pnl": 20, "pnl_pct": 20,
        "fee": 1, "strategy": "MOMENTUM", "opened_at": "2026-01-01T00:00:00+00:00",
        "closed_at": "2026-01-01T01:00:00+00:00", "close_reason": "TAKE_PROFIT",
    }
    review = build_trade_review(trade)
    assert review["outcome"] == "PROFIT"
    assert review["decision_quality"] == "NOT_RATED"
    assert review["strategy_rule_adherence"] == "UNVERIFIABLE"
    assert "Profit or loss" in review["findings"][1]


def test_signal_evidence_is_linked_and_strategy_mismatch_is_flagged():
    trade = {
        "position_id": "pos-2", "symbol": "ETHUSDT", "market": "SPOT",
        "side": "BUY", "entry_price": 102, "exit_price": 98,
        "amount": 1, "leverage": 1, "pnl": -4, "pnl_pct": -3.9,
        "fee": 0.1, "strategy": "BREAKOUT", "opened_at": None,
        "closed_at": None, "close_reason": "STOP_LOSS",
    }
    signal = {
        "signal_id": "sig-2", "strategy": "MOMENTUM", "direction": "BUY",
        "entry": 100, "stop_loss": 95, "take_profit": 110, "reasons": ["rule"],
    }
    review = build_trade_review(trade, signal)
    assert review["outcome"] == "LOSS"
    assert review["signal_link_status"] == "AVAILABLE"
    assert review["entry_price_deviation_pct"] == 2
    assert any("strategy label differs" in finding for finding in review["findings"])
    assert review["evidence"][1]["record_id"] == "sig-2"


def test_missing_trade_fields_do_not_create_fake_compliance_claims():
    review = build_trade_review({"position_id": "pos-3", "pnl": 1})
    assert review["risk_limit_compliance"] == "UNVERIFIABLE"
    assert review["position_sizing_compliance"] == "UNVERIFIABLE"
