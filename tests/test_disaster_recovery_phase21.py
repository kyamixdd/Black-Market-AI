"""Tests for Phase 21 Disaster Recovery and Long-Run Stability."""
import json
import asyncio
import gzip
import tempfile
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlite3

from config import BACKUP_DIR, DATABASE_URL
from core.disaster_recovery import (
    BackupConfig,
    DatabaseBackupManager,
    IdempotentEventProcessor,
    PositionRecoveryManager,
    ModelCheckpointRecovery,
    WebSocketReconnectionManager,
    RESTResynchronizationManager,
    TelegramRetryManager,
    WatchdogMonitor,
    GracefulShutdownManager,
    DisasterRecoveryOrchestrator,
)
from database.connection import Database
from database.repositories import Repository
from paper_trading.simulator import Simulator
from core.event_bus import EventBus


class TestBackupConfig:
    """Test backup configuration."""

    def test_backup_config_defaults(self):
        """Test backup config defaults."""
        config = BackupConfig()
        assert config.max_backups == 30
        assert config.backup_interval_hours == 6
        assert config.compress is True
        assert config.verify_after_backup is True
        assert config.backup_dir == BACKUP_DIR


class TestDatabaseBackupManager:
    """Test database backup manager."""

    @pytest.fixture
    def temp_db(self):
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        db = Database(f"sqlite:///{db_path}")
        db.init_db()
        yield db
        db.close()
        os.unlink(db_path)

    @pytest.fixture
    def backup_manager(self, temp_db):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = BackupConfig(backup_dir=Path(tmpdir), max_backups=5, compress=True)
            manager = DatabaseBackupManager(config, temp_db)
            yield manager

    def test_create_backup(self, backup_manager, temp_db):
        """Test creating a backup."""
        # Add some data
        repo = Repository(temp_db.session_maker())
        repo.save_symbols([{
            "symbol": "BTCUSDT", "market": "SPOT",
            "base_asset": "BTC", "quote_asset": "USDT",
            "price_precision": 2, "quantity_precision": 6,
            "tick_size": 0.01, "step_size": 0.0001,
            "min_notional": 10.0, "status": "TRADING", "is_eligible": True,
        }])

        backup_path = backup_manager.create_backup("test")
        assert backup_path.exists()
        assert backup_path.suffix == ".gz"

    def test_backup_verification(self, backup_manager, temp_db):
        """Test backup verification."""
        backup_path = backup_manager.create_backup("verify_test")
        # Verify it can be opened
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            with gzip.open(backup_path, "rb") as f_in:
                with open(tmp_path, "wb") as f_out:
                    import shutil
                    shutil.copyfileobj(f_in, f_out)
            conn = sqlite3.connect(str(tmp_path))
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            assert result[0] == "ok"
        finally:
            conn.close()
            tmp_path.unlink(missing_ok=True)

    def test_prune_old_backups(self, backup_manager, temp_db):
        """Test old backup pruning."""
        # Create more backups than max
        for i in range(10):
            backup_manager.create_backup(f"test_{i}")

        backups = list(backup_manager.config.backup_dir.glob("*.gz"))
        assert len(backups) <= backup_manager.config.max_backups

    def test_restore_backup(self, backup_manager, temp_db):
        """Test restoring from backup."""
        # Add data
        repo = Repository(temp_db.session_maker())
        repo.save_symbols([{
            "symbol": "ETHUSDT", "market": "SPOT",
            "base_asset": "ETH", "quote_asset": "USDT",
            "price_precision": 2, "quantity_precision": 6,
            "tick_size": 0.01, "step_size": 0.0001,
            "min_notional": 10.0, "status": "TRADING", "is_eligible": True,
        }])

        backup_path = backup_manager.create_backup("restore_test")

        # Create new database and restore
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            new_db_path = f.name
        try:
            new_db = Database(f"sqlite:///{new_db_path}")
            new_db.init_db()

            # Restore to the target database configured on the manager.
            target_backup_manager = DatabaseBackupManager(
                BackupConfig(backup_dir=backup_manager.config.backup_dir, compress=True),
                new_db,
            )
            success = target_backup_manager.restore_backup(backup_path)
            assert success

            # Verify data restored
            new_repo = Repository(new_db.session_maker())
            symbols = new_repo.get_eligible_symbols()
            assert len(symbols) == 1
            assert symbols[0].symbol == "ETHUSDT"
        finally:
            new_db.close()
            os.unlink(new_db_path)


