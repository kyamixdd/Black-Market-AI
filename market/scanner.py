"""Market scanner: coordinates data collection and tiered analysis."""
from __future__ import annotations

import asyncio
import logging

from core.event_bus import EventBus
from core.event_models import EventType, make_event
from exchange.futures_client import FuturesClient
from exchange.spot_client import SpotClient
from exchange.symbol_registry import SymbolRegistry
from market.market_cache import MarketCache

logger = logging.getLogger(__name__)


class Scanner:
    def __init__(
        self,
        event_bus: EventBus,
        registry: SymbolRegistry,
        cache: MarketCache,
        spot_client: SpotClient,
        futures_client: FuturesClient,
        candle_manager=None,
        intelligence=None,
        analysis_symbol_limit: int = 10,
    ):
        self.event_bus = event_bus
        self.registry = registry
        self.cache = cache
        self.spot_client = spot_client
        self.futures_client = futures_client
        self.candle_manager = candle_manager
        self.intelligence = intelligence
        from config import SCAN_ALL_ELIGIBLE_SYMBOLS, SPOT_ENABLED, USDM_FUTURES_ENABLED, TIMEFRAMES

        self.analysis_symbol_limit = 50 if SCAN_ALL_ELIGIBLE_SYMBOLS else max(1, int(analysis_symbol_limit))
        self.enabled_markets = {
            market for market, enabled in (("SPOT", SPOT_ENABLED), ("FUTURES", USDM_FUTURES_ENABLED))
            if enabled
        }
        self.analysis_timeframes = tuple(TIMEFRAMES)
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def _analyze_market(self, market: str) -> None:
        """Refresh candles for the most liquid symbols, then run strategy analysis."""
        if self.candle_manager is None or self.intelligence is None:
            return
        snapshots = self.cache.get_market_tickers(market)
        candidates = [
            item for item in snapshots
            if item.get("symbol") and float(item.get("volume_24h") or 0) > 0
            and self.registry.is_eligible(item["symbol"], market)
        ]
        candidates.sort(key=lambda item: float(item.get("volume_24h") or 0), reverse=True)
        prioritized = [
            (market, str(item["symbol"]))
            for item in candidates[:self.analysis_symbol_limit]
        ]
        if not prioritized:
            return

        # Refresh each configured analysis timeframe for the prioritized universe.
        for _market, symbol in prioritized:
            for timeframe in self.analysis_timeframes:
                await self.candle_manager.collect_historical(
                    self.spot_client, self.futures_client,
                    market, symbol, timeframe, limit=200,
                )
        await self.intelligence.run_prioritized_scan(prioritized)

    async def _scan_market_tickers(self, market: str) -> None:
        client = self.spot_client if market == "SPOT" else self.futures_client
        while self._running:
            try:
                if market not in self.enabled_markets:
                    await asyncio.sleep(1)
                    continue
                tickers = await client.get_all_tickers()
                for ticker in tickers:
                    symbol = ticker.get("symbol")
                    if not self.registry.is_eligible(symbol, market):
                        continue
                    price = float(ticker.get("lastPrice", 0))
                    volume = float(ticker.get("quoteVolume", 0))
                    change = float(ticker.get("priceChangePercent", 0))
                    if price <= 0:
                        continue
                    self.cache.update_ticker(market, symbol, price, volume, change)
                await self.event_bus.publish(make_event(
                    EventType.MARKET_SNAPSHOT, "scanner", market=market,
                    count=len(tickers)
                ))
                await self._analyze_market(market)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("%s ticker scan failed: %s", market, exc)
            await asyncio.sleep(30)

    async def _scan_futures_extra(self) -> None:
        while self._running:
            try:
                if "FUTURES" not in self.enabled_markets:
                    await asyncio.sleep(1)
                    continue
                marks = await self.futures_client.get_mark_price()
                if isinstance(marks, dict):
                    marks = [marks]
                for item in marks:
                    symbol = item.get("symbol")
                    if not self.registry.is_eligible(symbol, "FUTURES"):
                        continue
                    mark_price = float(item.get("markPrice", 0))
                    funding_rate = float(item.get("lastFundingRate", 0))
                    if mark_price > 0:
                        self.cache.update_mark(
                            "FUTURES", symbol, mark_price, funding_rate
                        )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Futures extra scan failed: %s", exc)
            await asyncio.sleep(60)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._tasks.append(asyncio.create_task(self._scan_market_tickers("SPOT")))
        self._tasks.append(asyncio.create_task(self._scan_market_tickers("FUTURES")))
        self._tasks.append(asyncio.create_task(self._scan_futures_extra()))
        logger.info("Scanner started")

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
