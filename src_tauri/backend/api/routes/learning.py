"""Learning API routes."""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Query, HTTPException

from ...bridge.orchestrator_bridge import get_bridge
from database.connection import get_session_maker
from database.repositories import Repository
from .schemas import (
    LearningStatusResponse,
    PredictionListResponse,
    PredictionResponse,
    ModelRegistryListResponse,
    ModelRegistryResponse,
)

router = APIRouter(prefix="/learning", tags=["learning"])

_STRATEGY_COMPARISON_CACHE: dict[tuple[str, str, str, int], tuple[float, dict]] = {}


@router.get("", response_model=LearningStatusResponse)
@router.get("/status", response_model=LearningStatusResponse)
async def get_learning_status():
    """Get learning engine status."""
    bridge = get_bridge()
    return bridge.get_learning_status()


@router.get("/predictions", response_model=PredictionListResponse)
async def get_predictions(limit: int = Query(100, le=1000)):
    """Get recent predictions with outcomes."""
    bridge = get_bridge()
    predictions = bridge.get_recent_predictions(limit)
    resolved = [p for p in predictions if p.get("is_correct") is not None]
    correct = [p for p in resolved if p.get("is_correct")]
    accuracy = len(correct) / len(resolved) * 100 if resolved else 0

    return PredictionListResponse(
        predictions=[PredictionResponse(**p) for p in predictions],
        total=len(predictions),
        resolved_count=len(resolved),
        accuracy=accuracy,
    )


@router.get("/performance")
async def get_model_performance():
    """Return classification metrics and closed paper-trade performance."""
    from collections import defaultdict
    from datetime import date
    from math import sqrt

    bridge = get_bridge()
    predictions = bridge.get_recent_predictions(limit=10000)
    evaluated = [p for p in predictions if p.get("is_correct") is not None
                 and p.get("predicted_class") is not None and p.get("actual_outcome") is not None]
    accuracy = sum(bool(p["is_correct"]) for p in evaluated) / len(evaluated) * 100 if evaluated else None
    labels = sorted({str(p["predicted_class"]).upper() for p in evaluated}
                    | {str(p["actual_outcome"]).upper() for p in evaluated})
    precisions, recalls = [], []
    for label in labels:
        tp = sum(str(p["predicted_class"]).upper() == label and str(p["actual_outcome"]).upper() == label for p in evaluated)
        pred_n = sum(str(p["predicted_class"]).upper() == label for p in evaluated)
        actual_n = sum(str(p["actual_outcome"]).upper() == label for p in evaluated)
        if pred_n: precisions.append(tp / pred_n)
        if actual_n: recalls.append(tp / actual_n)
    precision = sum(precisions) / len(precisions) * 100 if precisions else None
    recall = sum(recalls) / len(recalls) * 100 if recalls else None

    trades = bridge.get_recent_trades(limit=10000)
    closed = [t for t in trades if t.get("closed_at") is not None and _finite_metric(t.get("pnl")) is not None]
    closed.sort(key=lambda t: str(t.get("closed_at") or ""))
    pnls = [_finite_metric(t.get("pnl")) or 0.0 for t in closed]
    wins, losses = [p for p in pnls if p > 0], [p for p in pnls if p < 0]
    gross_profit, gross_loss = sum(wins), abs(sum(losses))
    factor = gross_profit / gross_loss if gross_loss else (None if gross_profit == 0 else "infinite")
    win_rate = len(wins) / len(closed) * 100 if closed else None

    sim = bridge.simulator
    initial = (_finite_metric(getattr(sim, "initial_spot_balance", 0)) or 0.0) + (_finite_metric(getattr(sim, "initial_futures_balance", 0)) or 0.0)
    equity = peak = initial
    max_dd = 0.0
    daily = defaultdict(float)
    for trade, pnl in zip(closed, pnls):
        equity += pnl
        peak = max(peak, equity)
        if peak > 0: max_dd = max(max_dd, (peak - equity) / peak * 100)
        try: daily[date.fromisoformat(str(trade["closed_at"])[:10])] += pnl
        except (ValueError, TypeError, KeyError): pass
    returns = [pnl / initial for _, pnl in sorted(daily.items())] if initial > 0 else []
    if len(returns) >= 2:
        mean = sum(returns) / len(returns)
        std = sqrt(sum((x - mean) ** 2 for x in returns) / len(returns))
        sharpe = mean / std * sqrt(365) if std else 0.0
    else: sharpe = None
    return {
        "prediction_count": len(evaluated), "accuracy_pct": accuracy,
        "precision_macro_pct": precision, "recall_macro_pct": recall,
        "trade_count": len(closed), "profit_factor": factor,
        "win_rate_pct": win_rate, "max_drawdown_pct": max_dd if closed else None,
        "sharpe_ratio": sharpe,
        "trade_metrics_source": "closed_paper_trades",
        "classification_metrics_source": "resolved_predictions",
        "sharpe_period": "daily realized PnL / initial paper equity, annualized with sqrt(365)",
    }


def _finite_metric(value):
    from math import isfinite
    try: number = float(value)
    except (TypeError, ValueError, OverflowError): return None
    return number if isfinite(number) else None