class TestIdempotentEventProcessor:
    """Test idempotent event processing."""

    @pytest.fixture
    def temp_db(self):
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        db = Database(f"sqlite:///{db_path}")
        db.init_db()
        yield db
        db.close()
        os.unlink(db_path)

    @pytest.fixture
    def processor(self, temp_db):
        return IdempotentEventProcessor(temp_db)

    def test_first_process_succeeds(self, processor):
        """Test first event processing succeeds."""
        event_id = "test_event_001"
        called = []

        def handler():
            called.append(True)
            return "result"

        was_processed, result = processor.process_event(event_id, handler)
        assert was_processed is False
        assert result == "result"
        assert len(called) == 1

    def test_duplicate_event_skipped(self, processor):
        """Test duplicate event is skipped."""
        event_id = "test_event_002"
        called = []

        def handler():
            called.append(True)
            return "result"

        # First call
        processor.process_event(event_id, handler)
        assert len(called) == 1

        # Second call - should be skipped
        was_processed, result = processor.process_event(event_id, handler)
        assert was_processed is True
        assert result is None
        assert len(called) == 1  # Not called again

    def test_is_processed_check(self, processor):
        """Test is_processed check."""
        event_id = "test_event_003"
        assert processor.is_processed(event_id) is False

        def handler():
            return "result"

        processor.process_event(event_id, handler)
        assert processor.is_processed(event_id) is True


