"""Tests for Phase 20 Performance Drift and Reliability Monitoring."""
from datetime import datetime, timezone, timedelta
import pytest
from unittest.mock import patch

from monitoring.drift_monitor import (
    AlertSeverity,
    DriftAlert,
    DriftMonitor,
    DriftThresholds,
    DriftType,
    RollingMetrics,
)
from database.repositories import Repository
from database.connection import Database
import tempfile
import os


class TestRollingMetrics:
    """Test rolling metrics calculation."""

    def test_rolling_metrics_basic(self):
        """Test basic rolling metrics operations."""
        rm = RollingMetrics(window_size=5)
        for i in range(10):
            rm.add(float(i))

        assert len(rm.values) == 5
        assert list(rm.values) == [5.0, 6.0, 7.0, 8.0, 9.0]
        assert rm.mean() == 7.0
        assert rm.min() == 5.0
        assert rm.max() == 9.0

    def test_rolling_metrics_trend(self):
        """Test trend calculation."""
        rm = RollingMetrics(window_size=20)
        # Add upward trend
        for i in range(15):
            rm.add(float(i) * 0.1)

        trend = rm.trend(periods=10)
        assert trend > 0  # Positive slope

        # Add downward trend
        for i in range(15, 25):
            rm.add(1.5 - (i - 15) * 0.1)

        trend = rm.trend(periods=10)
        assert trend < 0  # Negative slope

    def test_is_degrading(self):
        """Test degradation detection."""
        rm = RollingMetrics(window_size=50)
        # Stable then degrading
        for i in range(30):
            rm.add(0.8)
        for i in range(30, 50):
            rm.add(0.8 - (i - 30) * 0.01)

        assert rm.is_degrading(min_periods=20, threshold=-0.001) is True

        # Stable - not degrading
        rm2 = RollingMetrics(window_size=50)
        for i in range(50):
            rm2.add(0.8 + (i % 5) * 0.01)
        assert rm2.is_degrading(min_periods=20, threshold=-0.001) is False


class TestDriftThresholds:
    """Test drift threshold configuration."""

    def test_default_thresholds(self):
        """Test default drift thresholds."""
        t = DriftThresholds()

        assert t.accuracy_warning_drop == 0.05
        assert t.accuracy_critical_drop == 0.10
        assert t.calibration_warning_increase == 0.02
        assert t.strategy_sharpe_warning_drop == 0.3
        assert t.feature_psi_warning == 0.1
        assert t.data_quality_warning_score == 0.8
        assert t.cpu_warning_pct == 80.0


