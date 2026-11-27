"""Market discovery engine.

Fetches Binance exchange information (public REST) and builds the symbol registry.
No API keys required - only public market data.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any

import aiohttp

from .rate_limiter import RateLimiter
from .symbol_registry import SymbolRegistry
from core.observability import log_event

logger = logging.getLogger(__name__)

SPOT_EXCHANGE_INFO = "https://api.binance.com/api/v3/exchangeInfo"
FUTURES_EXCHANGE_INFO = "https://fapi.binance.com/fapi/v1/exchangeInfo"


class MarketDiscovery:
    def __init__(self, registry: SymbolRegistry, rate_limiter: RateLimiter,
                 spot_enabled: bool = True, futures_enabled: bool = True):
        self.registry = registry
        self.rate_limiter = rate_limiter
        self.spot_enabled = spot_enabled
        self.futures_enabled = futures_enabled
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    @staticmethod
    def _extract_min_notional(filters: dict[str, dict[str, Any]]) -> float:
        notional_filter = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL") or {}
        raw = notional_filter.get("minNotional")
        if raw is None:
            raw = notional_filter.get("notional")
        try:
            value = float(raw) if raw is not None else 10.0
            return value if value > 0 else 10.0
        except (TypeError, ValueError):
            return 10.0

    async def _fetch(self, url: str) -> dict[str, Any]:
        started = time.perf_counter()
        session = await self._ensure_session()
        max_retries = 2
        for attempt in range(max_retries + 1):
            await self.rate_limiter.acquire("exchange_info", 1.0, timeout=30.0)
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status in (418, 429) or 500 <= resp.status <= 599:
                        if attempt >= max_retries:
                            resp.raise_for_status()
                        delay = min(8.0, 0.5 * (2 ** attempt) + random.uniform(0, 0.25))
                        await asyncio.sleep(delay)
                        continue
                    resp.raise_for_status()
                    data = await resp.json()
                    log_event(
                        logger, logging.INFO, "exchange_metadata_retrieved",
                        component="market_discovery", operation="fetch_exchange_info",
                        endpoint=url.removeprefix("https://"), status_code=200,
                        duration_ms=round((time.perf_counter() - started) * 1000, 2),
                        symbol_count=len(data.get("symbols", [])),
                    )
                    return data
            except asyncio.CancelledError:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError):
                if attempt >= max_retries:
                    raise
                delay = min(8.0, 0.5 * (2 ** attempt) + random.uniform(0, 0.25))
                await asyncio.sleep(delay)
        raise RuntimeError(f"Unreachable retry loop for {url}")

    async def discover_spot(self) -> int:
        if not self.spot_enabled:
            return 0
        try:
            data = await self._fetch(SPOT_EXCHANGE_INFO)
        except Exception as exc:
            logger.error("Spot exchange info failed: %s", exc)
            log_event(
                logger, logging.ERROR, "exchange_metadata_failed",
                component="market_discovery", operation="spot_exchange_info",
                endpoint="api.binance.com/api/v3/exchangeInfo",
                outcome="FAILURE", error_type=type(exc).__name__,
                recommendation="Check public Binance Spot API availability, DNS, rate limits, and network access.",
            )
            return 0
        count = 0
        for s in data.get("symbols", []):
            if s.get("status") != "TRADING":
                continue
            filters = {f["filterType"]: f for f in s.get("filters", [])}
            lot = filters.get("LOT_SIZE", {})
            price = filters.get("PRICE_FILTER", {})
            info = {
                "symbol": s["symbol"],
                "market": "SPOT",
                "base_asset": s.get("baseAsset", ""),
                "quote_asset": s.get("quoteAsset", ""),
                "price_precision": s.get("pricePrecision", 4),
                "quantity_precision": s.get("quantityPrecision", 4),
                "tick_size": float(price.get("tickSize", 0.0001)),
                "step_size": float(lot.get("stepSize", 0.0001)),
                "min_notional": self._extract_min_notional(filters),
                "status": s.get("status", "TRADING"),
                "is_eligible": True,
            }
            self.registry.register(s["symbol"], "SPOT", info)
            count += 1
        log_event(
            logger, logging.INFO, "market_symbols_discovered",
            component="market_discovery", operation="filter_spot_symbols",
            market="SPOT", symbol_count=len(data.get("symbols", [])),
            eligible_count=count, outcome="SUCCESS",
        )
        return count

    async def discover_futures(self) -> int:
        if not self.futures_enabled:
            return 0
        try:
            data = await self._fetch(FUTURES_EXCHANGE_INFO)
        except Exception as exc:
            logger.error("Futures exchange info failed: %s", exc)
            log_event(
                logger, logging.ERROR, "exchange_metadata_failed",
                component="market_discovery", operation="futures_exchange_info",
                endpoint="fapi.binance.com/fapi/v1/exchangeInfo",
                outcome="FAILURE", error_type=type(exc).__name__,
                recommendation="Check public Binance USD-M Futures API availability, DNS, rate limits, and network access.",
            )
            return 0
        count = 0
        for s in data.get("symbols", []):
            if s.get("status") != "TRADING":
                continue
            filters = {f["filterType"]: f for f in s.get("filters", [])}
            lot = filters.get("LOT_SIZE", {})
            price = filters.get("PRICE_FILTER", {})
            info = {
                "symbol": s["symbol"],
                "market": "FUTURES",
                "base_asset": s.get("baseAsset", ""),
                "quote_asset": s.get("quoteAsset", ""),
                "price_precision": s.get("pricePrecision", 4),
                "quantity_precision": s.get("quantityPrecision", 4),
                "tick_size": float(price.get("tickSize", 0.0001)),
                "step_size": float(lot.get("stepSize", 0.0001)),
                "min_notional": self._extract_min_notional(filters),
                "status": s.get("status", "TRADING"),
                "is_eligible": True,
            }
            self.registry.register(s["symbol"], "FUTURES", info)
            count += 1
        log_event(
            logger, logging.INFO, "market_symbols_discovered",
            component="market_discovery", operation="filter_futures_symbols",
            market="FUTURES", symbol_count=len(data.get("symbols", [])),
            eligible_count=count, outcome="SUCCESS",
        )
        return count

    async def discover_all(self) -> dict[str, int]:
        started = time.perf_counter()
        log_event(
            logger, logging.INFO, "exchange_selection_started",
            component="market_discovery", operation="select_public_exchange_sources",
            phase="public_rest", details="Spot api.binance.com; USD-M Futures fapi.binance.com",
            outcome="STARTED",
        )
        try:
            spot = await self.discover_spot()
            futures = await self.discover_futures()
        finally:
            await self.close()
        result = {"spot": spot, "futures": futures}
        log_event(
            logger, logging.INFO, "market_discovery_completed",
            component="market_discovery", operation="discover_all_markets",
            outcome="SUCCESS" if spot or futures else "FAILURE",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            eligible_count=spot + futures,
            recommendation=None if spot or futures else "Both public exchange metadata requests returned no eligible symbols; inspect preceding exchange_metadata_failed events.",
        )
        return result