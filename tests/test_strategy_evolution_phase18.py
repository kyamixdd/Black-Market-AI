"""Tests for Phase 18 Controlled Self-Evolving Strategy Engine."""
import tempfile
import os
from datetime import datetime, timezone
import pytest
from unittest.mock import patch, MagicMock

from core.event_bus import EventBus
from database.connection import Database
from database.repositories import Repository
from learning.strategy_evolution import (
    SAFETY_BOUNDARIES,
    EVOLUTION_SPACE,
    ExperimentConfig,
    ExperimentResult,
    ExperimentStatus,
    ExperimentType,
    StrategyEvolutionEngine,
    ExperimentRegistry,
)
from learning.backtest_engine import BacktestConfig, HistoricalBacktester, BacktestResult
from market.candle_manager import CandleManager


class TestSafetyBoundaries:
    """Test safety boundary constants."""

    def test_safety_boundaries_exist(self):
        """Test safety boundaries are defined."""
        assert "max_spot_positions" in SAFETY_BOUNDARIES
        assert "max_futures_positions" in SAFETY_BOUNDARIES
        assert "risk_per_trade_pct" in SAFETY_BOUNDARIES
        assert "max_daily_loss_pct" in SAFETY_BOUNDARIES
        assert "max_total_open_pct" in SAFETY_BOUNDARIES
        assert "max_leverage" in SAFETY_BOUNDARIES

    def test_safety_boundaries_values(self):
        """Test safety boundaries have correct values."""
        assert SAFETY_BOUNDARIES["max_spot_positions"] == 5
        assert SAFETY_BOUNDARIES["max_futures_positions"] == 5
        assert SAFETY_BOUNDARIES["risk_per_trade_pct"] == 0.5
        assert SAFETY_BOUNDARIES["max_daily_loss_pct"] == 2.0
        assert SAFETY_BOUNDARIES["max_total_open_pct"] == 3.0
        assert SAFETY_BOUNDARIES["max_leverage"] == 3.0


class TestEvolutionSpace:
    """Test evolution space definition."""

    def test_evolution_space_structure(self):
        """Test evolution space has expected parameters."""
        assert "rsi_period" in EVOLUTION_SPACE
        assert "rsi_overbought" in EVOLUTION_SPACE
        assert "rsi_oversold" in EVOLUTION_SPACE
        assert "macd_fast" in EVOLUTION_SPACE
        assert "bb_period" in EVOLUTION_SPACE
        assert "timeframe_weights" in EVOLUTION_SPACE
        assert "strategy_weights" in EVOLUTION_SPACE
        assert "confidence_threshold" in EVOLUTION_SPACE
        assert "min_risk_reward" in EVOLUTION_SPACE

    def test_evolution_space_ranges(self):
        """Test evolution space ranges are reasonable."""
        assert EVOLUTION_SPACE["rsi_period"]["min"] == 7
        assert EVOLUTION_SPACE["rsi_period"]["max"] == 21
        assert EVOLUTION_SPACE["confidence_threshold"]["min"] == 0.5
        assert EVOLUTION_SPACE["confidence_threshold"]["max"] == 0.85


class TestExperimentConfig:
    """Test experiment configuration."""

    def test_experiment_config_creation(self):
        """Test creating experiment config."""
        config = ExperimentConfig(
            experiment_id="exp_test_001",
            experiment_type=ExperimentType.PARAMETER_TUNING,
            name="RSI Period Test",
            description="Test different RSI periods",
            base_config_hash="abc123",
            parameter_changes={"rsi_period": 10},
        )

        assert config.experiment_id == "exp_test_001"
        assert config.experiment_type == ExperimentType.PARAMETER_TUNING
        assert config.status == ExperimentStatus.GENERATED
        assert config.version == 1

    def test_experiment_config_with_parent(self):
        """Test experiment with parent lineage."""
        config = ExperimentConfig(
            experiment_id="exp_test_002",
            experiment_type=ExperimentType.INDICATOR_THRESHOLD,
            name="Child Experiment",
            description="Based on parent",
            base_config_hash="def456",
            parameter_changes={"rsi_overbought": 75},
            parent_experiment_id="exp_test_001",
        )

        assert config.parent_experiment_id == "exp_test_001"


