"""Evidence-grounded, deterministic assistant tools for local market data."""
from __future__ import annotations

import math
import re
from typing import Any

TOOL_NAMES = (
    "market_snapshot", "historical_candles", "indicator_report", "scanner_status",
    "signal_report", "strategy_report", "paper_account", "open_positions",
    "trade_history", "risk_status", "learning_evaluation",
)

def validate_symbol(value: str) -> str:
    symbol = str(value).strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,20}", symbol):
        raise ValueError("Symbol must contain 2–20 letters or digits.")
    return symbol

def validate_market(value: str) -> str:
    market = str(value).strip().upper()
    if market not in {"SPOT", "FUTURES"}:
        raise ValueError("Market must be SPOT or FUTURES.")
    return market

def select_tool(question: str) -> str:
    q = question.lower()
    if any(k in q for k in ("candle", "historical", "history chart", "ohlc")):
        return "historical_candles"
    if any(k in q for k in ("indicator", "sma", "ema", "atr", "volatility", "analytics")):
        return "indicator_report"
    if "scanner" in q or "scan status" in q:
        return "scanner_status"
    if any(k in q for k in ("signal", "rejected", "signal reason")):
        return "signal_report"
    if any(k in q for k in ("strategy", "weights", "strategy config")):
        return "strategy_report"
    if any(k in q for k in ("position", "open trade")):
        return "open_positions"
    if any(k in q for k in ("trade history", "closed trade", "recent trade")):
        return "trade_history"
    if any(k in q for k in ("risk", "exposure", "risk limit")):
        return "risk_status"
    if any(k in q for k in ("learning", "model", "evaluation", "accuracy", "prediction")):
        return "learning_evaluation"
    if any(k in q for k in ("portfolio", "paper account", "equity", "balance", "pnl")):
        return "paper_account"
    return "market_snapshot"

def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

def _safe(value: Any) -> Any:
    """Convert provider values to JSON-safe values without leaking arbitrary settings."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items() if not any(secret in str(k).lower() for secret in ("secret", "token", "password", "api_key", "credential"))}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value[:100]]
    return str(value)

async def execute_tool(bridge: Any, tool: str, symbol: str, market: str, timeframe: str = "1h") -> dict:
    if tool not in TOOL_NAMES:
        raise ValueError("Unsupported assistant tool.")
    symbol = validate_symbol(symbol)
    market = validate_market(market)
    if timeframe not in {"1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"}:
        raise ValueError("Unsupported timeframe.")

    if tool == "market_snapshot":
        result = bridge.get_market_snapshot(symbol, market)
    elif tool == "historical_candles":
        candles = await bridge.get_candles(symbol, market, timeframe, limit=100)
        completed = [c for c in candles if _finite(c.get("close")) and c.get("close_time") is not None]
        result = {"symbol": symbol, "market": market, "timeframe": timeframe, "completed_candle_count": len(completed), "latest_completed_candle": completed[-1] if completed else None, "method": "backend candle series; latest returned completed candle"}
    elif tool == "indicator_report":
        result = await bridge.get_symbol_analytics(symbol, market, timeframe)
    elif tool == "scanner_status":
        scanner = getattr(bridge.orch, "scanner", None)
        result = scanner.status_snapshot() if scanner and callable(getattr(scanner, "status_snapshot", None)) else None
    elif tool == "signal_report":
        items = bridge.get_all_signals()
        result = {"signals": [s for s in items if s.get("symbol") == symbol and s.get("market", market) == market][-5:]}
    elif tool == "strategy_report":
        result = {"strategy_metrics": bridge.get_strategy_metrics(), "strategy_weights": bridge.get_strategy_weights()}
    elif tool == "paper_account":
        result = bridge.get_portfolio_summary()
    elif tool == "open_positions":
        result = {"positions": [p for p in bridge.get_open_positions() if p.get("symbol") == symbol and p.get("market") == market]}
    elif tool == "trade_history":
        result = {"closed_paper_trades": [t for t in bridge.get_recent_trades(limit=20) if t.get("symbol") == symbol and t.get("market") == market]}
    elif tool == "risk_status":
        result = bridge.get_risk_metrics()
    else:
        result = bridge.get_learning_status()
        if isinstance(result, dict):
            result = {**result, "recent_predictions": bridge.get_recent_predictions(limit=20)}
    if result is None or result == {} or result == []:
        return {"tool": tool, "status": "unavailable", "data": None, "source": "local backend", "message": "The requested data is not currently available."}
    return {"tool": tool, "status": "available", "data": _safe(result), "source": "local backend", "symbol": symbol, "market": market, "timeframe": timeframe}

def summarize_result(question: str, result: dict) -> str:
    if result.get("status") != "available":
        return result.get("message", "The requested local data is unavailable.")
    tool, data = result["tool"], result["data"]
    if tool == "market_snapshot":
        return f"Observed {result['symbol']} {result['market']} snapshot: price={data.get('price', 'unavailable')}; 24h change={data.get('price_change_24h', 'unavailable')}%; regime={data.get('regime', 'unavailable')}; freshness={data.get('data_freshness', 'unknown')} (age {data.get('data_age_seconds', 'unknown')} seconds)."
    if tool == "paper_account":
        return f"Paper account only: total equity={data.get('total_balance', 'unavailable')}; realized P&L={data.get('realized_pnl', 'unavailable')}; unrealized P&L={data.get('unrealized_pnl', 'unavailable')}; daily P&L={data.get('daily_pnl', 'unavailable')}; drawdown={data.get('drawdown_pct', 'unavailable')}%. No real-money account is accessed."
    if tool == "indicator_report":
        return f"Backend indicator report for {result['symbol']} {result['market']} ({result['timeframe']}): {data.get('data_completeness', {})}; price changes={data.get('price_change_pct', {})}; historical volatility={data.get('historical_volatility_24h_pct', 'unavailable')}%; ATR(14)={data.get('atr_14_pct', 'unavailable')}%. These are calculated measurements, not forecasts."
    if tool == "historical_candles":
        latest = data.get("latest_completed_candle")
        return f"Historical candle tool returned {data.get('completed_candle_count', 0)} completed candles for {result['symbol']} {result['market']} {result['timeframe']}. Latest returned candle: {latest if latest else 'unavailable'}."
    if tool == "signal_report":
        signals = data.get("signals", [])
        if not signals: return f"No persisted signal records are available for {result['symbol']} {result['market']}."
        return f"Persisted signals for {result['symbol']} {result['market']}: " + "; ".join(f"{s.get('direction','?')} {s.get('strategy','?')} status={s.get('status','?')} confidence={s.get('confidence','unavailable')} reasons={s.get('reasons', [])}" for s in signals)
    if tool == "open_positions":
        positions = data.get("positions", [])
        return f"Open paper positions for {result['symbol']} {result['market']}: {positions if positions else 'none recorded'}."
    if tool == "trade_history":
        trades = data.get("closed_paper_trades", [])
        return f"Recent closed paper trades for {result['symbol']} {result['market']}: {trades if trades else 'none recorded'}."
    if tool == "risk_status":
        return "Current risk metrics from the local risk manager: " + str(data)
    if tool == "strategy_report":
        return "Strategy performance and configured weights from local records: " + str(data)
    if tool == "learning_evaluation":
        return "Learning status and recorded prediction outcomes: " + str(data)
    return "Scanner status from the local scanner: " + str(data)
