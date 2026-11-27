"""Market scanner: coordinates data collection and tiered analysis."""
from __future__ import annotations

import asyncio
import math
import time
import logging
from asyncio import Semaphore
from datetime import datetime, timezone

from core.event_bus import EventBus
from core.event_models import EventType, make_event
from exchange.futures_client import FuturesClient
from exchange.spot_client import SpotClient
from exchange.symbol_registry import SymbolRegistry
from market.candle_manager import TIMEFRAME_SECONDS
from market.market_cache import MarketCache
from market.data_reliability import valid_price, valid_volume
from core.observability import log_event

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
        self._refresh_retry_state: dict[tuple[str, str, str], tuple[int, float]] = {}
        self._scan_status: dict[str, dict] = {market: {"state": "IDLE", "started_at": None, "completed_at": None, "symbols_selected": 0, "timeframes_configured": list(self.analysis_timeframes), "refresh_successes": 0, "refresh_failures": 0, "refresh_skipped": 0, "last_error": None} for market in ("SPOT", "FUTURES")}

    def status_snapshot(self) -> dict:
        return {
            "running": self._running,
            "markets": {market: {**status, "timeframes_configured": list(status["timeframes_configured"])} for market, status in self._scan_status.items()},
            "configured_timeframes": list(self.analysis_timeframes),
            "analysis_batch_size": self.analysis_symbol_limit,
            "scan_all_eligible": self.scan_all_eligible,
            "stream_symbol_limit": self.stream_symbol_limit,
            "max_concurrent_scans": self.max_concurrent_scans,
        }

    def _record_refresh_failure(self, market: str, symbol: str, timeframe: str) -> None:
        key = (market, symbol, timeframe)
        attempts = self._refresh_retry_state.get(key, (0, 0.0))[0] + 1
        delay = min(300.0, 60.0 * (2 ** min(attempts - 1, 3)))
        self._refresh_retry_state[key] = (attempts, time.monotonic() + delay)

    async def _analyze_market(self, market: str) -> None:
        """Refresh candles for the most liquid symbols, then run strategy analysis."""
        if self.candle_manager is None or self.intelligence is None:
            log_event(
                logger, logging.WARNING, "scanner_analysis_unavailable",
                component="scanner", operation="analyze_market",
                market=market, outcome="SKIPPED",
                recommendation="Initialize the candle manager and intelligence core before starting market scans.",
            )
            return
        analysis_started = time.perf_counter()
        snapshots = self.cache.get_market_tickers(market)
        candidates = [
            item for item in snapshots
            if item.get("symbol") and float(item.get("volume_24h") or 0) > 0
            and self.registry.is_eligible(item["symbol"], market)
        ]
        candidates.sort(key=lambda item: float(item.get("volume_24h") or 0), reverse=True)
        if not candidates:
            self._scan_status[market].update({"state": "NO_ELIGIBLE_DATA", "completed_at": datetime.now(timezone.utc).isoformat(), "last_error": "No eligible ticker snapshot available"})
            log_event(
                logger, logging.WARNING, "scanner_candidates_unavailable",
                component="scanner", operation="filter_and_rank_symbols",
                market=market, outcome="FAILURE",
                recommendation="Wait for ticker retrieval and verify the exchange market is enabled and eligible symbols are registered.",
            )
            return

        # Rotate through the full eligible universe in bounded batches. This avoids
        # permanently ignoring symbols beyond the first page while controlling REST load.
        batch_size = min(self.analysis_symbol_limit, len(candidates) if self.scan_all_eligible else self.analysis_symbol_limit)
        offset = self._analysis_offsets.get(market, 0)
        if self.scan_all_eligible:
            end = offset + batch_size
            selected = candidates[offset:end] + candidates[:max(0, end - len(candidates))]
            self._analysis_offsets[market] = end % len(candidates)
        else:
            selected = candidates[:batch_size]
            self._analysis_offsets[market] = 0
        prioritized = [(market, str(item["symbol"])) for item in selected]
        if not prioritized:
            return
        log_event(
            logger, logging.INFO, "scanner_candidates_ranked",
            component="scanner", operation="filter_and_rank_symbols",
            market=market, outcome="SUCCESS",
            symbol_count=len(snapshots), candidate_count=len(candidates),
            symbols_selected=len(prioritized),
            details=f"ranking=quote_volume_desc; scan_all_eligible={self.scan_all_eligible}; offset={offset}",
        )

        status = self._scan_status[market]
        scan_started = time.perf_counter()
        status.update({"state": "SCANNING", "started_at": datetime.now(timezone.utc).isoformat(),
                       "symbols_selected": len(prioritized), "refresh_successes": 0,
                       "refresh_failures": 0, "refresh_skipped": 0, "last_error": None})
        log_event(logger, logging.INFO, "scanner_batch_started", component="scanner", market=market, symbols_selected=len(prioritized))
        semaphore = Semaphore(self.max_concurrent_scans)

        def needs_refresh(symbol: str, timeframe: str) -> bool:
            latest = self.candle_manager.get_series(market, symbol, timeframe, limit=1)
            if latest:
                age_seconds = (self.candle_manager.current_time_ms() - latest[-1]["close_time"]) / 1000
                if 0 <= age_seconds < TIMEFRAME_SECONDS[timeframe] + 120:
                    self._refresh_retry_state.pop((market, symbol, timeframe), None)
                    return False
            retry_state = self._refresh_retry_state.get((market, symbol, timeframe))
            return retry_state is None or retry_state[1] <= time.monotonic()

        async def refresh(symbol: str, timeframe: str) -> bool:
            async with semaphore:
                try:
                    await self.candle_manager.collect_historical(
                        self.spot_client, self.futures_client, market, symbol, timeframe, limit=200,
                    )
                    collection = self.candle_manager.get_collection_status(market, symbol, timeframe)
                    if collection and collection.get("state") == "FAILED":
                        status["refresh_failures"] += 1
                        status["last_error"] = f"{symbol} {timeframe}: {collection.get('error')}"
                        self._record_refresh_failure(market, symbol, timeframe)
                        log_event(
                            logger, logging.ERROR, "scanner_candle_refresh_failed",
                            component="scanner", operation="refresh_candles",
                            market=market, symbol=symbol, outcome="FAILURE",
                            details=f"timeframe={timeframe}; error={collection.get('error')}",
                            recommendation="Check public kline API connectivity, symbol eligibility, interval support, and exchange rate limits.",
                        )
                        return False
                    succeeded = bool(collection and collection.get("state") == "SUCCESS")
                    if succeeded:
                        self._refresh_retry_state.pop((market, symbol, timeframe), None)
                    else:
                        status["refresh_failures"] += 1
                        status["last_error"] = f"{symbol} {timeframe}: refresh_not_confirmed"
                        self._record_refresh_failure(market, symbol, timeframe)
                        log_event(
                            logger, logging.ERROR, "scanner_candle_refresh_unconfirmed",
                            component="scanner", operation="refresh_candles",
                            market=market, symbol=symbol, outcome="FAILURE",
                            details=f"timeframe={timeframe}; collector did not confirm success",
                            recommendation="Inspect candle collection status and the exchange response for this symbol and interval.",
                        )
                    return succeeded
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    status["refresh_failures"] += 1
                    status["last_error"] = f"{symbol} {timeframe}: {type(exc).__name__}"
                    self._record_refresh_failure(market, symbol, timeframe)
                    log_event(
                        logger, logging.ERROR, "scanner_candle_refresh_exception",
                        component="scanner", operation="refresh_candles",
                        market=market, symbol=symbol, outcome="FAILURE",
                        error_type=type(exc).__name__,
                        details=f"timeframe={timeframe}",
                        recommendation="Inspect the traceback and exchange response; retries use bounded backoff.",
                    )
                    logger.warning("Candle refresh failed for %s %s %s: %s", market, symbol, timeframe, exc)
                    return False

        refresh_jobs = [
            refresh(symbol, timeframe)
            for _market, symbol in prioritized
            for timeframe in self.analysis_timeframes
            if needs_refresh(symbol, timeframe)
        ]
        status["refresh_skipped"] = len(prioritized) * len(self.analysis_timeframes) - len(refresh_jobs)
        results = await asyncio.gather(*refresh_jobs, return_exceptions=True)
        status["refresh_successes"] = sum(result is True for result in results)
        status["refresh_failures"] += sum(isinstance(result, BaseException) for result in results)
        try:
            strategy_started = time.perf_counter()
            await self.intelligence.run_prioritized_scan(prioritized)
            log_event(
                logger, logging.INFO, "scanner_strategy_analysis_completed",
                component="scanner", operation="run_prioritized_scan",
                market=market, outcome="SUCCESS",
                symbols_selected=len(prioritized),
                duration_ms=round((time.perf_counter() - strategy_started) * 1000, 2),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            status["last_error"] = f"strategy scan: {type(exc).__name__}"
            log_event(
                logger, logging.ERROR, "scanner_strategy_analysis_failed",
                component="scanner", operation="run_prioritized_scan",
                market=market, outcome="FAILURE",
                exception_type=type(exc).__name__,
                recommendation="Inspect the strategy traceback and check candle integrity and feature/model inputs.",
            )
            logger.exception("Strategy scan batch failed for %s", market)
        status["completed_at"] = datetime.now(timezone.utc).isoformat()
        status["state"] = "DEGRADED" if status["refresh_failures"] or status["last_error"] else "COMPLETE"
        log_event(logger, logging.INFO if status["state"] == "COMPLETE" else logging.WARNING,
                  "scanner_batch_completed", component="scanner", market=market,
                  scanner_state=status["state"], symbols_selected=len(prioritized),
                  refresh_successes=status["refresh_successes"], refresh_failures=status["refresh_failures"],
                  refresh_skipped=status["refresh_skipped"],
                  duration_ms=round((time.perf_counter() - scan_started) * 1000, 2))
        log_event(
            logger,
            logging.INFO if status["state"] == "COMPLETE" else logging.WARNING,
            "scanner_market_analysis_summary",
            component="scanner", operation="refresh_and_analyze_market",
            market=market, outcome=status["state"],
            symbols_selected=len(prioritized),
            timeframe_count=len(self.analysis_timeframes),
            refresh_successes=status["refresh_successes"],
            refresh_failures=status["refresh_failures"],
            refresh_skipped=status["refresh_skipped"],
            duration_ms=round((time.perf_counter() - analysis_started) * 1000, 2),
            recommendation=None if status["state"] == "COMPLETE" else "Inspect failed symbol/timeframe events; successful refreshes are retained and failed pairs use bounded retries.",
        )

    async def _handle_stream_message(self, market: str, message: dict) -> None:
        """Consume validated Binance ticker events into the shared cache."""
        payload = message.get("data", message) if isinstance(message, dict) else {}
        if not isinstance(payload, dict):
            return
        symbol = payload.get("s") or payload.get("symbol")
        if not symbol or not self.registry.is_eligible(str(symbol), market):
            return
        symbol = str(symbol).upper()
        is_book_ticker = payload.get("e") == "bookTicker"
        if is_book_ticker:
            try:
                bid = float(payload.get("b", payload.get("bidPrice", 0)))
                ask = float(payload.get("a", payload.get("askPrice", 0)))
            except (TypeError, ValueError, OverflowError):
                return
            if not valid_price(bid) or not valid_price(ask) or ask < bid:
                return
            price = (bid + ask) / 2
            volume = self.cache.get_volume(market, symbol)
            change = self.cache.get_change(market, symbol)
            if volume is None or change is None:
                return
        else:
            try:
                price = float(payload.get("c", payload.get("lastPrice", 0)))
                volume = float(payload.get("q", payload.get("quoteVolume", 0)))
                change = float(payload.get("P", payload.get("priceChangePercent", 0)))
            except (TypeError, ValueError, OverflowError):
                return
        try:
            event_time_ms = int(payload.get("E", payload.get("T", 0)))
        except (TypeError, ValueError, OverflowError):
            return
        client = self.spot_client if market == "SPOT" else self.futures_client
        exchange_now = getattr(client, "now_ms", None)
        now_ms = exchange_now() if callable(exchange_now) else int(time.time() * 1000)
        if event_time_ms and (event_time_ms > now_ms + 5_000 or event_time_ms < now_ms - 120_000):
            return
        if valid_price(price) and valid_volume(volume) and math.isfinite(change):
            data_source = "WEBSOCKET_BOOK" if is_book_ticker else "WEBSOCKET"
            if is_book_ticker:
                self.cache.update_book_ticker(market, symbol, price)
            else:
                self.cache.update_ticker(market, symbol, price, volume, change, source=data_source)
            # Fan out validated stream data through the existing shared EventBus.
            publish = getattr(self.event_bus, "publish", None)
            if callable(publish):
                await publish(make_event(
                    EventType.MARKET_DATA, "scanner.websocket", symbol=symbol,
                    market=market, price=price, volume_24h=volume,
                    price_change_24h_pct=change, exchange_event_time_ms=event_time_ms or None,
                    data_source=data_source,
                ))

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
        futures_streams = [f"{symbol}@bookTicker" for symbol in self._stream_symbols["FUTURES"]]
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
                await client.sync_clock_if_due()
                ticker_started = time.perf_counter()
                tickers = await client.get_all_tickers()
                eligible_tickers = 0
                for ticker in tickers:
                    symbol = ticker.get("symbol")
                    if not self.registry.is_eligible(symbol, market):
                        continue
                    try:
                        price = float(ticker.get("lastPrice", 0))
                        volume = float(ticker.get("quoteVolume", 0))
                        change = float(ticker.get("priceChangePercent", 0))
                    except (TypeError, ValueError, OverflowError):
                        continue
                    if not valid_price(price) or not valid_volume(volume) or not math.isfinite(change):
                        continue
                    self.cache.update_ticker(market, symbol, price, volume, change, source="REST")
                    eligible_tickers += 1
                log_event(
                    logger, logging.INFO, "scanner_tickers_retrieved",
                    component="scanner", operation="retrieve_and_validate_tickers",
                    market=market, outcome="SUCCESS",
                    symbol_count=len(tickers), eligible_count=eligible_tickers,
                    duration_ms=round((time.perf_counter() - ticker_started) * 1000, 2),
                )
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
                log_event(
                    logger, logging.ERROR, "scanner_ticker_scan_failed",
                    component="scanner", operation="retrieve_and_validate_tickers",
                    market=market, outcome="FAILURE",
                    exception_type=type(exc).__name__,
                    recommendation="Check Binance public market-data reachability, rate limits, and exchange client logs.",
                )
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
        log_event(
            logger, logging.INFO, "scanner_started",
            component="scanner", operation="start",
            outcome="SUCCESS",
            details=f"markets={','.join(sorted(self.enabled_markets))}; batch_size={self.analysis_symbol_limit}; concurrency={self.max_concurrent_scans}",
            timeframe_count=len(self.analysis_timeframes),
        )

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        log_event(
            logger, logging.INFO, "scanner_stopped",
            component="scanner", operation="stop", outcome="SUCCESS",
        )
