"""Disaster Recovery and Long-Run Stability: backups, replay, idempotency, and recovery."""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import inspect
import json
import logging
import os
import shutil
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from config import BACKUP_DIR, DATABASE_URL
from database.connection import Database

logger = logging.getLogger(__name__)


@dataclass
class BackupConfig:
    """Configuration for automated backups."""
    backup_dir: Path = BACKUP_DIR
    max_backups: int = 30
    backup_interval_hours: int = 6
    compress: bool = True
    verify_after_backup: bool = True


@dataclass
class RecoveryPoint:
    """A point-in-time recovery marker."""
    timestamp: datetime
    backup_path: Path
    event_id: Optional[str] = None
    description: str = ""


class DatabaseBackupManager:
    """Manages SQLite database backups with integrity verification."""

    def __init__(self, config: BackupConfig, db: Database):
        self.config = config
        self.db = db
        self.config.backup_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def create_backup(self, description: str = "scheduled") -> Path:
        """Create a verified database backup."""
        with self._lock:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            db_name = self._extract_db_name()
            backup_name = f"{db_name}_{timestamp}_{description}"
            backup_path = self.config.backup_dir / backup_name

            if self.config.compress:
                backup_path = backup_path.with_suffix(".db.gz")
            else:
                backup_path = backup_path.with_suffix(".db")

            # Perform backup using SQLite's backup API
            self._perform_backup(backup_path)

            # Verify integrity
            if self.config.verify_after_backup:
                if not self._verify_backup(backup_path):
                    backup_path.unlink(missing_ok=True)
                    raise RuntimeError("Backup verification failed")

            # Prune old backups
            self._prune_old_backups()

            logger.info(f"Backup created: {backup_path}")
            return backup_path

    def _extract_db_name(self) -> str:
        """Extract database name from URL."""
        db_url = self.db.url
        if "sqlite:///" in db_url:
            path = db_url.replace("sqlite:///", "")
            return Path(path).stem
        return "blackmarket"

    def _get_source_path(self) -> str:
        """Get the actual SQLite file path."""
        db_url = self.db.url
        if "sqlite:///" in db_url:
            path = db_url.replace("sqlite:///", "")
            return path
        elif db_url.startswith("sqlite://"):
            path = db_url.replace("sqlite://", "")
            return path
        raise ValueError("Only SQLite databases supported")

    def _perform_backup(self, backup_path: Path) -> None:
        """Perform the actual backup using SQLite backup API."""
        source_path = self._get_source_path()

        source = sqlite3.connect(source_path)
        try:
            if self.config.compress:
                # Backup to temporary file then compress
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                try:
                    dest = sqlite3.connect(str(tmp_path))
                    source.backup(dest)
                    dest.close()

                    # Compress
                    with open(tmp_path, "rb") as f_in:
                        with gzip.open(backup_path, "wb") as f_out:
                            shutil.copyfileobj(f_in, f_out)
                finally:
                    tmp_path.unlink(missing_ok=True)
            else:
                dest = sqlite3.connect(str(backup_path))
                source.backup(dest)
                dest.close()
        finally:
            source.close()

    def _verify_backup(self, backup_path: Path) -> bool:
        """Verify backup integrity by opening and running PRAGMA integrity_check."""
        try:
            if self.config.compress:
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                try:
                    with gzip.open(backup_path, "rb") as f_in:
                        with open(tmp_path, "wb") as f_out:
                            shutil.copyfileobj(f_in, f_out)

                    # Verify the decompressed file
                    conn = sqlite3.connect(str(tmp_path))
                    try:
                        cursor = conn.cursor()
                        cursor.execute("PRAGMA integrity_check")
                        result = cursor.fetchone()
                        return result[0] == "ok"
                    finally:
                        conn.close()
                finally:
                    tmp_path.unlink(missing_ok=True)
            else:
                conn = sqlite3.connect(str(backup_path))
                try:
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA integrity_check")
                    result = cursor.fetchone()
                    return result[0] == "ok"
                finally:
                    conn.close()
        except Exception as e:
            logger.error(f"Backup verification failed: {e}")
            return False

    def _prune_old_backups(self) -> None:
        """Remove old backups beyond max_backups."""
        backups = sorted(
            self.config.backup_dir.glob("*.db*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        for old_backup in backups[self.config.max_backups:]:
            old_backup.unlink(missing_ok=True)
            logger.info(f"Pruned old backup: {old_backup}")

    def restore_backup(self, backup_path: Path, target_path: Optional[Path] = None) -> bool:
        """Restore a verified SQLite backup atomically and reopen the live database."""
        with self._lock:
            if not backup_path.exists():
                logger.error("Backup not found: %s", backup_path)
                return False
            if target_path is None:
                target_path = Path(self._get_source_path())
            target_path = Path(target_path)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path: Path | None = None
            try:
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".restore.db", dir=target_path.parent, delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                if self.config.compress:
                    with gzip.open(backup_path, "rb") as source, open(tmp_path, "wb") as dest:
                        shutil.copyfileobj(source, dest)
                else:
                    shutil.copy2(backup_path, tmp_path)

                check = sqlite3.connect(str(tmp_path))
                try:
                    integrity = check.execute("PRAGMA integrity_check").fetchone()
                    if not integrity or integrity[0] != "ok":
                        raise RuntimeError("Backup failed SQLite integrity_check")
                finally:
                    check.close()

                live_target = target_path.resolve() == Path(self._get_source_path()).resolve()
                if live_target:
                    try:
                        with self.db.engine.connect() as connection:
                            connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
                    except Exception:
                        logger.debug("WAL checkpoint before restore skipped", exc_info=True)
                    self.db.close()

                for suffix in ("-wal", "-shm"):
                    Path(str(target_path) + suffix).unlink(missing_ok=True)
                os.replace(tmp_path, target_path)
                tmp_path = None
                if live_target:
                    self.db.init_db()
                logger.info("Restored database from %s", backup_path)
                return True
            except Exception as exc:
                logger.error("Restore failed: %s", exc, exc_info=True)
                return False
            finally:
                if tmp_path is not None:
                    tmp_path.unlink(missing_ok=True)


class IdempotentEventProcessor:
    """Ensures events are processed exactly once using deduplication."""

    def __init__(self, db: Database):
        self.db = db
        self._processed_cache: set[str] = set()
        self._cache_lock = threading.RLock()
        self._max_cache_size = 100000
        self._load_processed_ids()

    def _load_processed_ids(self) -> None:
        """Load recently processed event IDs from database."""
        from database.repositories import Repository
        repo = Repository(self.db.session_maker())
        # Load last 100k event IDs
        events = repo.get_system_events(limit=100000)
        with self._cache_lock:
            self._processed_cache = {e.event_id for e in events}

    def is_processed(self, event_id: str) -> bool:
        """Check if event was already processed."""
        with self._cache_lock:
            if event_id in self._processed_cache:
                return True
            # Check database for older events
            from database.repositories import Repository
            repo = Repository(self.db.session_maker())
            return repo.event_exists(event_id)

    def mark_processed(self, event_id: str) -> None:
        """Mark event as processed."""
        with self._cache_lock:
            self._processed_cache.add(event_id)
            if len(self._processed_cache) > self._max_cache_size:
                # Remove oldest entries (simple FIFO)
                self._processed_cache = set(list(self._processed_cache)[-self._max_cache_size:])

    def process_event(self, event_id: str, handler: Callable[[], Any]) -> tuple[bool, Any]:
        """
        Process event with idempotency guarantee.

        Returns:
            (was_processed, result) - was_processed=True means event was already handled
        """
        if self.is_processed(event_id):
            logger.debug(f"Event {event_id} already processed, skipping")
            return True, None

        # Process the event
        result = handler()

        # Mark as processed
        self.mark_processed(event_id)

        return False, result


class PersistentEventQueue:
    """Persistent queue for critical events that must not be lost."""

    def __init__(self, db: Database, queue_name: str = "critical_events"):
        self.db = db
        self.queue_name = queue_name
        self._lock = threading.RLock()
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Ensure queue table exists."""
        from database.connection import Database
        # Table creation handled by database migrations
        pass

    def enqueue(self, event_type: str, payload: dict, priority: int = 0) -> str:
        """Add event to persistent queue."""
        import uuid
        event_id = str(uuid.uuid4())[:8]
        with self._lock:
            # Store in database
            from database.repositories import Repository
            repo = Repository(self.db.session_maker())
            repo.save_system_event({
                "event_id": event_id,
                "event_type": f"QUEUE_{self.queue_name}_{event_type}",
                "source": "PersistentEventQueue",
                "symbol": None,
                "market": None,
                "payload": json.dumps({
                    "queue": self.queue_name,
                    "type": event_type,
                    "payload": payload,
                    "priority": priority,
                    "enqueued_at": datetime.now(timezone.utc).isoformat(),
                }),
            })
        return event_id

    def dequeue(self, limit: int = 100) -> list[dict]:
        """Dequeue events for processing."""
        with self._lock:
            # This would need a proper queue table implementation
            # For now, return empty - full implementation needs queue table
            return []

    def mark_completed(self, event_id: str) -> None:
        """Mark queue event as completed."""
        with self._lock:
            from database.repositories import Repository
            repo = Repository(self.db.session_maker())
            repo.update_system_event_status(event_id, "COMPLETED")


class PositionRecoveryManager:
    """Recovers paper trading positions after restart."""

    def __init__(self, db: Database, simulator):
        self.db = db
        self.simulator = simulator
        self._lock = threading.RLock()

    def recover_positions(self) -> dict[str, int]:
        """Recover all open positions from database."""
        with self._lock:
            from database.repositories import Repository
            repo = Repository(self.db.session_maker())

            recovered = {"spot": 0, "futures": 0, "orders": 0}

            # Recover spot positions
            for pos in repo.get_open_positions("SPOT"):
                self.simulator.spot_positions[pos.position_id] = {
                    "position_id": pos.position_id,
                    "symbol": pos.symbol,
                    "market": pos.market,
                    "side": pos.side,
                    "entry_price": pos.entry_price,
                    "amount": pos.amount,
                    "current_price": pos.current_price,
                    "stop_loss": pos.stop_loss,
                    "take_profit": pos.take_profit,
                    "leverage": pos.leverage,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "realized_pnl": pos.realized_pnl,
                    "fees_paid": pos.fees_paid,
                    "last_funding_time": pos.last_funding_time or 0,
                    "reserved_notional": pos.reserved_notional or (pos.entry_price * pos.amount),
                    "order_id": pos.order_id,
                    "signal_id": pos.signal_id,
                    "strategy": pos.strategy,
                    "order_type": pos.order_type,
                    "status": pos.status,
                    "opened_at": pos.opened_at,
                }
                recovered["spot"] += 1

            # Recover futures positions
            for pos in repo.get_open_positions("FUTURES"):
                self.simulator.futures_positions[pos.position_id] = {
                    "position_id": pos.position_id,
                    "symbol": pos.symbol,
                    "market": pos.market,
                    "side": pos.side,
                    "entry_price": pos.entry_price,
                    "amount": pos.amount,
                    "current_price": pos.current_price,
                    "stop_loss": pos.stop_loss,
                    "take_profit": pos.take_profit,
                    "leverage": pos.leverage,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "realized_pnl": pos.realized_pnl,
                    "fees_paid": pos.fees_paid,
                    "last_funding_time": pos.last_funding_time or 0,
                    "reserved_notional": pos.reserved_notional or (pos.entry_price * pos.amount),
                    "reserved_margin": pos.reserved_margin or (pos.entry_price * pos.amount / max(float(pos.leverage or 1.0), 1.0)),
                    "order_id": pos.order_id,
                    "signal_id": pos.signal_id,
                    "strategy": pos.strategy,
                    "order_type": pos.order_type,
                    "status": pos.status,
                    "opened_at": pos.opened_at,
                }
                recovered["futures"] += 1

            trade_history = repo.get_trade_history(limit=None)
            recovered_position_order_ids = {
                position.get("order_id")
                for position in (*self.simulator.spot_positions.values(), *self.simulator.futures_positions.values())
                if position.get("order_id")
            }
            completed_order_ids = {trade.order_id for trade in trade_history if trade.order_id}

            for order in repo.get_open_orders():
                signal = repo.get_signal(order.signal_id) if order.signal_id else None
                status = order.status
                if status == "FILLING":
                    if order.order_id in recovered_position_order_ids or order.order_id in completed_order_ids:
                        status = "FILLED"
                    else:
                        status = "RECOVERY_REVIEW"
                    repo.save_order({
                        "order_id": order.order_id,
                        "signal_id": order.signal_id,
                        "symbol": order.symbol,
                        "market": order.market,
                        "order_type": order.order_type,
                        "side": order.side,
                        "amount": order.amount,
                        "price": order.price,
                        "stop_loss": order.stop_loss,
                        "take_profit": order.take_profit,
                        "status": status,
                        "filled_amount": order.filled_amount,
                        "avg_fill_price": order.avg_fill_price,
                        "fee": order.fee,
                        "leverage": order.leverage,
                        "created_at": order.created_at,
                    })
                if status == "FILLED":
                    continue
                self.simulator.open_orders[order.order_id] = {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "market": order.market,
                    "side": order.side,
                    "entry_price": order.price,
                    "amount": order.amount,
                    "stop_loss": order.stop_loss,
                    "take_profit": order.take_profit,
                    "leverage": order.leverage,
                    "order_type": order.order_type,
                    "status": status,
                    "created_at": order.created_at,
                    "signal_id": order.signal_id,
                    "filled_amount": order.filled_amount,
                    "avg_fill_price": order.avg_fill_price,
                    "fee": order.fee,
                    "strategy": signal.strategy if signal else "UNKNOWN",
                    "quantity_override": order.amount,
                }
                recovered["orders"] += 1

            # Recover balances and completed trade history
            self._recover_balances(trade_history)

            logger.info(
                "Recovered paper state: spot=%d, futures=%d, orders=%d",
                recovered["spot"], recovered["futures"], recovered["orders"],
            )
            return recovered

    def _recover_balances(self, trades: list | None = None) -> None:
        """Rebuild balances, daily P&L, and completed-trade cache from durable records."""
        from database.repositories import Repository
        repo = Repository(self.db.session_maker())
        if trades is None:
            trades = repo.get_trade_history(limit=None)

        # Preserve runtime-configured starting equity loaded by the orchestrator.
        self.simulator.spot_balance = self.simulator.initial_spot_balance
        self.simulator.futures_balance = self.simulator.initial_futures_balance
        today = datetime.now(timezone.utc).date()
        self.simulator.daily_pnl_date = today
        self.simulator.daily_pnl = 0.0
        self.simulator.closed_trades = []

        for trade in trades:
            if trade.market == "SPOT":
                self.simulator.spot_balance += trade.pnl
            else:
                self.simulator.futures_balance += trade.pnl
            self.simulator.closed_trades.append({
                "position_id": trade.position_id,
                "symbol": trade.symbol,
                "market": trade.market,
                "side": trade.side,
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "amount": trade.amount,
                "leverage": trade.leverage,
                "pnl": trade.pnl,
                "pnl_pct": trade.pnl_pct,
                "fee": trade.fee,
                "strategy": trade.strategy,
                "signal_id": trade.signal_id,
                "order_id": trade.order_id,
                "opened_at": trade.opened_at,
                "closed_at": trade.closed_at,
                "close_reason": trade.close_reason,
            })
            closed_at = trade.closed_at
            if closed_at:
                if closed_at.tzinfo is None:
                    closed_at = closed_at.replace(tzinfo=timezone.utc)
                if closed_at.astimezone(timezone.utc).date() == today:
                    self.simulator.daily_pnl += trade.pnl

        for position in self.simulator.spot_positions.values():
            reserved = float(
                position.get("reserved_notional")
                or (position.get("entry_price", 0.0) * position.get("amount", 0.0))
            )
            self.simulator.spot_balance -= reserved + position.get("fees_paid", 0.0)
        for position in self.simulator.futures_positions.values():
            reserved_margin = float(position.get(
                "reserved_margin",
                position.get("entry_price", 0.0) * position.get("amount", 0.0) / max(float(position.get("leverage", 1.0)), 1.0),
            ))
            self.simulator.futures_balance -= reserved_margin + float(position.get("fees_paid", 0.0))

        # Reconstruct today's mark-to-market P&L from durable trade records.
        # Closed trades above contribute realized net P&L. Today's still-open
        # positions contribute unrealized P&L less their entry fees.
        for position in (
            list(self.simulator.spot_positions.values())
            + list(self.simulator.futures_positions.values())
        ):
            opened_at = position.get("opened_at")
            if isinstance(opened_at, str):
                try:
                    opened_at = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
                except ValueError:
                    opened_at = None
            if isinstance(opened_at, datetime):
                if opened_at.tzinfo is None:
                    opened_at = opened_at.replace(tzinfo=timezone.utc)
                if opened_at.astimezone(timezone.utc).date() == today:
                    self.simulator.daily_pnl += (
                        float(position.get("unrealized_pnl", 0.0))
                        - float(position.get("fees_paid", 0.0))
                    )

        # Preserve the persisted same-day baseline when available. On a first
        # recovery without a saved baseline, reconstruct it from current equity
        # minus the recovered daily P&L; setting it to current equity would
        # erase losses and incorrectly report zero daily drawdown.
        if not self.simulator.daily_equity_state_loaded:
            current_equity = self.simulator.get_account_equity_breakdown()["total_equity"]
            self.simulator.daily_start_equity = current_equity - self.simulator.daily_pnl
            if self.simulator.daily_start_equity <= 0:
                raise RuntimeError("Recovered daily equity baseline is non-positive.")
            self.simulator.daily_equity_state_loaded = True
            self.simulator._persist_daily_equity_baseline()


class ModelCheckpointRecovery:
    """Recovers ML model checkpoints after restart."""

    def __init__(self, models_dir: Path = Path("models")):
        self.models_dir = models_dir
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def list_checkpoints(self) -> list[dict]:
        """List available model checkpoints."""
        checkpoints = []
        for model_file in self.models_dir.glob("*.joblib"):
            stat = model_file.stat()
            checkpoints.append({
                "name": model_file.stem,
                "path": model_file,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            })
        return sorted(checkpoints, key=lambda c: c["modified"], reverse=True)

    def get_latest_checkpoint(self, model_type: str) -> Optional[Path]:
        """Get latest checkpoint for a model type."""
        checkpoints = self.list_checkpoints()
        for cp in checkpoints:
            if model_type.lower() in cp["name"].lower():
                return cp["path"]
        return None

    def verify_checkpoint(self, checkpoint_path: Path) -> bool:
        """Verify checkpoint can be loaded."""
        try:
            import joblib
            model = joblib.load(checkpoint_path)
            return model is not None
        except Exception as e:
            logger.error(f"Checkpoint verification failed: {e}")
            return False

    def load_checkpoint(self, checkpoint_path: Path):
        """Load model from checkpoint."""
        import joblib
        return joblib.load(checkpoint_path)


class WebSocketReconnectionManager:
    """Manages WebSocket reconnection with exponential backoff."""

    def __init__(
        self,
        ws_manager,
        max_retries: int = 10,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: float = 0.1,
        spot_streams: tuple[str, ...] = (),
        futures_streams: tuple[str, ...] = (),
        reconnect_callback: Optional[Callable] = None,
    ):
        self.ws_manager = ws_manager
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.spot_streams = spot_streams
        self.futures_streams = futures_streams
        self.reconnect_callback = reconnect_callback
        self._retry_count = 0
        self._running = False
        self._lock = threading.RLock()

    async def start(self) -> None:
        """Start the reconnection manager."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._retry_count = 0

    async def stop(self) -> None:
        """Stop the reconnection manager."""
        with self._lock:
            self._running = False

    async def handle_disconnect(self) -> bool:
        """Handle WebSocket disconnect with exponential backoff."""
        with self._lock:
            if not self._running:
                return False

            if self._retry_count >= self.max_retries:
                logger.error("Max WebSocket reconnection retries reached")
                return False

            # Calculate delay with exponential backoff and jitter
            delay = min(self.base_delay * (2 ** self._retry_count), self.max_delay)
            import random
            delay *= (1 + random.uniform(-self.jitter, self.jitter))

            self._retry_count += 1
            logger.warning(f"WebSocket disconnected. Reconnecting in {delay:.1f}s (attempt {self._retry_count}/{self.max_retries})")

        # Wait outside lock
        await asyncio.sleep(delay)
        with self._lock:
            if not self._running:
                return False

        # Attempt reconnection
        try:
            if self.reconnect_callback:
                await self.reconnect_callback()
            else:
                await self.ws_manager.start(list(self.spot_streams), list(self.futures_streams))
            await asyncio.sleep(0)
            with self._lock:
                self._retry_count = 0  # Reset on success
            logger.info("WebSocket reconnected successfully")
            return True
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            return await self.handle_disconnect()  # Retry


class RESTResynchronizationManager:
    """Handles REST API resynchronization after disconnect."""

    def __init__(
        self,
        spot_client,
        futures_client,
        symbol_registry,
        candle_manager,
        max_symbols_per_sync: int = 100,
    ):
        self.spot_client = spot_client
        self.futures_client = futures_client
        self.symbol_registry = symbol_registry
        self.candle_manager = candle_manager
        self.max_symbols_per_sync = max_symbols_per_sync

    async def resync_all(self) -> dict[str, int]:
        """Perform full resynchronization."""
        results = {"symbols": 0, "candles": 0, "tickers": 0}

        # 1. Resync symbol registry
        from exchange.market_discovery import MarketDiscovery
        from exchange.rate_limiter import RateLimiter

        rate_limiter = RateLimiter()
        discovery = MarketDiscovery(self.symbol_registry, rate_limiter, True, True)
        await discovery.discover_all()
        results["symbols"] = len(self.symbol_registry.list_symbols())

        # 2. Resync tickers
        spot_tickers = await self.spot_client.get_all_tickers()
        futures_tickers = await self.futures_client.get_all_tickers()
        results["tickers"] = len(spot_tickers) + len(futures_tickers)

        # 3. Resync candles for active symbols
        symbols = self.symbol_registry.list_symbols()[:self.max_symbols_per_sync]
        for sym_info in symbols:
            symbol = sym_info["symbol"]
            market = sym_info["market"]
            for tf in ["1m", "5m", "15m", "1h", "4h", "1d"]:
                try:
                    client = self.spot_client if market == "SPOT" else self.futures_client
                    klines = await client.get_klines(symbol, tf, limit=200)
                    for k in klines:
                        self.candle_manager.add_candle(
                            market, symbol, tf,
                            int(k[0]), float(k[1]), float(k[2]),
                            float(k[3]), float(k[4]), float(k[5]),
                            int(k[6])
                        )
                    results["candles"] += 1
                except Exception as e:
                    logger.warning(f"Candle resync failed for {symbol} {tf}: {e}")

        return results


class TelegramRetryManager:
    """Manages Telegram notification retries with exponential backoff."""

    def __init__(
        self,
        telegram_client,
        max_retries: int = 5,
        base_delay: float = 5.0,
        max_delay: float = 300.0,
    ):
        self.telegram = telegram_client
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._pending: dict[str, tuple[Callable, int]] = {}
        self._lock = threading.RLock()

    async def send_with_retry(self, method: Callable, *args, **kwargs) -> bool:
        """Send notification with automatic retry."""
        for attempt in range(self.max_retries):
            try:
                result = await method(*args, **kwargs)
                if result:
                    return True
            except Exception as e:
                logger.warning(f"Telegram send attempt {attempt + 1} failed: {e}")

            if attempt < self.max_retries - 1:
                delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                await asyncio.sleep(delay)

        logger.error(f"Telegram send failed after {self.max_retries} attempts")
        return False

    def queue_notification(self, notification_id: str, method: Callable, *args, **kwargs) -> None:
        """Queue notification for later retry."""
        with self._lock:
            self._pending[notification_id] = (method, args, kwargs, 0)

    async def process_queue(self) -> None:
        """Process queued notifications."""
        while True:
            with self._lock:
                if not self._pending:
                    break
                notification_id, (method, args, kwargs, attempts) = self._pending.popitem()

            if attempts >= self.max_retries:
                logger.error(f"Notification {notification_id} failed permanently")
                continue

            try:
                result = await method(*args, **kwargs)
                if result:
                    continue  # Success
            except Exception as e:
                logger.warning(f"Queued notification {notification_id} attempt {attempts + 1} failed: {e}")

            # Re-queue with incremented attempts
            with self._lock:
                self._pending[notification_id] = (method, args, kwargs, attempts + 1)

            await asyncio.sleep(min(self.base_delay * (2 ** attempts), 60.0))


class WatchdogMonitor:
    """Watchdog for detecting and recovering from system stalls."""

    def __init__(
        self,
        check_interval: float = 30.0,
        stall_timeout: float = 120.0,
        on_stall: Optional[Callable] = None,
    ):
        self.check_interval = check_interval
        self.stall_timeout = stall_timeout
        self.on_stall = on_stall
        self._last_heartbeat = time.monotonic()
        self._stall_reported = False
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

    def heartbeat(self) -> None:
        """Record a heartbeat."""
        self._last_heartbeat = time.monotonic()
        self._stall_reported = False

    async def start(self) -> None:
        """Start the watchdog monitor."""
        if self._monitor_task and not self._monitor_task.done():
            return
        self._running = True
        self._last_heartbeat = time.monotonic()
        self._stall_reported = False
        # Give a small delay before first check to allow initial heartbeats
        await asyncio.sleep(0.001)
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stop the watchdog monitor."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            await asyncio.sleep(self.check_interval)

            elapsed = time.monotonic() - self._last_heartbeat
            scheduling_grace = max(self.check_interval, 0.05)
            if elapsed > self.stall_timeout + scheduling_grace and not self._stall_reported:
                self._stall_reported = True
                logger.critical(f"Watchdog detected stall: {elapsed:.1f}s since last heartbeat")
                if self.on_stall:
                    try:
                        result = self.on_stall()
                        if inspect.isawaitable(result):
                            await result
                    except Exception as e:
                        logger.error(f"Watchdog stall handler failed: {e}")


class GracefulShutdownManager:
    """Coordinates graceful shutdown of all components."""

    def __init__(self):
        self._shutdown_handlers: list[tuple[int, Callable]] = []
        self._shutdown_event = asyncio.Event()
        self._shutdown_started = False

    def register_handler(self, handler: Callable, priority: int = 0) -> None:
        """Register a shutdown handler with priority (higher runs first)."""
        self._shutdown_handlers.append((priority, handler))
        self._shutdown_handlers.sort(key=lambda x: -x[0])

    async def shutdown(self, signal_name: str = "unknown") -> None:
        """Execute graceful shutdown."""
        if self._shutdown_started:
            return
        self._shutdown_started = True

        logger.info(f"Graceful shutdown initiated by {signal_name}")

        for priority, handler in self._shutdown_handlers:
            try:
                handler_name = getattr(handler, "__name__", type(handler).__name__)
                logger.info("Running shutdown handler: %s (priority=%s)", handler_name, priority)
                result = handler()
                if inspect.isawaitable(result):
                    await result
            except Exception as e:
                logger.exception("Shutdown handler %s failed: %s", handler_name, e)

        self._shutdown_event.set()
        logger.info("Graceful shutdown complete")

    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown to complete."""
        await self._shutdown_event.wait()


class DisasterRecoveryOrchestrator:
    """Main orchestrator for disaster recovery and long-run stability."""

    def __init__(
        self,
        db: Database,
        simulator,
        ws_manager,
        spot_client,
        futures_client,
        symbol_registry,
        candle_manager,
        telegram_client,
        persist_state: Optional[Callable] = None,
        reconnect_callback: Optional[Callable] = None,
    ):
        self.db = db

        # Components
        self.backup_manager = DatabaseBackupManager(BackupConfig(), db)
        self.event_processor = IdempotentEventProcessor(db)
        self.position_recovery = PositionRecoveryManager(db, simulator)
        self.model_recovery = ModelCheckpointRecovery()
        self.ws_reconnection = WebSocketReconnectionManager(
            ws_manager,
            reconnect_callback=reconnect_callback,
        )
        self.rest_resync = RESTResynchronizationManager(
            spot_client, futures_client, symbol_registry, candle_manager
        )
        self.telegram_retry = TelegramRetryManager(telegram_client) if telegram_client else None

        # Watchdog
        self.watchdog = WatchdogMonitor(
            check_interval=30.0,
            stall_timeout=120.0,
            on_stall=self._on_stall
        )

        # Graceful shutdown
        self.shutdown_manager = GracefulShutdownManager()
        self._auto_backup_task: Optional[asyncio.Task] = None
        self._telegram_retry_task: Optional[asyncio.Task] = None
        self._running = False
        self._persist_state = persist_state
        self._register_shutdown_handlers()

    def _register_shutdown_handlers(self) -> None:
        """Register all shutdown handlers in priority order."""
        # Priority 100: Stop accepting new work
        self.shutdown_manager.register_handler(
            lambda: setattr(self, '_running', False),
            priority=100
        )

        # Priority 90: Stop watchdog
        self.shutdown_manager.register_handler(
            self.watchdog.stop,
            priority=90
        )

        # Priority 80: Stop WebSocket
        self.shutdown_manager.register_handler(
            self.ws_reconnection.stop,
            priority=80
        )

        # Priority 70: Flush Telegram queue
        if self.telegram_retry:
            self.shutdown_manager.register_handler(
                self.telegram_retry.process_queue,
                priority=70
            )

        # Priority 60: Persist final state
        if self._persist_state:
            self.shutdown_manager.register_handler(self._persist_state, priority=60)

        # Priority 50: Create final backup
        self.shutdown_manager.register_handler(
            lambda: self.backup_manager.create_backup("shutdown"),
            priority=50
        )

    async def start(self) -> None:
        """Start all recovery and monitoring components."""
        if self._running:
            return
        if self.shutdown_manager._shutdown_started:
            raise RuntimeError("Disaster recovery cannot restart after shutdown.")

        self.position_recovery.recover_positions()
        self._running = True
        try:
            await self.watchdog.start()
            await self.ws_reconnection.start()
            self._auto_backup_task = asyncio.create_task(self._auto_backup_loop())
            if self.telegram_retry:
                self._telegram_retry_task = asyncio.create_task(self.telegram_retry.process_queue())
        except Exception:
            self._running = False
            await self.watchdog.stop()
            await self.ws_reconnection.stop()
            if self._auto_backup_task:
                self._auto_backup_task.cancel()
                await asyncio.gather(self._auto_backup_task, return_exceptions=True)
                self._auto_backup_task = None
            raise

        logger.info("Disaster recovery orchestrator started")

    async def stop(self) -> None:
        """Stop all components and shutdown gracefully."""
        self._running = False
        if self._auto_backup_task:
            self._auto_backup_task.cancel()
            await asyncio.gather(self._auto_backup_task, return_exceptions=True)
            self._auto_backup_task = None
        if self._telegram_retry_task and not self._telegram_retry_task.done():
            self._telegram_retry_task.cancel()
            await asyncio.gather(self._telegram_retry_task, return_exceptions=True)
        self._telegram_retry_task = None
        await self.shutdown_manager.shutdown("manual")
        await self.shutdown_manager.wait_for_shutdown()

    async def _auto_backup_loop(self) -> None:
        """Periodic automatic backup."""
        while self._running:
            await asyncio.sleep(self.backup_manager.config.backup_interval_hours * 3600)
            if self._running:
                try:
                    self.backup_manager.create_backup("auto")
                except Exception as e:
                    logger.error(f"Auto backup failed: {e}")

    def _on_stall(self) -> None:
        """Called when watchdog detects stall."""
        logger.critical("System stall detected - initiating emergency recovery")
        # Could trigger restart, alert, etc.


def create_disaster_recovery_orchestrator(
    db: Database,
    simulator,
    ws_manager,
    spot_client,
    futures_client,
    symbol_registry,
    candle_manager,
    telegram_client,
    persist_state: Optional[Callable] = None,
    reconnect_callback: Optional[Callable] = None,
) -> DisasterRecoveryOrchestrator:
    """Factory function to create the disaster recovery orchestrator."""
    return DisasterRecoveryOrchestrator(
        db=db,
        simulator=simulator,
        ws_manager=ws_manager,
        spot_client=spot_client,
        futures_client=futures_client,
        symbol_registry=symbol_registry,
        candle_manager=candle_manager,
        telegram_client=telegram_client,
        persist_state=persist_state,
        reconnect_callback=reconnect_callback,
    )