class TestStrategyEvolutionEngine:
    """Test strategy evolution engine."""

    @pytest.fixture
    async def temp_db(self):
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        db = Database(f"sqlite:///{db_path}")
        db.init_db()
        yield db
        db.close()
        os.unlink(db_path)

    @pytest.fixture
    def repo(self, temp_db):
        session_maker = temp_db.session_maker()
        return Repository(session_maker)

    @pytest.fixture
    def candle_manager(self):
        cm = CandleManager()
        # Populate with test data
        base_time = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        tf_ms = 3600000  # 1h

        for i in range(500):
            price = 50000 + i * 10
            cm.add_candle("SPOT", "BTCUSDT", "1h",
                           base_time + i * tf_ms,
                           price, price + 50, price - 50, price + 10, 1000)

        return cm

    @pytest.fixture
    def backtester(self, repo, candle_manager):
        return HistoricalBacktester(repo, candle_manager)

    @pytest.fixture
    def engine(self, repo, backtester):
        return StrategyEvolutionEngine(repo, backtester)

    @pytest.mark.asyncio
    async def test_engine_initialization(self, engine):
        """Test engine initializes with baselines."""
        assert engine._baseline_configs is not None
        assert "rsi" in engine._baseline_configs
        assert "macd" in engine._baseline_configs
        assert "timeframe_weights" in engine._baseline_configs

    @pytest.mark.asyncio
    async def test_generate_experiment(self, engine):
        """Test generating a new experiment."""
        config = engine.generate_experiment(
            ExperimentType.PARAMETER_TUNING,
            "RSI Period Experiment",
            "Test shorter RSI period",
            {"rsi_period": 10}
        )

        assert config.experiment_id.startswith("exp_parameter_tuning_")
        assert config.experiment_type == ExperimentType.PARAMETER_TUNING
        assert config.parameter_changes == {"rsi_period": 10}
        assert config.status == ExperimentStatus.GENERATED

        # Check it's registered
        assert config.experiment_id in engine._experiments

    @pytest.mark.asyncio
    async def test_generate_experiment_invalid_parameter(self, engine):
        """Test generating experiment with invalid parameter raises error."""
        with pytest.raises(ValueError, match="SAFETY VIOLATION"):
            engine.generate_experiment(
                ExperimentType.PARAMETER_TUNING,
                "Bad Experiment",
                "Try to change risk limit",
                {"max_daily_loss_pct": 5.0}  # Safety boundary!
            )

    @pytest.mark.asyncio
    async def test_generate_experiment_out_of_range(self, engine):
        """Test generating experiment with out-of-range parameter raises error."""
        with pytest.raises(ValueError, match="outside allowed range"):
            engine.generate_experiment(
                ExperimentType.PARAMETER_TUNING,
                "Bad Experiment",
                "RSI period too high",
                {"rsi_period": 50}  # Max is 21
            )

    @pytest.mark.asyncio
    async def test_apply_changes(self, engine):
        """Test applying parameter changes."""
        changes = {"rsi_period": 10, "macd_fast": 8}
        result = engine._apply_changes(changes)

        assert result["rsi"]["period"] == 10
        assert result["macd"]["fast"] == 8
        # Other params unchanged
        assert result["rsi"]["overbought"] == 70

    @pytest.mark.asyncio
    async def test_run_backtest(self, engine):
        """Test running backtest for experiment."""
        config = engine.generate_experiment(
            ExperimentType.PARAMETER_TUNING,
            "Test Experiment",
            "Test description",
            {"rsi_period": 10}
        )

        # Mock the backtester to avoid long computation
        with patch.object(engine.backtester, 'run_backtest') as mock_bt:
            mock_result = MagicMock(spec=BacktestResult)
            mock_result.sharpe_ratio = 1.5
            mock_result.sortino_ratio = 1.8
            mock_result.calmar_ratio = 2.0
            mock_result.max_drawdown = 25.0
            mock_result.max_drawdown_pct = 5.0
            mock_result.metrics = {
                "total_trades": 60,
                "total_return": 15.0,
                "win_rate": 0.65,
                "profit_factor": 1.8,
            }
            mock_result.by_strategy = {}
            mock_result.by_market = {}
            mock_result.by_regime = {}
            mock_result.out_of_sample = {"sharpe": 1.2}

            mock_bt.return_value = mock_result

            result = engine.run_backtest(config.experiment_id)

        assert result.experiment_id == config.experiment_id
        assert result.backtest_result is not None
        assert config.status == ExperimentStatus.BACKTEST_COMPLETE

    @pytest.mark.asyncio
    async def test_start_shadow_test(self, engine):
        """Test starting shadow test."""
        config = engine.generate_experiment(
            ExperimentType.PARAMETER_TUNING,
            "Shadow Test",
            "Test shadow",
            {"rsi_period": 10}
        )

        # Mock backtest result
        engine._results[config.experiment_id] = ExperimentResult(
            experiment_id=config.experiment_id,
            backtest_result={
                "total_trades": 60,
                "total_return": 15.0,
                "win_rate": 0.65,
                "max_drawdown_pct": 5.0,
                "sharpe_ratio": 1.5,
            },
            comparison={
                "sharpe_improvement": 0.2,
                "drawdown_change_pct": -0.01,
                "win_rate_improvement": 0.02,
                "out_of_sample": {"sharpe": 1.0},  # Pass OOS check
            }
        )
        config.status = ExperimentStatus.BACKTEST_COMPLETE

        # Should succeed
        engine.start_shadow_test(config.experiment_id)
        assert config.status == ExperimentStatus.SHADOW_TESTING
        assert engine._active_shadow_experiment == config.experiment_id

    @pytest.mark.asyncio
    async def test_start_shadow_test_rejects_failed_backtest(self, engine):
        """Test shadow test rejected if backtest failed criteria."""
        config = engine.generate_experiment(
            ExperimentType.PARAMETER_TUNING,
            "Bad Backtest",
            "Test",
            {"rsi_period": 10}
        )

        # Backtest with too few trades
        engine._results[config.experiment_id] = ExperimentResult(
            experiment_id=config.experiment_id,
            backtest_result={
                "total_trades": 10,  # Below minimum
                "total_return": 5.0,
                "win_rate": 0.55,
                "max_drawdown_pct": 8.0,
                "sharpe_ratio": 0.8,
            },
            comparison={
                "sharpe_improvement": 0.05,  # Below minimum
                "drawdown_change_pct": 0.05,  # Worse
                "win_rate_improvement": -0.01,
            }
        )
        config.status = ExperimentStatus.BACKTEST_COMPLETE

        engine.start_shadow_test(config.experiment_id)
        assert config.status == ExperimentStatus.REJECTED

    @pytest.mark.asyncio
    async def test_evaluate_shadow_test(self, engine):
        """Test evaluating shadow test."""
        config = engine.generate_experiment(
            ExperimentType.PARAMETER_TUNING,
            "Shadow Eval",
            "Test",
            {"rsi_period": 10}
        )

        # Setup
        config.status = ExperimentStatus.SHADOW_TESTING
        engine._active_shadow_experiment = config.experiment_id
        engine._results[config.experiment_id] = ExperimentResult(
            experiment_id=config.experiment_id,
            backtest_result={"total_trades": 60, "sharpe_ratio": 1.5},
            comparison={}
        )

        with patch.object(engine, '_get_shadow_performance') as mock_perf:
            mock_perf.return_value = {
                "total_trades": 25,
                "total_pnl": 45.20,
                "win_rate": 0.64,
                "max_drawdown_pct": 3.2,
                "sharpe_ratio": 1.45,
            }

            with patch.object(engine, '_get_baseline_shadow_performance') as mock_base:
                mock_base.return_value = {
                    "total_trades": 30,
                    "total_pnl": 38.50,
                    "win_rate": 0.60,
                    "max_drawdown_pct": 2.8,
                    "sharpe_ratio": 1.20,
                }

                result = engine.evaluate_shadow_test(config.experiment_id, days_completed=7)

        assert result.shadow_result is not None
        assert "shadow" in result.comparison

    @pytest.mark.asyncio
    async def test_rollback_experiment(self, engine):
        """Test rolling back an experiment."""
        config = engine.generate_experiment(
            ExperimentType.PARAMETER_TUNING,
            "Rollback Test",
            "Test",
            {"rsi_period": 10}
        )

        config.status = ExperimentStatus.ACCEPTED
        engine._results[config.experiment_id] = ExperimentResult(
            experiment_id=config.experiment_id,
            accepted=True
        )

        success = engine.rollback_experiment(config.experiment_id)
        assert success is True
        assert config.status == ExperimentStatus.ROLLED_BACK

    @pytest.mark.asyncio
    async def test_get_experiment_registry(self, engine):
        """Test getting experiment registry."""
        config1 = engine.generate_experiment(
            ExperimentType.PARAMETER_TUNING,
            "Exp 1",
            "Test",
            {"rsi_period": 10}
        )

        config2 = engine.generate_experiment(
            ExperimentType.INDICATOR_THRESHOLD,
            "Exp 2",
            "Test",
            {"rsi_overbought": 75}
        )

        registry = engine.get_experiment_registry()
        assert len(registry) == 2
        assert registry[0]["experiment_id"] == config1.experiment_id
        assert registry[1]["experiment_id"] == config2.experiment_id
        assert registry[0]["type"] == "PARAMETER_TUNING"
        assert registry[1]["type"] == "INDICATOR_THRESHOLD"