class TestPositionRecoveryManager:
    """Test position recovery after restart."""

    @pytest.fixture
    def temp_db(self):
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        db = Database(f"sqlite:///{db_path}")
        db.init_db()
        yield db
        db.close()
        os.unlink(db_path)

    @pytest.fixture
    def simulator(self):
        bus = EventBus()
        return Simulator(bus)

    @pytest.fixture
    def recovery_manager(self, temp_db, simulator):
        return PositionRecoveryManager(temp_db, simulator)

    def test_recover_positions_empty(self, recovery_manager):
        """Test recovery with no positions."""
        recovered = recovery_manager.recover_positions()
        assert recovered["spot"] == 0
        assert recovered["futures"] == 0

    def test_recover_positions_with_data(self, recovery_manager, temp_db):
        """Test recovery with existing positions."""
        repo = Repository(temp_db.session_maker())

        # Save a spot position
        repo.save_position({
            "position_id": "POS-SPOT-001",
            "symbol": "BTCUSDT",
            "market": "SPOT",
            "side": "LONG",
            "entry_price": 50000.0,
            "amount": 0.001,
            "current_price": 51000.0,
            "stop_loss": 49000.0,
            "take_profit": 52000.0,
            "leverage": 1.0,
            "unrealized_pnl": 100.0,
            "realized_pnl": 0.0,
            "fees_paid": 5.0,
            "status": "OPEN",
            "opened_at": datetime.now(timezone.utc),
        })

        # Save a futures position
        repo.save_position({
            "position_id": "POS-FUT-001",
            "symbol": "ETHUSDT",
            "market": "FUTURES",
            "side": "SHORT",
            "entry_price": 3000.0,
            "amount": 0.01,
            "current_price": 2950.0,
            "stop_loss": 3100.0,
            "take_profit": 2800.0,
            "leverage": 3.0,
            "unrealized_pnl": 50.0,
            "realized_pnl": 0.0,
            "fees_paid": 9.0,
            "status": "OPEN",
            "opened_at": datetime.now(timezone.utc),
        })

        repo.save_order({
            "order_id": "ORD-SPOT-001",
            "symbol": "SOLUSDT",
            "market": "SPOT",
            "side": "BUY",
            "order_type": "LIMIT",
            "amount": 0.01,
            "price": 100.0,
            "leverage": 1.0,
            "status": "OPEN",
            "filled_amount": 0.0,
            "avg_fill_price": 0.0,
            "fee": 0.0,
        })

        recovered = recovery_manager.recover_positions()
        assert recovered["spot"] == 1
        assert recovered["futures"] == 1
        assert recovered["orders"] == 1
        assert "POS-SPOT-001" in recovery_manager.simulator.spot_positions
        assert "POS-FUT-001" in recovery_manager.simulator.futures_positions
        assert "ORD-SPOT-001" in recovery_manager.simulator.open_orders
        from config import SPOT_INITIAL_BALANCE, FUTURES_INITIAL_BALANCE, SPOT_TAKER
        assert recovery_manager.simulator.spot_balance == pytest.approx(SPOT_INITIAL_BALANCE - 55.0)
        assert recovery_manager.simulator.futures_balance == pytest.approx(FUTURES_INITIAL_BALANCE - 39.0)
        expected_available_spot = SPOT_INITIAL_BALANCE - 55.0 - (1.0 * (1.0 + SPOT_TAKER))
        assert recovery_manager.simulator._available_balance("SPOT") == pytest.approx(expected_available_spot)

        # A second recovery must rebuild from the database, not double-subtract
        # reserved capital or duplicate restored positions/orders.
        recovery_manager.recover_positions()
        assert len(recovery_manager.simulator.spot_positions) == 1
        assert len(recovery_manager.simulator.futures_positions) == 1
        assert len(recovery_manager.simulator.open_orders) == 1
        assert recovery_manager.simulator.spot_balance == pytest.approx(SPOT_INITIAL_BALANCE - 55.0)
        assert recovery_manager.simulator.futures_balance == pytest.approx(FUTURES_INITIAL_BALANCE - 39.0)


class TestModelCheckpointRecovery:
    """Test model checkpoint recovery."""

    @pytest.fixture
    def checkpoint_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def recovery(self, checkpoint_dir):
        return ModelCheckpointRecovery(checkpoint_dir)

    def test_list_checkpoints_empty(self, recovery):
        """Test listing checkpoints when empty."""
        checkpoints = recovery.list_checkpoints()
        assert checkpoints == []

    def test_list_checkpoints_with_models(self, recovery, checkpoint_dir):
        """Test listing checkpoints with models."""
        import joblib
        from sklearn.ensemble import RandomForestClassifier
        import numpy as np

        # Create a dummy model
        model = RandomForestClassifier(n_estimators=10, random_state=42)
        model.fit(np.random.randn(100, 10), np.random.randint(0, 3, 100))

        # Save models
        joblib.dump(model, checkpoint_dir / "rf_v1.joblib")
        joblib.dump(model, checkpoint_dir / "xgb_v1.joblib")

        checkpoints = recovery.list_checkpoints()
        assert len(checkpoints) == 2
        assert all(c["size"] > 0 for c in checkpoints)

    def test_verify_checkpoint(self, recovery, checkpoint_dir):
        """Test checkpoint verification."""
        import joblib
        from sklearn.ensemble import RandomForestClassifier
        import numpy as np

        model = RandomForestClassifier(n_estimators=10, random_state=42)
        model.fit(np.random.randn(100, 10), np.random.randint(0, 3, 100))

        cp_path = checkpoint_dir / "test_model.joblib"
        joblib.dump(model, cp_path)

        assert recovery.verify_checkpoint(cp_path) is True

        # Corrupt file
        cp_path.write_bytes(b"corrupted")
        assert recovery.verify_checkpoint(cp_path) is False


