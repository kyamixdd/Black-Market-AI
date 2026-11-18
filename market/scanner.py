"""Market scanner: coordinates data collection and tiered analysis."""
from __future__ import annotations

import asyncio
import logging

from core.event_bus import EventBus
from core.event_models import EventType, make_event
from config import SPOT_ENABLED, USDM_FUTURES_ENABLED
from exchange.futures_client import FuturesClient
from exchange.spot_client import SpotClient
from exchange.symbol_registry import SymbolRegistry
from market.market_cache import MarketCache

logger = logging.getLogger(__name__)


class Scanner:
    def __init__(self, event_bus: EventBus, registry: SymbolRegistry,
                 cache: MarketCache, spot_client: SpotClient,
                 futures_client: FuturesClient):
        self.event_bus = event_bus
        self.registry = registry
        self.cache = cache
        self.spot_client = spot_client
        self.futures_client = futures_client
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def _scan_market_tickers(self, market: str) -> None:
        client = self.spot_client if market == "SPOT" else self.futures_client
        while self._running:
            try:
                tickers = await client.get_all_tickers()
                for t in tickers:
                    symbol = t.get("symbol")
                    if not self.registry.is_eligible(symbol, market):
                        continue
                    price = float(t.get("lastPrice", 0))
                    volume = float(t.get("quoteVolume", 0))
                    change = float(t.get("priceChangePercent", 0))
                    if price <= 0:
                        continue
                    self.cache.update_ticker(market, symbol, price, volume, change)
                    # Publish a per-symbol price event so paper positions, pending
                    # limit orders, and subscribed dashboard clients receive updates.
                    await self.event_bus.publish(make_event(
                        EventType.MARKET_DATA,
                        "scanner",
                        symbol=symbol,
                        market=market,
                        price=price,
                        volume_24h=volume,
                        price_change_24h=change,
                    ))
                await self.event_bus.publish(make_event(
                    EventType.MARKET_SNAPSHOT, "scanner", market=market,
                    count=len(tickers)
                ))
            except Exception as exc:
                logger.error("%s ticker scan failed: %s", market, exc)
            await asyncio.sleep(30)

    async def _scan_futures_extra(self) -> None:
        while self._running:
            try:
                # Mark prices & Funding
                marks = await self.futures_client.get_mark_price()
                for m in marks:
                    symbol = m.get("symbol")
                    if not self.registry.is_eligible(symbol, "FUTURES"):
                        continue
                    mark_price = float(m.get("markPrice", 0))
                    funding_rate = float(m.get("lastFundingRate", 0))
                    self.cache.update_mark("FUTURES", symbol, mark_price, funding_rate)
                    if mark_price > 0:
                        await self.event_bus.publish(make_event(
                            EventType.MARKET_DATA,
                            "scanner",
                            symbol=symbol,
                            market="FUTURES",
                            mark_price=mark_price,
                            funding_rate=funding_rate,
                        ))
            except Exception as exc:
                logger.error("Futures extra scan failed: %s", exc)
            await asyncio.sleep(60)

    async def start(self) -> None:
        self._running = True
        if SPOT_ENABLED:
            self._tasks.append(asyncio.create_task(self._scan_market_tickers("SPOT")))
        if USDM_FUTURES_ENABLED:
            self._tasks.append(asyncio.create_task(self._scan_market_tickers("FUTURES")))
            self._tasks.append(asyncio.create_task(self._scan_futures_extra()))
        logger.info("Scanner started")

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()