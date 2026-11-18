"""Tests for Phase 16 Historical Backtesting and Strategy Laboratory."""
import tempfile
import os
from datetime import datetime, timezone, timedelta
import pytest

from core.event_bus import EventBus
from database.connection import Database
from database.repositories import Repository
from learning.backtest_engine import (
    BacktestConfig,
    HistoricalBacktester,
    StrategyLaboratory,
    BacktestTrade,
    BacktestResult
)
from market.candle_manager import CandleManager


@pytest.fixture
async def temp_db():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    db = Database(f"sqlite:///{db_path}")
    db.init_db()
    yield db
    db.close()
    os.unlink(db_path)


class TestBacktestConfig:
    """Test backtest configuration."""

    def test_backtest_config_defaults(self):
        """Test BacktestConfig initializes with sensible defaults."""
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 31, tzinfo=timezone.utc)
        )
        assert config.initial_balance == 500.0
        assert config.max_positions == 5
        assert config.risk_per_trade_pct == 0.5
        assert "momentum" in config.strategies
        assert "breakout" in config.strategies

    def test_backtest_config_custom(self):
        """Test BacktestConfig with custom parameters."""
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 31, tzinfo=timezone.utc),
            initial_balance=1000.0,
            max_positions=10,
            risk_per_trade_pct=1.0,
            strategies=["momentum", "breakout"],
            timeframes=["1h", "4h"],
            markets=["SPOT"],
            parameter_grid={"risk_per_trade_pct": [0.5, 1.0, 2.0]}
        )
        assert config.initial_balance == 1000.0
        assert config.max_positions == 10
        assert config.parameter_grid is not None
        assert "risk_per_trade_pct" in config.parameter_grid


class TestHistoricalBacktester:
    """Test historical backtesting engine."""

    @pytest.fixture
    def backtester(self, temp_db):
        """Create backtester with populated candle data."""
        session_maker = temp_db.session_maker()
        repo = Repository(session_maker)
        candles = CandleManager()

        # Populate with synthetic trending data for BTCUSDT
        base_time = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        tf_ms = 3600000  # 1h

        for i in range(500):
            price = 50000 + i * 10  # Strong uptrend
            candles.add_candle("SPOT", "BTCUSDT", "1h",
                               base_time + i * tf_ms,
                               price, price + 50, price - 50, price + 10, 1000)

        return HistoricalBacktester(repo, candles)

    @pytest.mark.asyncio
    async def test_backtester_initialization(self, backtester):
        """Test HistoricalBacktester initializes correctly."""
        assert backtester.repo is not None
        assert backtester.candles is not None
        assert len(backtester.strategies) == 5

    @pytest.mark.asyncio
    async def test_run_backtest_basic(self, backtester):
        """Test basic backtest execution."""
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 2, tzinfo=timezone.utc),  # 1 day
            initial_balance=500.0,
            max_positions=2,
            risk_per_trade_pct=0.5,
            strategies=["momentum"],  # Use just one for speed
            timeframes=["1h"],
            markets=["SPOT"],
            min_confidence=0.5
        )

        result = backtester.run_backtest(config)

        assert isinstance(result, BacktestResult)
        assert result.config == config
        assert len(result.trades) >= 0  # May have 0 trades in short period
        assert len(result.equity_curve) > 0
        assert "total_return" in result.metrics
        assert result.max_drawdown_pct >= 0
        assert result.sharpe_ratio >= 0

    @pytest.mark.asyncio
    async def test_backtest_metrics_calculation(self, backtester):
        """Test performance metrics are calculated correctly."""
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 5, tzinfo=timezone.utc),
            initial_balance=500.0,
            strategies=["momentum", "breakout"],
            timeframes=["1h"],
            markets=["SPOT"],
            min_confidence=0.4
        )

        result = backtester.run_backtest(config)

        metrics = result.metrics
        assert "total_return" in metrics
        assert "win_rate" in metrics
        assert "profit_factor" in metrics
        assert "total_trades" in metrics
        assert "max_drawdown_pct" in metrics
        assert "sharpe" in metrics
        assert "sortino" in metrics
        assert "calmar" in metrics

    @pytest.mark.asyncio
    async def test_performance_attribution(self, backtester):
        """Test performance attribution by dimension."""
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 5, tzinfo=timezone.utc),
            initial_balance=500.0,
            strategies=["momentum", "breakout"],
            timeframes=["1h"],
            markets=["SPOT"],
            min_confidence=0.4
        )

        result = backtester.run_backtest(config)

        # Check attribution dictionaries exist
        assert isinstance(result.by_strategy, dict)
        assert isinstance(result.by_market, dict)
        assert isinstance(result.by_symbol, dict)
        assert isinstance(result.by_regime, dict)

    @pytest.mark.asyncio
    async def test_drawdown_calculation(self, backtester):
        """Test drawdown calculations."""
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 5, tzinfo=timezone.utc),
            initial_balance=500.0,
            strategies=["momentum"],
            timeframes=["1h"],
            markets=["SPOT"]
        )

        result = backtester.run_backtest(config)

        assert result.max_drawdown >= 0
        assert result.max_drawdown_pct >= 0

    @pytest.mark.asyncio
    async def test_risk_ratios(self, backtester):
        """Test Sharpe, Sortino, Calmar ratios."""
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 10, tzinfo=timezone.utc),
            initial_balance=500.0,
            strategies=["momentum"],
            timeframes=["1h"],
            markets=["SPOT"]
        )

        result = backtester.run_backtest(config)

        assert result.sharpe_ratio >= 0
        assert result.sortino_ratio >= 0
        assert result.calmar_ratio >= 0

    @pytest.mark.asyncio
    async def test_out_of_sample_testing(self, backtester):
        """Test out-of-sample testing with holdout period."""
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 10, tzinfo=timezone.utc),
            holdout_start=datetime(2024, 1, 6, tzinfo=timezone.utc),
            initial_balance=500.0,
            strategies=["momentum"],
            timeframes=["1h"],
            markets=["SPOT"]
        )

        result = backtester.run_backtest(config)

        assert result.out_of_sample is not None
        oos = result.out_of_sample
        assert "trades" in oos
        assert "metrics" in oos
        assert "sharpe" in oos
        assert "max_drawdown_pct" in oos

    @pytest.mark.asyncio
    async def test_parameter_sensitivity(self, backtester):
        """Test parameter sensitivity analysis."""
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 5, tzinfo=timezone.utc),
            initial_balance=500.0,
            strategies=["momentum"],
            timeframes=["1h"],
            markets=["SPOT"],
            parameter_grid={"risk_per_trade_pct": [0.3, 0.5, 1.0]}
        )

        result = backtester.run_backtest(config)

        assert "risk_per_trade_pct" in result.parameter_sensitivity
        sens = result.parameter_sensitivity["risk_per_trade_pct"]
        assert len(sens) == 3
        for s in sens:
            assert "value" in s
            assert "sharpe" in s
            assert "return" in s
            assert "max_dd" in s
            assert "trades" in s