class TestWebSocketReconnectionManager:
    """Test WebSocket reconnection manager."""

    @pytest.fixture
    def ws_manager_mock(self):
        return MagicMock()

    @pytest.fixture
    def reconnection_manager(self, ws_manager_mock):
        return WebSocketReconnectionManager(
            ws_manager_mock,
            max_retries=3,
            base_delay=0.01,  # Fast for testing
            max_delay=0.1,
            jitter=0.0,
        )

    @pytest.mark.asyncio
    async def test_start_stop(self, reconnection_manager):
        """Test start and stop."""
        await reconnection_manager.start()
        assert reconnection_manager._running is True

        await reconnection_manager.stop()
        assert reconnection_manager._running is False

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self, reconnection_manager):
        """Test max retries behavior."""
        ws_manager_mock = MagicMock()
        ws_manager_mock.start = AsyncMock(side_effect=Exception("Connection failed"))

        reconnection_manager = WebSocketReconnectionManager(
            ws_manager_mock,
            max_retries=2,
            base_delay=0.01,
            max_delay=0.1,
            jitter=0.0,
        )
        await reconnection_manager.start()

        result = await reconnection_manager.handle_disconnect()
        assert result is False
        assert reconnection_manager._retry_count == 2

    @pytest.mark.asyncio
    async def test_reconnect_uses_managed_restart_callback(self):
        from exchange.websocket_manager import WebSocketManager
        from exchange.rate_limiter import RateLimiter

        manager = WebSocketManager(RateLimiter())
        manager._run_stream = AsyncMock()
        await manager.start(["btcusdt@ticker"], [])
        reconnection = WebSocketReconnectionManager(
            manager,
            base_delay=0.001,
            max_delay=0.001,
            jitter=0,
            reconnect_callback=manager.restart,
        )
        await reconnection.start()

        assert await reconnection.handle_disconnect() is True
        assert manager._run_stream.await_count == 2
        await reconnection.stop()
        await manager.stop()


class TestGracefulShutdownManager:
    """Test graceful shutdown manager."""

    def test_register_handler(self):
        """Test handler registration with priority."""
        manager = GracefulShutdownManager()
        handlers = []

        def h1(): handlers.append(1)
        def h2(): handlers.append(2)
        def h3(): handlers.append(3)

        manager.register_handler(h1, priority=10)
        manager.register_handler(h2, priority=30)
        manager.register_handler(h3, priority=20)

        asyncio.run(manager.shutdown("test"))
        # Should run in priority order: 30, 20, 10 -> h2, h3, h1
        assert handlers == [2, 3, 1]

    @pytest.mark.asyncio
    async def test_shutdown_error_handling(self):
        """Test shutdown continues despite handler errors."""
        manager = GracefulShutdownManager()

        def bad_handler():
            raise ValueError("Handler failed")

        def good_handler():
            pass

        manager.register_handler(bad_handler, priority=10)
        manager.register_handler(good_handler, priority=20)

        # Should not raise
        await manager.shutdown("test")
        await manager.wait_for_shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_awaits_awaitable_returned_by_sync_handler(self):
        manager = GracefulShutdownManager()
        calls = []

        async def finish_shutdown():
            calls.append("finished")

        manager.register_handler(lambda: finish_shutdown())

        await manager.shutdown("test")

        assert calls == ["finished"]


