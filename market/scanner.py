"""Market scanner: coordinates data collection and tiered analysis."""
from __future__ import annotations

import asyncio
import logging
from asyncio import Semaphore

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
        analysis_symbol_limit: int = 50,
        websocket_manager=None,
        max_concurrent_scans: int = 8,
    ):
        self.event_bus = event_bus
        self.registry = registry
        self.cache = cache
        self.spot_client = spot_client
        self.futures_client = futures_client
        self.candle_manager = candle_manager
        self.intelligence = intelligence
        self.websocket_manager = websocket_manager
        self.max_concurrent_scans = max(1, int(max_concurrent_scans))
        self._analysis_offsets: dict[str, int] = {"SPOT": 0, "FUTURES": 0}
        self._stream_symbols: dict[str, tuple[str, ...]] = {"SPOT": (), "FUTURES": ()}
        from config import SCAN_ALL_ELIGIBLE_SYMBOLS, SPOT_ENABLED, USDM_FUTURES_ENABLED, TIMEFRAMES, SCANNER_ANALYSIS_BATCH_SIZE, SCANNER_STREAM_SYMBOL_LIMIT, MAX_CONCURRENT_SCANS

        self.scan_all_eligible = bool(SCAN_ALL_ELIGIBLE_SYMBOLS)
        self.analysis_symbol_limit = max(1, int(SCANNER_ANALYSIS_BATCH_SIZE or analysis_symbol_limit))
        self.stream_symbol_limit = max(1, int(SCANNER_STREAM_SYMBOL_LIMIT))
        self.max_concurrent_scans = max(1, int(MAX_CONCURRENT_SCANS))
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
        if not candidates:
            return

        # Rotate through the full eligible universe in bounded batches. This avoids
        # permanently ignoring symbols beyond the first page while controlling REST load.
        batch_size = self.analysis_symbol_limit
        offset = self._analysis_offsets.get(market, 0)
        if self.scan_all_eligible:
            selected = (candidates + candidates)[offset:offset + batch_size]
            self._analysis_offsets[market] = (offset + batch_size) % len(candidates)
        else:
            selected = candidates[:batch_size]
            self._analysis_offsets[market] = 0
        prioritized = [(market, str(item["symbol"])) for item in selected]
        if not prioritized:
            return

        semaphore = Semaphore(self.max_concurrent_scans)

        async def refresh(symbol: str, timeframe: str) -> None:
            async with semaphore:
                await self.candle_manager.collect_historical(
                    self.spot_client, self.futures_client, market, symbol, timeframe, limit=200,
                )

        # Populate every configured timeframe for each rotating symbol batch with
        # bounded concurrency; one slow endpoint cannot block the entire scan.
        await asyncio.gather(*(
            refresh(symbol, timeframe)
            for _market, symbol in prioritized
            for timeframe in self.analysis_timeframes
        ))
        await self.intelligence.run_prioritized_scan(prioritized)

    async def _handle_stream_message(self, market: str, message: dict) -> None:
        """Consume Binance combined-stream 24h ticker events into the shared cache."""
        payload = message.get("data", message) if isinstance(message, dict) else {}
        if not isinstance(payload, dict):
            return
        symbol = payload.get("s") or payload.get("symbol")
        if not symbol or not self.registry.is_eligible(str(symbol), market):
            return
        try:
            price = float(payload.get("c", payload.get("lastPrice", 0)))
            volume = float(payload.get("q", payload.get("quoteVolume", 0)))
            change = float(payload.get("P", payload.get("priceChangePercent", 0)))
        except (TypeError, ValueError):
            return
        if price > 0 and volume >= 0:
            self.cache.update_ticker(market, str(symbol), price, volume, change)

    async def _refresh_stream_subscriptions(self, market: str) -> None:
        if self.websocket_manager is None:
            return
        candidates = [
            item for item in self.cache.get_market_tickers(market)
            if item.get("symbol") and self.registry.is_eligible(item["symbol"], market)
        ]
        candidates.sort(key=lambda item: float(item.get("volume_24h") or 0), reverse=True)
        # Use a bounded liquid universe for live ticker streams; the scanner rotates
        # through the full eligible universe for historical/timeframe analysis.
        selected = tuple(str(item["symbol"]).lower() for item in candidates[:self.stream_symbol_limit])
        if selected == self._stream_symbols.get(market):
            return
        self._stream_symbols[market] = selected
        spot_streams = [f"{symbol}@ticker" for symbol in self._stream_symbols["SPOT"]]
        futures_streams = [f"{symbol}@ticker" for symbol in self._stream_symbols["FUTURES"]]
        try:
            await self.websocket_manager.start(spot_streams, futures_streams)
        except Exception:
            logger.exception("Unable to refresh Binance ticker stream subscriptions")

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
                await self._refresh_stream_subscriptions(market)
                await self.event_bus.publish(make_event(
                    EventType.MARKET_SNAPSHOT, "scanner", market=market,
                    count=len(tickers), eligible=len(self.registry.list_symbols(market)),
                    analyzed_batch=min(self.analysis_symbol_limit, len(self.registry.list_symbols(market))),
                    timeframes=list(self.analysis_timeframes),
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

    async def _stream_handler(self, message: dict) -> None:
        market = message.get("_market") if isinstance(message, dict) else None
        if market in {"SPOT", "FUTURES"}:
            await self._handle_stream_message(market, message)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._tasks.append(asyncio.create_task(self._scan_market_tickers("SPOT")))
        if self.websocket_manager is not None:
            self.websocket_manager.add_handler(self._stream_handler)
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
