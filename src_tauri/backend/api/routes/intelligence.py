"""Intelligence API routes."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ...bridge.orchestrator_bridge import get_bridge
from .schemas import (
    IntelligenceSummaryResponse,
    StrategyMetricsListResponse,
    StrategyMetricsResponse,
    StrategyWeightResponse,
)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("", response_model=IntelligenceSummaryResponse)
async def get_intelligence_summary():
    """Get strategy evaluations and current strategy weights."""
    bridge = get_bridge()
    return IntelligenceSummaryResponse(
        strategies=[
            StrategyMetricsResponse(**metric)
            for metric in bridge.get_strategy_metrics()
        ],
        strategy_weights=bridge.get_strategy_weights(),
    )


@router.get("/strategies", response_model=StrategyMetricsListResponse)
async def get_strategy_metrics():
    """Get strategy performance metrics."""
    bridge = get_bridge()
    metrics = bridge.get_strategy_metrics()
    return StrategyMetricsListResponse(metrics=[StrategyMetricsResponse(**m) for m in metrics])


@router.get("/weights", response_model=dict[str, StrategyWeightResponse])
async def get_strategy_weights():
    """Get strategy weights by regime."""
    bridge = get_bridge()
    return bridge.get_strategy_weights()

@router.get("/regime/{symbol}")
async def get_market_regime(
    symbol: str,
    market: str = Query("SPOT", pattern="^(SPOT|FUTURES)$"),
    timeframe: str = Query("1h", pattern="^(1m|3m|5m|15m|30m|1h|4h|1d|1w)$"),
    limit: int = Query(100, ge=50, le=1000),
):
    """Rule-based market regime with explicit evidence and sample sufficiency."""
    from market.regime_radar import classify_market_regime

    bridge = get_bridge()
    candles = await bridge.get_candles(symbol.upper(), market, timeframe, limit=limit)
    result = classify_market_regime(
        candles, symbol=symbol, market=market, timeframe=timeframe,
        expected_candles=limit,
    )
    if candles:
        last_close = candles[-1].get("close_time")
        try:
            age = max(0.0, (__import__("time").time() * 1000 - float(last_close)) / 1000)
        except (TypeError, ValueError, OverflowError):
            age = None
    else:
        age = None
    result["data_age_seconds"] = age
    result["data_freshness"] = (
        "LIVE" if age is not None and age <= 90 else
        "DELAYED" if age is not None and age <= 300 else
        "STALE" if age is not None else "UNKNOWN"
    )
    return result


@router.get("/market-analysis/{symbol}")
async def get_evidence_market_analysis(
    symbol: str,
    market: str = Query("SPOT", pattern="^(SPOT|FUTURES)$"),
    timeframe: str = Query("1h", pattern="^(1m|3m|5m|15m|30m|1h|4h|1d|1w)$"),
):
    """Aggregate observed market state and calculated evidence without prediction."""
    bridge = get_bridge()
    snapshot = bridge.get_market_snapshot(symbol.upper(), market)
    if not snapshot:
        return {
            "symbol": symbol.upper(), "market": market, "timeframe": timeframe,
            "status": "UNAVAILABLE", "observed": {}, "calculated": {},
            "supporting_evidence": [], "conflicting_evidence": [],
            "risk_factors": ["No market snapshot is currently available."],
            "invalidation_conditions": ["Re-evaluate when a valid market snapshot and candles are available."],
            "interpretation": None,
        }

    analytics = await bridge.get_symbol_analytics(symbol.upper(), market, timeframe)
    regime = await get_market_regime(symbol, market, timeframe, 100)
    observed = {
        key: snapshot.get(key) for key in (
            "price", "volume_24h", "price_change_24h", "timestamp",
            "data_age_seconds", "data_freshness", "mark_price",
            "funding_rate", "open_interest",
        ) if snapshot.get(key) is not None
    }
    calculated = {
        key: analytics.get(key) for key in (
            "price_changes", "indicators", "data_completeness", "status",
        ) if key in analytics
    }
    supporting = list(regime.get("evidence", []))
    if observed.get("price_change_24h") is not None:
        change = float(observed["price_change_24h"])
        supporting.append(f"Observed 24-hour price change: {change:+.3f}%.")
    conflicts = []
    if regime.get("regime") in ("UPTREND", "DOWNTREND") and observed.get("price_change_24h") is not None:
        daily_change = float(observed["price_change_24h"])
        if (regime["regime"] == "UPTREND" and daily_change < 0) or (regime["regime"] == "DOWNTREND" and daily_change > 0):
            conflicts.append("The short-window regime rule and 24-hour price change point in different directions.")
    risks = []
    if observed.get("data_freshness") not in ("LIVE", "DELAYED"):
        risks.append("Market snapshot is stale or its freshness is unknown.")
    if regime.get("status") != "READY":
        risks.append("Regime classification lacks sufficient valid candle data.")
    if observed.get("funding_rate") is not None and market == "FUTURES":
        risks.append("Funding rate is a current observation and may change before execution.")
    return {
        "symbol": symbol.upper(), "market": market, "timeframe": timeframe,
        "status": "READY" if regime.get("status") == "READY" else regime.get("status"),
        "observed": observed, "calculated": calculated,
        "regime": regime, "supporting_evidence": supporting,
        "conflicting_evidence": conflicts, "risk_factors": risks,
        "invalidation_conditions": [
            "Re-evaluate when the selected timeframe closes a new candle.",
            "Re-evaluate if price no longer satisfies the reported SMA and slope rule.",
            "Do not rely on this descriptive classification as a forecast.",
        ],
        "interpretation": "Evidence summary only; not a guaranteed prediction or investment recommendation.",
    }