class TestDriftMonitor:
    """Test drift monitor functionality."""

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
    def repo(self, temp_db):
        session_maker = temp_db.session_maker()
        return Repository(session_maker)

    @pytest.fixture
    def monitor(self, repo):
        return DriftMonitor(repo)

    def test_monitor_initialization(self, monitor):
        """Test monitor initializes correctly."""
        assert monitor.thresholds is not None
        assert monitor._baseline_established is False
        assert monitor._last_regime == "UNKNOWN"

    def test_accuracy_drift_warning(self, monitor):
        """Test prediction accuracy warning detection."""
        # Establish baseline - need 100+ samples BEFORE the check
        for _ in range(120):
            monitor._prediction_accuracy.add(0.75)

        # Now check with degraded accuracy - baseline is 0.75, current is 0.70 = 5% drop
        alerts = monitor.check_all(current_accuracy=0.70)  # 5% drop = warning
        assert len(alerts) >= 1
        acc_alert = next(a for a in alerts if a.drift_type == DriftType.PREDICTION_ACCURACY)
        assert acc_alert.severity == AlertSeverity.WARNING
        assert "5.0%" in acc_alert.message or "5%" in acc_alert.message
        assert "75.0%" in acc_alert.message and "70.0%" in acc_alert.message

    def test_accuracy_drift_critical(self, monitor):
        """Test prediction accuracy critical detection."""
        # Establish baseline
        for _ in range(120):
            monitor._prediction_accuracy.add(0.75)

        # Check with critical degradation - 15% drop
        alerts = monitor.check_all(current_accuracy=0.60)  # 15% drop = critical
        acc_alert = next(a for a in alerts if a.drift_type == DriftType.PREDICTION_ACCURACY)
        assert acc_alert.severity == AlertSeverity.CRITICAL
        assert "15.0%" in acc_alert.message or "15%" in acc_alert.message

    def test_calibration_drift(self, monitor):
        """Test model calibration drift detection."""
        # Establish baseline (lower Brier = better)
        for _ in range(60):
            monitor._model_calibration.add(0.10)

        # Check with worse calibration (higher Brier)
        alerts = monitor.check_all(current_calibration=0.15)  # +0.05 increase
        cal_alert = next(a for a in alerts if a.drift_type == DriftType.MODEL_CALIBRATION)
        assert cal_alert.severity == AlertSeverity.CRITICAL

    def test_strategy_drift_warning(self, monitor):
        """Test strategy performance drift warning."""
        # Establish baseline - need 30+ samples
        perf = RollingMetrics(window_size=200)
        for _ in range(40):
            perf.add(1.5)
        monitor._strategy_performance["momentum"] = perf

        # Check with degraded strategy - baseline 1.5, current 1.1 = 0.4 drop = warning (threshold is 0.3)
        alerts = monitor.check_all(strategy_metrics={
            "momentum": {"sharpe": 1.1, "trades": 50}  # 0.4 drop = warning
        })
        strat_alert = next(a for a in alerts if a.drift_type == DriftType.STRATEGY_PERFORMANCE)
        assert strat_alert.severity == AlertSeverity.WARNING

    def test_strategy_drift_critical(self, monitor):
        """Test strategy performance critical drift."""
        # Establish baseline
        perf = RollingMetrics(window_size=200)
        for _ in range(40):
            perf.add(1.5)
        monitor._strategy_performance["momentum"] = perf

        # Check with critical degradation - baseline 1.5, current 0.8 = 0.7 drop = critical
        alerts = monitor.check_all(strategy_metrics={
            "momentum": {"sharpe": 0.8, "trades": 50}  # 0.7 drop = critical
        })
        strat_alert = next(a for a in alerts if a.drift_type == DriftType.STRATEGY_PERFORMANCE)
        assert strat_alert.severity == AlertSeverity.CRITICAL

    def test_feature_drift_psi(self, monitor):
        """Test feature distribution drift via PSI."""
        alerts = monitor.check_all(feature_stats={
            "rsi_14": 0.15,  # Warning
            "macd_hist": 0.25,  # Critical
        })

        feature_alerts = [a for a in alerts if a.drift_type == DriftType.FEATURE_DISTRIBUTION]
        assert len(feature_alerts) == 2

        psi_critical = next(a for a in feature_alerts if a.metric_name == "macd_hist_psi")
        assert psi_critical.severity == AlertSeverity.CRITICAL

        psi_warning = next(a for a in feature_alerts if a.metric_name == "rsi_14_psi")
        assert psi_warning.severity == AlertSeverity.WARNING

    def test_regime_shift_detection(self, monitor):
        """Test market regime shift detection."""
        # Simulate regime changes - need 5+ changes in last 20
        # Create 6 regime segments to get 5+ changes
        regimes = ["BULL_TREND"] * 4 + ["BEAR_TREND"] * 3 + ["SIDEWAYS"] * 3 + ["HIGH_VOLATILITY"] * 3 + ["BULL_TREND"] * 3 + ["BEAR_TREND"] * 4
        for r in regimes:
            alerts = monitor.check_all(current_regime=r)

        # Should detect instability (5+ changes in last 20)
        # Last 20 entries will have: BEAR->SIDEWAYS, SIDEWAYS->HIGH_VOL, HIGH_VOL->BULL, BULL->BEAR = 4 changes
        # Need one more - let's make it 5+ by having more segments in last 20
        # Actually the last 20 will have the last segments
        alerts = monitor.check_all(current_regime="SIDEWAYS")  # This makes 5th change in last 20

        regime_alerts = [a for a in alerts if a.drift_type == DriftType.MARKET_REGIME_SHIFT]
        assert len(regime_alerts) >= 1
        assert regime_alerts[0].severity == AlertSeverity.WARNING

    def test_adverse_regime_persistence(self, monitor):
        """Test extended adverse regime detection."""
        # Stay in BEAR_TREND for many days
        monitor._regime_stability_days = 10
        monitor._last_regime = "BEAR_TREND"

        alerts = monitor.check_all(current_regime="BEAR_TREND")
        regime_alerts = [a for a in alerts if a.drift_type == DriftType.MARKET_REGIME_SHIFT]
        assert len(regime_alerts) >= 1
        assert "Extended adverse regime" in regime_alerts[0].message

    def test_data_quality_critical(self, monitor):
        """Test data quality critical alert."""
        alerts = monitor.check_all(data_quality_score=0.3)  # Below 0.5 critical
        dq_alert = next(a for a in alerts if a.drift_type == DriftType.DATA_QUALITY)
        assert dq_alert.severity == AlertSeverity.CRITICAL

    def test_data_quality_warning(self, monitor):
        """Test data quality warning alert."""
        alerts = monitor.check_all(data_quality_score=0.6)  # Between 0.5 and 0.8
        dq_alert = next(a for a in alerts if a.drift_type == DriftType.DATA_QUALITY)
        assert dq_alert.severity == AlertSeverity.WARNING

    def test_system_resources_cpu_critical(self, monitor):
        """Test CPU critical alert."""
        alerts = monitor.check_all(system_cpu_pct=96.0)
        cpu_alert = next(a for a in alerts if a.drift_type == DriftType.SYSTEM_RESOURCES)
        assert cpu_alert.severity == AlertSeverity.CRITICAL
        assert "CPU" in cpu_alert.message

    def test_system_resources_cpu_warning(self, monitor):
        """Test CPU warning alert."""
        alerts = monitor.check_all(system_cpu_pct=85.0)
        cpu_alert = next(a for a in alerts if a.drift_type == DriftType.SYSTEM_RESOURCES)
        assert cpu_alert.severity == AlertSeverity.WARNING

    def test_system_resources_memory_critical(self, monitor):
        """Test memory critical alert."""
        alerts = monitor.check_all(system_cpu_pct=50.0, system_memory_pct=96.0)
        mem_alert = next(a for a in alerts if a.drift_type == DriftType.SYSTEM_RESOURCES)
        assert mem_alert.severity == AlertSeverity.CRITICAL
        assert "Memory" in mem_alert.message

    def test_system_resources_disk_critical(self, monitor):
        """Test disk critical alert."""
        alerts = monitor.check_all(system_cpu_pct=50.0, system_disk_pct=99.0)
        disk_alert = next(a for a in alerts if a.drift_type == DriftType.SYSTEM_RESOURCES)
        assert disk_alert.severity == AlertSeverity.CRITICAL
        assert "Disk" in disk_alert.message

    def test_accuracy_trend_detection(self, monitor):
        """Test degrading trend detection."""
        # First establish baseline - need 100+ samples for baseline
        for _ in range(120):
            monitor._prediction_accuracy.add(0.75)

        # Add a FAST degrading trend to ensure trend detection triggers
        # Need slope < -0.001 over last 20 periods
        for i in range(50):
            monitor._prediction_accuracy.add(0.75 - i * 0.002)  # Degrading from 0.75 to 0.65 over 50 steps

        # Now check with a value that continues the trend but does NOT exceed
        # the 5% absolute drop threshold (baseline 0.75 * 0.95 = 0.7125)
        # Use 0.72 to continue trend without triggering absolute drop alert
        alerts = monitor.check_all(current_accuracy=0.720)
        trend_alert = next((a for a in alerts if a.metric_name == "accuracy_trend"), None)
        assert trend_alert is not None, f"No trend alert found. Alerts: {[a.metric_name for a in alerts]}"
        assert trend_alert.severity == AlertSeverity.WARNING

    def test_strategy_trend_detection(self, monitor):
        """Test strategy performance trend detection."""
        monitor._strategy_performance["trend_following"] = RollingMetrics(window_size=200)
        for i in range(50):
            monitor._strategy_performance["trend_following"].add(1.5 - i * 0.02)

        alerts = monitor.check_all(strategy_metrics={
            "trend_following": {"sharpe": 0.5, "trades": 50}
        })
        trend_alert = next((a for a in alerts if "trend" in a.metric_name and a.drift_type == DriftType.STRATEGY_PERFORMANCE), None)
        assert trend_alert is not None

    def test_get_recent_alerts_filtering(self, monitor):
        """Test alert filtering by severity and type."""
        # First establish accuracy baseline
        for _ in range(120):
            monitor._prediction_accuracy.add(0.75)

        # Generate some alerts - accuracy critical + CPU critical + data quality warning
        monitor.check_all(current_accuracy=0.60)  # Critical (15% drop)
        monitor.check_all(system_cpu_pct=96.0)  # Critical
        monitor.check_all(data_quality_score=0.6)  # Warning

        all_alerts = monitor.get_recent_alerts(hours=24)
        critical_alerts = monitor.get_recent_alerts(severity=AlertSeverity.CRITICAL, hours=24)
        warning_alerts = monitor.get_recent_alerts(severity=AlertSeverity.WARNING, hours=24)
        accuracy_alerts = monitor.get_recent_alerts(drift_type=DriftType.PREDICTION_ACCURACY, hours=24)

        # Accuracy drop is critical (15%), CPU is critical, data quality is warning
        assert len(critical_alerts) >= 2
        assert len(warning_alerts) >= 1
        assert len(accuracy_alerts) >= 1

    def test_acknowledge_alert(self, monitor):
        """Test alert acknowledgment."""
        # First establish baseline
        for _ in range(120):
            monitor._prediction_accuracy.add(0.75)

        # Now generate an alert
        alerts = monitor.check_all(current_accuracy=0.60)
        assert len(alerts) >= 1
        alert = alerts[0]
        assert alert.acknowledged is False

        monitor.acknowledge_alert(alert)
        assert alert.acknowledged is True

    def test_get_status(self, monitor):
        """Test status reporting."""
        monitor._baselines["accuracy"] = 0.75
        monitor._baseline_established = True

        status = monitor.get_status()
        assert status["baselines_established"] is True
        assert "accuracy" in status["baselines"]
        assert "recent_alerts_24h" in status
        assert "critical_alerts_24h" in status
        assert "regime_stability_days" in status

    def test_reset_baselines(self, monitor):
        """Test baseline reset."""
        monitor._baselines["accuracy"] = 0.75
        monitor._prediction_accuracy.add(0.7)
        monitor._model_calibration.add(0.1)

        monitor.reset_baselines()

        assert len(monitor._baselines) == 0
        assert monitor._baseline_established is False
        assert len(monitor._prediction_accuracy.values) == 0
        assert len(monitor._model_calibration.values) == 0


class TestDriftAlert:
    """Test drift alert dataclass."""

    def test_alert_creation(self):
        """Test creating a drift alert."""
        alert = DriftAlert(
            drift_type=DriftType.PREDICTION_ACCURACY,
            severity=AlertSeverity.WARNING,
            message="Test alert",
            metric_name="accuracy",
            current_value=0.65,
            baseline_value=0.75,
            threshold=0.05,
        )

        assert alert.drift_type == DriftType.PREDICTION_ACCURACY
        assert alert.severity == AlertSeverity.WARNING
        assert alert.acknowledged is False
        assert len(alert.recovery_recommendations) == 0

    def test_alert_with_recommendations(self):
        """Test alert with recovery recommendations."""
        alert = DriftAlert(
            drift_type=DriftType.MODEL_CALIBRATION,
            severity=AlertSeverity.CRITICAL,
            message="Calibration failed",
            metric_name="brier",
            current_value=0.2,
            baseline_value=0.1,
            threshold=0.05,
            recovery_recommendations=["Recalibrate", "Retrain"],
        )

        assert len(alert.recovery_recommendations) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])