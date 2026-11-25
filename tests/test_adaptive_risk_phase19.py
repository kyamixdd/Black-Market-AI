"""Tests for Phase 19 Adaptive Risk Intelligence."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from risk.adaptive_risk import (
    AdaptiveRiskEngine,
    RiskAction,
    RiskAssessment,
    RiskFactor,
    RiskLevel,
    RiskThresholds,
)
from config import (
    MAX_SPOT_POSITIONS,
    MAX_FUTURES_POSITIONS,
    RISK_MAX_DAILY_LOSS_PCT,
    RISK_MAX_LEVERAGE,
    RISK_MAX_TOTAL_OPEN_PCT,
    RISK_PER_TRADE_PCT,
)


class TestRiskThresholds:
    """Test risk threshold configuration."""

    def test_default_thresholds(self):
        """Test default risk thresholds."""
        thresholds = RiskThresholds()

        assert thresholds.volatility_warning_pct == 2.0
        assert thresholds.volatility_critical_pct == 5.0
        assert thresholds.drawdown_warning_pct == 5.0
        assert thresholds.drawdown_critical_pct == 10.0
        assert thresholds.consecutive_losses_warning == 3
        assert thresholds.consecutive_losses_critical == 5
        assert thresholds.correlation_warning_pct == 60.0
        assert thresholds.concentration_warning_pct == 20.0
        assert thresholds.funding_warning_pct == 0.05
        assert thresholds.liquidation_distance_warning_pct == 20.0
        assert thresholds.daily_loss_warning_pct == 0.5
        assert thresholds.data_quality_warning_score == 0.7
        assert thresholds.system_health_warning_score == 0.7


class TestAdaptiveRiskEngine:
    """Test adaptive risk engine."""

    @pytest.fixture
    def engine(self):
        """Create a fresh risk engine."""
        return AdaptiveRiskEngine()

    def test_engine_initialization(self, engine):
        """Test engine initializes with admin maximums."""
        assert engine.effective_risk_per_trade == RISK_PER_TRADE_PCT
        assert engine.effective_daily_loss_limit == RISK_MAX_DAILY_LOSS_PCT
        assert engine.effective_total_open_limit == RISK_MAX_TOTAL_OPEN_PCT
        assert engine.effective_leverage == RISK_MAX_LEVERAGE
        assert engine.effective_max_spot_positions == MAX_SPOT_POSITIONS
        assert engine.effective_max_futures_positions == MAX_FUTURES_POSITIONS

    def test_admin_maximums_are_immutable(self, engine):
        """Test admin maximums cannot be increased."""
        # Engine should never allow limits to exceed admin maximums
        assert engine.effective_risk_per_trade <= RISK_PER_TRADE_PCT
        assert engine.effective_leverage <= RISK_MAX_LEVERAGE
        assert engine.effective_max_spot_positions <= MAX_SPOT_POSITIONS
        assert engine.effective_max_futures_positions <= MAX_FUTURES_POSITIONS

    def test_assess_normal_risk(self, engine):
        """Test risk assessment with normal conditions."""
        assessment = engine.assess_risk(
            portfolio_value=1000.0,
            daily_pnl=10.0,  # 1% gain
            open_positions={},
            current_volatility={"BTCUSDT": 0.5},  # Very low volatility (well below 2% warning)
            data_quality_score=1.0,
            system_health_score=1.0,
            equity_high_water_mark=1000.0,
            equity_high_water_mark_since=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

        assert isinstance(assessment, RiskAssessment)
        assert assessment.overall_level == RiskLevel.NORMAL
        assert len(assessment.factors) == 10
        assert assessment.unavailable_factors == []
        assert next(f for f in assessment.factors if f.name == "liquidation").level == RiskLevel.NOT_APPLICABLE

    def test_missing_risk_evidence_is_not_reported_as_normal(self, engine):
        assessment = engine.assess_risk(
            portfolio_value=1000.0,
            daily_pnl=0.0,
            open_positions={},
            current_volatility={},
        )

        assert assessment.overall_level == RiskLevel.UNAVAILABLE
        assert set(assessment.unavailable_factors) == {
            "volatility", "drawdown", "data_quality", "system_health",
        }
        assert next(f for f in assessment.factors if f.name == "drawdown").current_value is None

    def test_drawdown_uses_persisted_high_water_mark_after_engine_recreation(self):
        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        first_engine = AdaptiveRiskEngine()
        second_engine = AdaptiveRiskEngine()

        first = first_engine.assess_risk(
            portfolio_value=920.0,
            daily_pnl=0.0,
            open_positions={},
            current_volatility={"BTCUSDT": 1.0},
            data_quality_score=1.0,
            system_health_score=1.0,
            equity_high_water_mark=1000.0,
            equity_high_water_mark_since=since,
        )
        restarted = second_engine.assess_risk(
            portfolio_value=920.0,
            daily_pnl=0.0,
            open_positions={},
            current_volatility={"BTCUSDT": 1.0},
            data_quality_score=1.0,
            system_health_score=1.0,
            equity_high_water_mark=1000.0,
            equity_high_water_mark_since=since,
        )

        for assessment in (first, restarted):
            factor = next(f for f in assessment.factors if f.name == "drawdown")
            assert factor.current_value == pytest.approx(8.0)
            assert factor.basis == f"all-time high-water mark since {since.isoformat()}"

    def test_drawdown_rejects_high_water_mark_below_current_equity(self, engine):
        assessment = engine.assess_risk(
            portfolio_value=1100.0,
            daily_pnl=0.0,
            open_positions={},
            current_volatility={"BTCUSDT": 1.0},
            equity_high_water_mark=1000.0,
            equity_high_water_mark_since=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

        factor = next(f for f in assessment.factors if f.name == "drawdown")
        assert factor.level == RiskLevel.UNAVAILABLE
        assert factor.current_value is None

    def test_correlation_exposure_uses_aligned_valid_returns(self, engine):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        timestamps = [start + timedelta(minutes=index) for index in range(40)]
        returns = [float(index % 7) for index in range(40)]
        positions = {
            "btc-position": {
                "symbol": "BTCUSDT", "amount": 0.002, "current_price": 50000.0,
                "market": "SPOT",
            },
            "eth-position": {
                "symbol": "ETHUSDT", "amount": 0.04, "current_price": 2500.0,
                "market": "SPOT",
            },
        }

        assessment = engine.assess_risk(
            portfolio_value=1000.0,
            daily_pnl=0.0,
            open_positions=positions,
            current_volatility={"BTCUSDT": 1.0},
            data_quality_score=1.0,
            system_health_score=1.0,
            equity_high_water_mark=1000.0,
            equity_high_water_mark_since=start,
            asset_returns={
                "BTCUSDT": list(zip(timestamps, returns)),
                "ETHUSDT": list(zip(timestamps, [value * 2 for value in returns])),
            },
        )

        factor = next(f for f in assessment.factors if f.name == "correlation")
        assert factor.current_value == pytest.approx(20.0)
        assert factor.level == RiskLevel.NORMAL

    def test_correlation_rejects_out_of_order_return_data(self, engine):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        timestamps = [start + timedelta(minutes=index) for index in range(40)]
        positions = {
            "BTCUSDT": {"amount": 1.0, "current_price": 100.0},
            "ETHUSDT": {"amount": 1.0, "current_price": 100.0},
        }

        assessment = engine.assess_risk(
            portfolio_value=1000.0,
            daily_pnl=0.0,
            open_positions=positions,
            current_volatility={"BTCUSDT": 1.0},
            asset_returns={
                "BTCUSDT": list(zip(timestamps, [float(index) for index in range(40)])),
                "ETHUSDT": list(zip(reversed(timestamps), [float(index) for index in range(40)])),
            },
        )

        factor = next(f for f in assessment.factors if f.name == "correlation")
        assert factor.level == RiskLevel.UNAVAILABLE
        assert factor.current_value is None

    def test_assess_elevated_volatility(self, engine):
        """Test risk assessment with elevated volatility."""
        assessment = engine.assess_risk(
            portfolio_value=1000.0,
            daily_pnl=0.0,
            open_positions={},
            current_volatility={"BTCUSDT": 3.0},  # Between warning (2%) and critical (5%)
            data_quality_score=1.0,
            system_health_score=1.0,
        )

        vol_factor = next(f for f in assessment.factors if f.name == "volatility")
        assert vol_factor.level == RiskLevel.HIGH
        assert assessment.overall_level in (RiskLevel.HIGH, RiskLevel.ELEVATED)

    def test_assess_critical_volatility(self, engine):
        """Test risk assessment with critical volatility."""
        assessment = engine.assess_risk(
            portfolio_value=1000.0,
            daily_pnl=0.0,
            open_positions={},
            current_volatility={"BTCUSDT": 6.0},  # Above critical (5%)
            data_quality_score=1.0,
            system_health_score=1.0,
        )

        vol_factor = next(f for f in assessment.factors if f.name == "volatility")
        assert vol_factor.level == RiskLevel.CRITICAL
        assert assessment.overall_level == RiskLevel.CRITICAL

        # Should trigger multiple protective actions
        assert RiskAction.PAUSE_NEW_ENTRIES in assessment.actions
        assert RiskAction.ACTIVATE_COOLDOWN in assessment.actions
        assert RiskAction.REDUCE_POSITION_SIZE in assessment.actions

    def test_consecutive_losses_tracking(self, engine):
        """Test consecutive loss tracking."""
        # Record losing trades
        engine.record_trade_result(-10.0)
        engine.record_trade_result(-15.0)
        engine.record_trade_result(-5.0)

        assert engine._consecutive_losses == 3

        assessment = engine.assess_risk(
            portfolio_value=1000.0,
            daily_pnl=-30.0,
            open_positions={},
            current_volatility={"BTCUSDT": 1.0},
            data_quality_score=1.0,
            system_health_score=1.0,
        )

        loss_factor = next(f for f in assessment.factors if f.name == "consecutive_losses")
        assert loss_factor.level == RiskLevel.HIGH  # 3 losses = warning threshold

        # Win resets counter
        engine.record_trade_result(20.0)
        assert engine._consecutive_losses == 0

    def test_cooldown_activation(self, engine):
        """Test cooldown activation on critical risk."""
        # Trigger critical volatility
        assessment = engine.assess_risk(
            portfolio_value=1000.0,
            daily_pnl=0.0,
            open_positions={},
            current_volatility={"BTCUSDT": 10.0},  # Way above critical
            data_quality_score=1.0,
            system_health_score=1.0,
        )

        assert RiskAction.ACTIVATE_COOLDOWN in assessment.actions
        assert engine._cooldown_until is not None
        assert engine.is_paused is True
        assert engine.cooldown_remaining_seconds > 0

    def test_cooldown_expiry(self, engine):
        """Test cooldown expiry."""
        # Manually set cooldown in past
        engine._cooldown_until = datetime.now(timezone.utc) - timedelta(hours=1)

        assert engine.is_paused is False
        assert engine.cooldown_remaining_seconds == 0

    def test_manual_cooldown_reset(self, engine):
        """Test manual cooldown reset restores limits."""
        # First trigger some reductions
        engine._effective_risk_per_trade = 0.2  # Reduced
        engine._effective_leverage = 1.5  # Reduced
        engine._paused = True
        engine._cooldown_until = datetime.now(timezone.utc) + timedelta(hours=2)

        engine.reset_cooldown()

        assert engine._paused is False
        assert engine._cooldown_until is None
        assert engine.effective_risk_per_trade == RISK_PER_TRADE_PCT
        assert engine.effective_leverage == RISK_MAX_LEVERAGE

    def test_position_concentration_assessment(self, engine):
        """Test asset concentration risk assessment."""
        positions = {
            "BTCUSDT": {
                "symbol": "BTCUSDT",
                "market": "SPOT",
                "amount": 0.05,
                "current_price": 50000.0,
                "entry_price": 49000.0,
            },
            "ETHUSDT": {
                "symbol": "ETHUSDT",
                "market": "SPOT",
                "amount": 0.5,
                "current_price": 3000.0,
                "entry_price": 2900.0,
            },
        }

        # BTC position = 0.05 * 50000 = 2500, ETH = 0.5 * 3000 = 1500
        # Total = 4000, BTC concentration = 2500/4000 = 62.5% (above critical 35%)
        assessment = engine.assess_risk(
            portfolio_value=4000.0,
            daily_pnl=0.0,
            open_positions=positions,
            current_volatility={"BTCUSDT": 1.0, "ETHUSDT": 1.0},
            data_quality_score=1.0,
            system_health_score=1.0,
        )

        conc_factor = next(f for f in assessment.factors if f.name == "concentration")
        # Concentration should be detected as high/critical
        assert conc_factor.level in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    def test_liquidation_distance_assessment(self, engine):
        """Test liquidation distance risk assessment."""
        positions = {
            "BTCUSDT": {
                "symbol": "BTCUSDT",
                "market": "FUTURES",
                "side": "LONG",
                "amount": 0.1,
                "current_price": 45000.0,
                "entry_price": 50000.0,
                "liq_price": 42000.0,
                "leverage": 3.0,
            },
        }

        # Current 45000, liq 42000, distance = (45000-42000)/45000 = 6.7% (below warning 20%)
        assessment = engine.assess_risk(
            portfolio_value=1000.0,
            daily_pnl=0.0,
            open_positions=positions,
            current_volatility={"BTCUSDT": 1.0},
            data_quality_score=1.0,
            system_health_score=1.0,
        )

        liq_factor = next(f for f in assessment.factors if f.name == "liquidation")
        assert liq_factor.level in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    def test_can_open_position_respects_pause(self, engine):
        """Test position opening blocked during pause."""
        engine._paused = True

        can_open, reason = engine.can_open_position("SPOT", 0)
        assert can_open is False
        assert "paused" in reason.lower()

    def test_can_open_position_respects_max_positions(self, engine):
        """Test position opening blocked at max positions."""
        can_open, reason = engine.can_open_position("SPOT", MAX_SPOT_POSITIONS)
        assert can_open is False
        assert "max" in reason.lower()

    def test_can_open_position_allowed(self, engine):
        """Test position opening allowed when under limits."""
        can_open, reason = engine.can_open_position("SPOT", 2)
        assert can_open is True
        assert reason == "OK"

    def test_effective_limits_reduced_on_critical(self, engine):
        """Test effective limits are reduced on critical risk."""
        # Trigger critical risk
        engine.assess_risk(
            portfolio_value=1000.0,
            daily_pnl=0.0,
            open_positions={},
            current_volatility={"BTCUSDT": 10.0},
            data_quality_score=1.0,
            system_health_score=1.0,
        )

        # Limits should be reduced
        assert engine.effective_risk_per_trade < RISK_PER_TRADE_PCT
        assert engine.effective_leverage < RISK_MAX_LEVERAGE
        assert engine.effective_max_spot_positions < MAX_SPOT_POSITIONS
        assert engine.effective_max_futures_positions < MAX_FUTURES_POSITIONS

    def test_never_exceeds_admin_maximums(self, engine):
        """Test engine never allows limits to exceed admin maximums."""
        # Even if we somehow try to increase, it should cap at admin max
        engine._effective_risk_per_trade = 10.0  # Artificially set high
        engine._restore_limits()  # Should cap at admin max

        assert engine.effective_risk_per_trade == RISK_PER_TRADE_PCT

    def test_get_status(self, engine):
        """Test status reporting."""
        status = engine.get_status()

        assert "paused" in status
        assert "cooldown_until" in status
        assert "effective_limits" in status
        assert "admin_maximums" in status
        assert "reduction_active" in status

        assert status["admin_maximums"]["risk_per_trade_pct"] == RISK_PER_TRADE_PCT
        assert status["admin_maximums"]["max_leverage"] == RISK_MAX_LEVERAGE

    def test_risk_budget_calculation(self, engine):
        """Test risk budget calculation."""
        positions = {
            "BTCUSDT": {
                "entry_price": 50000.0,
                "stop_loss": 49000.0,
                "amount": 0.2,  # 0.2 BTC = 10000 notional, risk = 1000 * 0.2 = 200
            },
        }

        budget = engine._calculate_risk_budget(positions, 1000.0)
        # Risk = (50000-49000) * 0.2 = 200, budget = 200/1000 * 100 = 20%
        assert budget == 20.0

    def test_data_quality_factor(self, engine):
        """Test data quality risk factor."""
        assessment = engine.assess_risk(
            portfolio_value=1000.0,
            daily_pnl=0.0,
            open_positions={},
            current_volatility={"BTCUSDT": 1.0},
            data_quality_score=0.3,  # Below critical (0.4)
            system_health_score=1.0,
        )

        dq_factor = next(f for f in assessment.factors if f.name == "data_quality")
        assert dq_factor.level == RiskLevel.CRITICAL

    def test_system_health_factor(self, engine):
        """Test system health risk factor."""
        assessment = engine.assess_risk(
            portfolio_value=1000.0,
            daily_pnl=0.0,
            open_positions={},
            current_volatility={"BTCUSDT": 1.0},
            data_quality_score=1.0,
            system_health_score=0.3,  # Below critical (0.4)
        )

        sh_factor = next(f for f in assessment.factors if f.name == "system_health")
        assert sh_factor.level == RiskLevel.CRITICAL


class TestRiskActionEnum:
    """Test RiskAction enum values."""

    def test_all_actions_defined(self):
        """Test all expected risk actions exist."""
        actions = [a.value for a in RiskAction]
        assert "NONE" in actions
        assert "REDUCE_POSITION_SIZE" in actions
        assert "REDUCE_MAX_POSITIONS" in actions
        assert "REDUCE_LEVERAGE" in actions
        assert "PAUSE_NEW_ENTRIES" in actions
        assert "ACTIVATE_COOLDOWN" in actions
        assert "REDUCE_DAILY_LOSS_LIMIT" in actions
        assert "CLOSE_RISKIEST_POSITIONS" in actions


class TestRiskLevelEnum:
    """Test RiskLevel enum."""

    def test_level_ordering(self):
        """Test risk levels have correct severity ordering."""
        levels = [RiskLevel.NORMAL, RiskLevel.ELEVATED, RiskLevel.HIGH, RiskLevel.CRITICAL]
        # Should be ordered by severity
        assert levels[0].value == "NORMAL"
        assert levels[3].value == "CRITICAL"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])