class TestExperimentRegistry:
    """Test experiment registry persistence."""

    @pytest.fixture
    async def temp_db(self):
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        db = Database(f"sqlite:///{db_path}")
        db.init_db()
        yield db
        db.close()
        os.unlink(db_path)

    @pytest.fixture
    def repo(self, temp_db):
        session_maker = temp_db.session_maker()
        return Repository(session_maker)

    @pytest.mark.asyncio
    async def test_save_and_load_experiment(self, repo):
        """Test saving and loading experiment."""
        registry = ExperimentRegistry(repo)

        config = ExperimentConfig(
            experiment_id="exp_registry_001",
            experiment_type=ExperimentType.PARAMETER_TUNING,
            name="Registry Test",
            description="Test persistence",
            base_config_hash="abc123",
            parameter_changes={"rsi_period": 10},
        )

        result = ExperimentResult(
            experiment_id=config.experiment_id,
            accepted=True,
            evaluated_at=datetime.now(timezone.utc)
        )

        registry.save_experiment(config, result)

        # Load back
        loaded = registry.load_experiments()
        assert len(loaded) == 1
        assert loaded[0]["config"]["experiment_id"] == "exp_registry_001"
        assert loaded[0]["config"]["name"] == "Registry Test"
        assert loaded[0]["result"]["accepted"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])