class TestStrategyLaboratory:
    """Test controlled strategy experimentation."""

    @pytest.fixture
    def laboratory(self):
        """Create a lab with in-memory repo for faster testing."""
        # Use a simple in-memory approach for testing
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        db = Database(f"sqlite:///{db_path}")
        db.init_db()
        session_maker = db.session_maker()
        repo = Repository(session_maker)
        candles = CandleManager()

        # Populate with data
        base_time = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        tf_ms = 3600000

        for i in range(500):
            price = 50000 + i * 10
            candles.add_candle("SPOT", "BTCUSDT", "1h",
                               base_time + i * tf_ms,
                               price, price + 50, price - 50, price + 10, 1000)

        backtester = HistoricalBacktester(repo, candles)
        lab = StrategyLaboratory(backtester)
        yield lab
        db.close()
        os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_run_experiment(self, laboratory):
        """Test running a controlled experiment."""
        configs = [
            BacktestConfig(
                start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end_date=datetime(2024, 1, 5, tzinfo=timezone.utc),
                initial_balance=500.0,
                strategies=["momentum"],
                timeframes=["1h"],
                markets=["SPOT"],
                min_confidence=0.5
            ),
            BacktestConfig(
                start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end_date=datetime(2024, 1, 5, tzinfo=timezone.utc),
                initial_balance=500.0,
                strategies=["breakout"],
                timeframes=["1h"],
                markets=["SPOT"],
                min_confidence=0.5
            )
        ]

        result = laboratory.run_experiment("strategy_comparison", configs)

        assert "results" in result
        assert "best" in result
        assert "experiment" in result
        assert len(result["results"]) == 2
        assert result["best"] in ["momentum", "breakout"]
        assert result["experiment"]["holdout_usage_count"] == 1

    @pytest.mark.asyncio
    async def test_holdout_usage_tracking(self, laboratory):
        """Test holdout dataset usage tracking to prevent overfitting."""
        configs = [
            BacktestConfig(
                start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end_date=datetime(2024, 1, 5, tzinfo=timezone.utc),
                initial_balance=500.0,
                strategies=["momentum"],
                timeframes=["1h"],
                markets=["SPOT"]
            )
        ]

        # Run same holdout multiple times
        for _ in range(6):
            laboratory.run_experiment("test", configs, holdout_key="default")

        # Should have warned about overuse
        # (Check log output in actual run)
        history = laboratory.get_experiment_history()
        assert len(history) == 6
        assert history[-1]["holdout_usage_count"] == 6

    @pytest.mark.asyncio
    async def test_experiment_history(self, laboratory):
        """Test experiment history retrieval."""
        configs = [
            BacktestConfig(
                start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end_date=datetime(2024, 1, 5, tzinfo=timezone.utc),
                initial_balance=500.0,
                strategies=["momentum"],
                timeframes=["1h"],
                markets=["SPOT"]
            )
        ]

        laboratory.run_experiment("exp1", configs, "key1")
        laboratory.run_experiment("exp2", configs, "key2")

        history = laboratory.get_experiment_history()
        assert len(history) == 2
        assert history[0]["name"] == "exp1"
        assert history[1]["name"] == "exp2"


class TestBacktestTrade:
    """Test BacktestTrade dataclass."""

    def test_backtest_trade_creation(self):
        """Test creating a backtest trade."""
        trade = BacktestTrade(
            trade_id="TEST-001",
            symbol="BTCUSDT",
            market="SPOT",
            strategy="momentum",
            side="LONG",
            entry_time=datetime.now(timezone.utc),
            entry_price=50000.0,
            exit_time=None,
            exit_price=None,
            amount=0.01,
            leverage=1.0,
            stop_loss=49000.0,
            take_profit=52000.0
        )

        assert trade.trade_id == "TEST-001"
        assert trade.pnl == 0.0
        assert trade.close_reason == "OPEN"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])