class TestWatchdogMonitor:
    """Test watchdog monitor."""

    @pytest.mark.asyncio
    async def test_heartbeat_stall_detection(self):
        """Test stall detection."""
        detected = []

        def on_stall():
            detected.append(True)

        watchdog = WatchdogMonitor(
            check_interval=0.01,
            stall_timeout=0.02,
            on_stall=on_stall,
        )

        await watchdog.start()

        # Wait for stall detection
        await asyncio.sleep(0.1)

        await watchdog.stop()

        assert len(detected) >= 1

    @pytest.mark.asyncio
    async def test_heartbeat_prevents_stall(self):
        """Test heartbeat prevents stall detection."""
        detected = []

        def on_stall():
            detected.append(True)

        watchdog = WatchdogMonitor(
            check_interval=0.01,
            stall_timeout=0.02,
            on_stall=on_stall,
        )

        await watchdog.start()

        # Send heartbeats regularly
        for _ in range(10):
            watchdog.heartbeat()
            await asyncio.sleep(0.015)

        await watchdog.stop()

        assert len(detected) == 0


class TestDisasterRecoveryOrchestrator:
    """Test disaster recovery orchestrator."""

    @pytest.fixture
    def temp_db(self):
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        db = Database(f"sqlite:///{db_path}")
        db.init_db()
        yield db
        db.close()
        os.unlink(db_path)

    @pytest.fixture
    def components(self, temp_db):
        """Create all required components."""
        bus = EventBus()
        simulator = Simulator(bus)
        ws_manager = MagicMock()
        spot_client = MagicMock()
        futures_client = MagicMock()
        from exchange.symbol_registry import SymbolRegistry
        symbol_registry = SymbolRegistry()
        from market.candle_manager import CandleManager
        candle_manager = CandleManager()
        telegram_client = MagicMock()

        return {
            "db": temp_db,
            "simulator": simulator,
            "ws_manager": ws_manager,
            "spot_client": spot_client,
            "futures_client": futures_client,
            "symbol_registry": symbol_registry,
            "candle_manager": candle_manager,
            "telegram_client": telegram_client,
        }

    @pytest.mark.asyncio
    async def test_orchestrator_start_stop(self, components):
        """Test orchestrator start and stop."""
        from core.disaster_recovery import create_disaster_recovery_orchestrator

        orchestrator = create_disaster_recovery_orchestrator(**components)

        await orchestrator.start()
        assert orchestrator._running is True

        await orchestrator.stop()
        assert orchestrator._running is False

    @pytest.mark.asyncio
    async def test_position_recovery_integration(self, components, temp_db):
        """Test position recovery through orchestrator."""
        from core.disaster_recovery import create_disaster_recovery_orchestrator

        # Add test position to database
        repo = Repository(temp_db.session_maker())
        repo.save_position({
            "position_id": "POS-ORCH-001",
            "symbol": "BTCUSDT",
            "market": "SPOT",
            "side": "LONG",
            "entry_price": 50000.0,
            "amount": 0.1,
            "current_price": 51000.0,
            "stop_loss": 49000.0,
            "take_profit": 52000.0,
            "leverage": 1.0,
            "unrealized_pnl": 100.0,
            "realized_pnl": 0.0,
            "fees_paid": 5.0,
            "status": "OPEN",
            "opened_at": datetime.now(timezone.utc),
        })

        orchestrator = create_disaster_recovery_orchestrator(**components)
        await orchestrator.start()

        # Verify position recovered
        assert "POS-ORCH-001" in orchestrator.position_recovery.simulator.spot_positions

        await orchestrator.stop()


class TestTelegramRetryManager:
    """Test Telegram retry manager."""

    @pytest.fixture
    def telegram_mock(self):
        return MagicMock()

    @pytest.fixture
    def retry_manager(self, telegram_mock):
        return TelegramRetryManager(
            telegram_mock,
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
        )

    @pytest.mark.asyncio
    async def test_send_with_retry_success(self, retry_manager, telegram_mock):
        """Test successful send on first try."""
        telegram_mock.send_message = AsyncMock(return_value=True)

        result = await retry_manager.send_with_retry(telegram_mock.send_message, "Test")
        assert result is True
        telegram_mock.send_message.assert_called_once_with("Test")

    @pytest.mark.asyncio
    async def test_send_with_retry_eventual_success(self, retry_manager, telegram_mock):
        """Test eventual success after failures."""
        telegram_mock.send_message = AsyncMock(side_effect=[Exception("fail"), True])

        result = await retry_manager.send_with_retry(telegram_mock.send_message, "Test")
        assert result is True
        assert telegram_mock.send_message.call_count == 2

    @pytest.mark.asyncio
    async def test_send_with_retry_all_fail(self, retry_manager, telegram_mock):
        """Test all retries fail."""
        telegram_mock.send_message = AsyncMock(side_effect=Exception("permanent fail"))

        result = await retry_manager.send_with_retry(telegram_mock.send_message, "Test")
        assert result is False
        assert telegram_mock.send_message.call_count == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