@router.get("/strategy-comparison")
async def get_strategy_comparison(
    symbol: str = Query("BTCUSDT", min_length=3, max_length=20, pattern=r"^[A-Z0-9]+$"),
    market: str = Query("SPOT", pattern="^(SPOT|FUTURES)$"),
    timeframe: str = Query("1h", pattern="^(5m|15m|30m|1h|4h|1d)$"),
    limit: int = Query(1000, ge=180, le=2000),
):
    """Compare five strategies on an identical historical out-of-sample period."""
    import time
    from learning.strategy_comparison import compare_strategies

    bridge = get_bridge()
    end_time = int(time.time() * 1000)
    candles = await bridge.get_candles(
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        limit=limit,
        end_time=end_time,
    )
    if not candles:
        return {
            "status": "insufficient_data",
            "symbol": symbol,
            "market": market,
            "timeframe": timeframe,
            "candles": 0,
            "strategies": [],
            "reason": "no_closed_historical_candles",
        }
    normalized = [
        {**candle, "symbol": symbol, "market": market, "timeframe": timeframe}
        for candle in candles
    ]
    result = compare_strategies(normalized, timeframe=timeframe)
    _STRATEGY_COMPARISON_CACHE[cache_key] = (time.monotonic(), result)
    if len(_STRATEGY_COMPARISON_CACHE) > 100:
        oldest = min(_STRATEGY_COMPARISON_CACHE, key=lambda key: _STRATEGY_COMPARISON_CACHE[key][0])
        _STRATEGY_COMPARISON_CACHE.pop(oldest, None)
    return result


@router.get("/models", response_model=ModelRegistryListResponse)
async def get_models():
    """Get model registry."""
    bridge = get_bridge()
    models = bridge.get_model_registry()
    return ModelRegistryListResponse(models=[ModelRegistryResponse(**m) for m in models])


def _save_lab_report(strategy_name: str, payload: dict, report: dict) -> str:
    """Persist every completed Strategy Lab result before returning it to the client."""
    repository = Repository(get_session_maker())
    report_id = uuid.uuid4().hex
    record = {
        "report_id": report_id,
        "strategy_id": payload.get("strategy_id") if isinstance(payload.get("strategy_id"), str) else None,
        "strategy_name": strategy_name,
        "symbol": str(payload.get("symbol", "BTCUSDT")).upper(),
        "market": str(payload.get("market", "SPOT")).upper(),
        "timeframe": str(payload.get("timeframe", "1h")),
        "status": report.get("status", "completed"),
        "config": payload,
        "report": report,
    }
    repository.save_backtest_report(record)
    return report_id


@router.post("/strategy-lab")
async def run_strategy_lab(payload: dict):
    """Run a deterministic historical simulation using completed candle data."""
    from datetime import datetime
    from learning.strategy_lab import LabConfig, STRATEGIES, run_strategy_lab

    symbol = str(payload.get("symbol", "BTCUSDT")).upper()
    market = str(payload.get("market", "SPOT")).upper()
    timeframe = str(payload.get("timeframe", "1h"))
    strategy = str(payload.get("strategy", "momentum")).lower()
    if not re.fullmatch(r"[A-Z0-9]{3,20}", symbol):
        raise HTTPException(status_code=422, detail="Invalid symbol")
    if strategy not in STRATEGIES:
        raise HTTPException(status_code=422, detail="Unsupported strategy")
    try:
        start = datetime.fromisoformat(str(payload["start_date"]).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(payload["end_date"]).replace("Z", "+00:00"))
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("Date range must be timezone-aware and start before end")
        config = LabConfig(
            symbol=symbol, market=market, timeframe=timeframe,
            start_time=int(start.timestamp() * 1000), end_time=int(end.timestamp() * 1000),
            initial_capital=payload.get("initial_capital", 1000),
            sizing_mode=payload.get("sizing_mode", "risk_pct"),
            risk_per_trade_pct=payload.get("risk_per_trade_pct", 1),
            fixed_notional=payload.get("fixed_notional", 100),
            max_position_pct=payload.get("max_position_pct", 50),
            fee_rate=payload.get("fee_rate"), slippage_bps=payload.get("slippage_bps"),
            spread_bps=payload.get("spread_bps"), funding_rate=payload.get("funding_rate"),
            strategy_parameters=payload.get("strategy_parameters", {}),
        )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid backtest configuration: {exc}") from exc
    bridge = get_bridge()
    candles = []
    cursor = config.end_time
    page_limit = 1000 if market == "SPOT" else 1500
    # Walk backward so user-selected ranges longer than one exchange page are supported.
    # Bound requests to 20 pages (20k Spot / 30k Futures candles) to prevent unbounded work.
    for _ in range(20):
        page = await bridge.get_candles(symbol, market, timeframe, limit=page_limit, end_time=cursor)
        page = [row for row in page if int(row.get("close_time", 0)) <= cursor]
        if not page:
            break
        candles.extend(page)
        earliest = min(int(row["open_time"]) for row in page)
        if earliest <= config.start_time:
            break
        cursor = earliest - 1
    candles = [row for row in candles if config.start_time <= int(row.get("open_time", 0))
               and int(row.get("close_time", row.get("open_time", 0))) <= config.end_time]
    candles.sort(key=lambda row: int(row["open_time"]))
    try:
        result = run_strategy_lab(candles, config, strategy)
        report_id = _save_lab_report(strategy, payload, result)
        result["report_id"] = report_id
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/strategy-lab/compare")
async def compare_strategy_lab(payload: dict):
    """Compare selected strategies on the same symbol, timeframe and candle window."""
    from learning.strategy_lab import STRATEGIES
    names = payload.get("strategies", list(STRATEGIES))
    if not isinstance(names, list) or not names or any(name not in STRATEGIES for name in names):
        raise HTTPException(status_code=422, detail="Select one or more supported strategies")
    results = []
    for name in names:
        config = dict(payload)
        config["strategy"] = name
        results.append(await run_strategy_lab(config))
    comparison = {"status": "ok", "conditions": {k: payload.get(k) for k in
            ("symbol", "market", "timeframe", "start_date", "end_date", "initial_capital")},
            "results": results}
    report_id = _save_lab_report("strategy-comparison", payload, comparison)
    comparison["report_id"] = report_id
    return comparison
