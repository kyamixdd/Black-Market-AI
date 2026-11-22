"""Market data API routes."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from ...bridge.orchestrator_bridge import get_bridge
from .schemas import (
    MarketSnapshotResponse,
    MarketListResponse,
    MarketHeatmapResponse,
    MarketBreadthResponse,
    VolumeResponse,
    LongShortResponse,
    CandleListResponse,
    MarketSymbolResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("", response_model=MarketListResponse)
async def get_all_markets():
    """Get all market snapshots."""
    bridge = get_bridge()
    markets = bridge.get_all_markets()
    spot = [m for m in markets if m["market"] == "SPOT"]
    futures = [m for m in markets if m["market"] == "FUTURES"]
    return MarketListResponse(
        markets=[MarketSnapshotResponse(**m) for m in markets],
        total=len(markets),
        spot_count=len(spot),
        futures_count=len(futures),
    )


@router.get("/symbols", response_model=list[MarketSymbolResponse])
async def get_market_symbols():
    """Get all eligible symbols with basic info."""
    bridge = get_bridge()
    return bridge.get_market_symbols()


@router.get("/heatmap", response_model=MarketHeatmapResponse)
async def get_heatmap():
    """Get market heatmap data."""
    bridge = get_bridge()
    heatmap = bridge.get_market_heatmap()
    return MarketHeatmapResponse(heatmap=heatmap)


@router.get("/analytics/{symbol}")
async def get_symbol_analytics(
    symbol: str,
    market: str = Query("SPOT", pattern="^(SPOT|FUTURES)$"),
    timeframe: str = Query("1h", pattern="^(1m|3m|5m|15m|30m|1h|4h|1d|1w)$"),
):
    """Return supported interval changes and indicator completeness."""
    return await get_bridge().get_symbol_analytics(symbol.upper(), market, timeframe)


@router.get("/correlation")
async def get_asset_correlation(
    symbol_a: str = Query(..., min_length=2, max_length=32),
    symbol_b: str = Query(..., min_length=2, max_length=32),
    market: str = Query("SPOT", pattern="^(SPOT|FUTURES)$"),
    timeframe: str = Query("1h", pattern="^(1m|3m|5m|15m|30m|1h|4h|1d|1w)$"),
    limit: int = Query(200, ge=21, le=1000),
):
    """Return Pearson correlation of aligned asset returns."""
    return await get_bridge().get_asset_correlation(
        symbol_a.upper(), symbol_b.upper(), market, timeframe, limit
)


@router.get("/scanner-status")
async def get_scanner_status():
    """Return configured scan coverage and last per-market scan outcome."""
    scanner = getattr(get_bridge().orch, "scanner", None)
    if scanner is None or not callable(getattr(scanner, "status_snapshot", None)):
        return {"state": "UNAVAILABLE", "detail": "Scanner status is not available"}
    return scanner.status_snapshot()


@router.get("/breadth", response_model=MarketBreadthResponse)
async def get_breadth():
    """Get market breadth statistics."""
    bridge = get_bridge()
    return bridge.get_market_breadth()


@router.get("/volume", response_model=VolumeResponse)
async def get_volume(
    symbol: str = Query("BTCUSDT", min_length=2, max_length=32),
    market: str = Query("SPOT", pattern="^(SPOT|FUTURES)$"),
):
    """Get measured trade flow for a symbol and 24-hour ticker volume."""
    bridge = get_bridge()
    try:
        return await bridge.get_volume_stats(symbol.upper(), market)
    except Exception as exc:
        logger.exception("Unable to load public trade flow for %s %s", market, symbol)
        raise HTTPException(status_code=503, detail="Public trade-flow data is temporarily unavailable") from exc


@router.get("/long-short", response_model=LongShortResponse)
async def get_long_short(symbol: str = Query("BTCUSDT", min_length=2, max_length=32)):
    """Get public Futures account ratio, open interest, and funding for a symbol."""
    bridge = get_bridge()
    try:
        return await bridge.get_long_short_stats(symbol.upper())
    except Exception as exc:
        logger.exception("Unable to load public Futures analytics for %s", symbol)
        raise HTTPException(status_code=503, detail="Public Futures analytics are temporarily unavailable") from exc


@router.get("/{symbol}/candles", response_model=CandleListResponse)
async def get_candles(
    symbol: str,
    market: str = Query("SPOT", pattern="^(SPOT|FUTURES)$"),
    timeframe: str = Query("1h", pattern="^(1m|3m|5m|15m|30m|1h|4h|1d|1w)$"),
    limit: int = Query(200, ge=1, le=1000),
    end_time: int | None = Query(None, ge=1),
):
    """Load current or completed historical Binance candles."""
    bridge = get_bridge()
    candles = await bridge.get_candles(symbol.upper(), market, timeframe, limit, end_time)
    return {"symbol": symbol.upper(), "market": market, "timeframe": timeframe, "candles": candles}


@router.get("/{symbol}", response_model=MarketSnapshotResponse)
async def get_market(symbol: str, market: str = Query("SPOT", pattern="^(SPOT|FUTURES)$")):
    """Get latest market snapshot for a specific symbol."""
    bridge = get_bridge()
    snap = bridge.get_market_snapshot(symbol.upper(), market)
    if not snap:
        raise HTTPException(status_code=404, detail=f"Market snapshot not found for {symbol.upper()} {market}")
    return MarketSnapshotResponse(**snap)