class TestPersistentEventQueue:
    @pytest.fixture
    def temp_db(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as handle:
            db_path = handle.name
        db = Database(f"sqlite:///{db_path}")
        db.init_db()
        yield db
        db.close()
        os.unlink(db_path)

    def test_enqueue_dequeue_and_complete(self, temp_db):
        from core.disaster_recovery import PersistentEventQueue

        queue = PersistentEventQueue(temp_db, "test_critical")
        event_id = queue.enqueue("POSITION_CLOSED", {"position_id": "p-1"}, priority=5)

        items = queue.dequeue(limit=10)
        assert len(items) == 1
        assert items[0]["event_id"] == event_id
        assert items[0]["event_type"] == "POSITION_CLOSED"
        assert items[0]["payload"] == {"position_id": "p-1"}
        assert items[0]["priority"] == 5
        assert items[0]["attempts"] == 1

        # A claimed item is invisible until its lease expires or it is completed.
        assert queue.dequeue(limit=10) == []
        queue.mark_completed(event_id)
        queue.mark_completed(event_id)
        assert queue.dequeue(limit=10) == []

    def test_claimed_item_can_be_retried_after_visibility_timeout(self, temp_db):
        from core.disaster_recovery import PersistentEventQueue

        queue = PersistentEventQueue(temp_db, "test_retry")
        event_id = queue.enqueue("NOTIFY", {"message": "retry me"})
        first = queue.dequeue(limit=1)
        assert first[0]["attempts"] == 1

        # Force the claim timestamp into the past to test lease recovery.
        from database.models import SystemEventModel
        with temp_db.session_maker() as session:
            row = session.get(SystemEventModel, event_id)
            payload = json.loads(row.payload)
            payload["claimed_at"] = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
            row.payload = json.dumps(payload)
            session.commit()

        retried = queue.dequeue(limit=1, visibility_timeout_seconds=1)
        assert len(retried) == 1
        assert retried[0]["event_id"] == event_id
        assert retried[0]["attempts"] == 2

    def test_dequeue_rejects_non_positive_limit(self, temp_db):
        from core.disaster_recovery import PersistentEventQueue

        queue = PersistentEventQueue(temp_db, "test_empty")
        queue.enqueue("NOOP", {})
        assert queue.dequeue(limit=0) == []

    def test_dequeue_claims_highest_priority_first(self, temp_db):
        from core.disaster_recovery import PersistentEventQueue

        queue = PersistentEventQueue(temp_db, "test_priority")
        low_id = queue.enqueue("LOW", {"level": "low"}, priority=1)
        high_id = queue.enqueue("HIGH", {"level": "high"}, priority=10)

        first = queue.dequeue(limit=1)
        assert len(first) == 1
        assert first[0]["event_id"] == high_id
        assert first[0]["event_id"] != low_id

    def test_queue_delivery_and_idempotency_ledger_work_end_to_end(self, temp_db):
        from core.disaster_recovery import IdempotentEventProcessor, PersistentEventQueue

        queue = PersistentEventQueue(temp_db, "test_end_to_end")
        processor = IdempotentEventProcessor(temp_db)
        event_id = queue.enqueue("POSITION_CLOSED", {"position_id": "position-42"}, priority=9)
        item = queue.dequeue(limit=1)[0]
        calls = []

        was_processed, result = processor.process_event(
            item["event_id"], lambda: calls.append(item["payload"]["position_id"]) or "ok"
        )
        assert was_processed is False
        assert result == "ok"
        queue.mark_completed(event_id)

        restarted_processor = IdempotentEventProcessor(temp_db)
        duplicate, duplicate_result = restarted_processor.process_event(
            event_id, lambda: calls.append("duplicate")
        )
        assert duplicate is True
        assert duplicate_result is None
        assert calls == ["position-42"]
        assert queue.dequeue(limit=1) == []

    @pytest.mark.asyncio
    async def test_telegram_retry_queue_survives_in_database_and_retries(tmp_path):
        from database.connection import Database

        db = Database(f"sqlite:///{tmp_path / 'telegram-retries.db'}")
        db.init_db()

        class FakeTelegram:
            def __init__(self):
                self.calls = 0

            async def send_message(self, message):
                self.calls += 1
                return self.calls >= 2

        telegram = FakeTelegram()
        retry = TelegramRetryManager(
            telegram, max_retries=3, base_delay=0.001, max_delay=0.01, db=db
        )
        retry.queue_notification("notification-1", telegram.send_message, "queued hello")

        # Recreate the retry manager to simulate a process restart. The new
        # manager must recover the queued notification from the database.
        restarted_retry = TelegramRetryManager(
            telegram, max_retries=3, base_delay=0.001, max_delay=0.01, db=db
        )
        await restarted_retry.process_queue()

        assert telegram.calls == 2
        assert restarted_retry._persistent_queue.dequeue(limit=10) == []
        db.close()

    @pytest.mark.asyncio
    async def test_telegram_retry_worker_wakes_for_new_notifications(tmp_path):
        from database.connection import Database

        db = Database(f"sqlite:///{tmp_path / 'telegram-worker.db'}")
        db.init_db()
        delivered = asyncio.Event()

        class FakeTelegram:
            async def send_message(self, _message):
                delivered.set()
                return True

        telegram = FakeTelegram()
        retry = TelegramRetryManager(telegram, base_delay=0.001, db=db)
        worker = asyncio.create_task(retry.run_worker())
        retry.queue_notification("notification-2", telegram.send_message, "wake worker")
        await asyncio.wait_for(delivered.wait(), timeout=2)
        retry.stop_worker()
        await asyncio.wait_for(worker, timeout=2)
        db.close()


    def test_model_checkpoint_recovery_loads_complete_versioned_hybrid_bundle(self, tmp_path, monkeypatch):
        import joblib
        import xgboost as xgb
        from core.disaster_recovery import ModelCheckpointRecovery

        class FakeXGB:
            def load_model(self, path):
                self.path = path

        monkeypatch.setattr(xgb, "XGBClassifier", FakeXGB)
        version = "active-20261119"
        joblib.dump({"model": "rf"}, tmp_path / f"rf_{version}.pkl")
        (tmp_path / f"xgb_{version}.json").write_text("{}", encoding="utf-8")
        joblib.dump({"model": "scaler"}, tmp_path / f"scaler_{version}.pkl")
        joblib.dump({"model": "river"}, tmp_path / f"river_{version}.pkl")
        (tmp_path / "latest_version.txt").write_text(version, encoding="utf-8")

        recovery = ModelCheckpointRecovery(tmp_path)
        bundle = recovery.recover_latest_active_bundle()

        assert bundle is not None
        assert bundle["version"] == version
        assert bundle["random_forest"] == {"model": "rf"}
        assert bundle["scaler"] == {"model": "scaler"}
        assert bundle["river"] == {"model": "river"}
        assert isinstance(bundle["xgboost"], FakeXGB)
        assert len(recovery.list_checkpoints()) == 4
        assert recovery.verify_checkpoint(tmp_path / f"xgb_{version}.json")
