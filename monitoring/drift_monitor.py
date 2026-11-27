"""Performance Drift and Reliability Monitoring: detects degradation and generates recovery recommendations."""
from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

if TYPE_CHECKING:
    from database.repositories import Repository
    from risk.adaptive_risk import AdaptiveRiskEngine

logger = logging.getLogger(__name__)


class DriftType(Enum):
    """Types of drift and degradation detected."""
    PREDICTION_ACCURACY = "PREDICTION_ACCURACY"
    MODEL_CALIBRATION = "MODEL_CALIBRATION"
    STRATEGY_PERFORMANCE = "STRATEGY_PERFORMANCE"
    FEATURE_DISTRIBUTION = "FEATURE_DISTRIBUTION"
    MARKET_REGIME_SHIFT = "MARKET_REGIME_SHIFT"
    DATA_QUALITY = "DATA_QUALITY"
    SYSTEM_RESOURCES = "SYSTEM_RESOURCES"


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class DriftThresholds:
    """Configurable thresholds for drift detection."""
    # Prediction accuracy
    accuracy_warning_drop: float = 0.05  # 5% drop from baseline
    accuracy_critical_drop: float = 0.10  # 10% drop
    min_samples_for_accuracy: int = 100

    # Calibration (Brier score increase)
    calibration_warning_increase: float = 0.02
    calibration_critical_increase: float = 0.05

    # Strategy performance (Sharpe ratio drop)
    strategy_sharpe_warning_drop: float = 0.3
    strategy_sharpe_critical_drop: float = 0.5
    min_trades_for_strategy: int = 30

    # Feature distribution (KS test / PSI)
    feature_psi_warning: float = 0.1  # Population Stability Index
    feature_psi_critical: float = 0.2

    # Market regime (unexpected regime frequency)
    regime_shift_warning_days: int = 7
    regime_shift_critical_days: int = 3

    # Data quality
    data_quality_warning_score: float = 0.8
    data_quality_critical_score: float = 0.5

    # System resources
    cpu_warning_pct: float = 80.0
    cpu_critical_pct: float = 95.0
    memory_warning_pct: float = 85.0
    memory_critical_pct: float = 95.0
    disk_warning_pct: float = 90.0
    disk_critical_pct: float = 98.0


@dataclass
class DriftAlert:
    """A drift or degradation alert."""
    drift_type: DriftType
    severity: AlertSeverity
    message: str
    metric_name: str
    current_value: float
    baseline_value: float
    threshold: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    recovery_recommendations: list[str] = field(default_factory=list)
    acknowledged: bool = False


@dataclass
class RollingMetrics:
    """Rolling window metrics for drift detection."""
    window_size: int = 100
    values: deque = field(default_factory=deque)

    def __post_init__(self):
        # Ensure deque has correct maxlen
        if self.values.maxlen != self.window_size:
            self.values = deque(self.values, maxlen=self.window_size)

    def add(self, value: float) -> None:
        if len(self.values) >= self.window_size and self.window_size > 0:
            self.values.popleft()
        self.values.append(value)

    def mean(self) -> float:
        return float(np.mean(self.values)) if self.values else 0.0

    def std(self) -> float:
        return float(np.std(self.values)) if len(self.values) > 1 else 0.0

    def min(self) -> float:
        return float(np.min(self.values)) if self.values else 0.0

    def max(self) -> float:
        return float(np.max(self.values)) if self.values else 0.0

    def trend(self, periods: int = 10) -> float:
        """Calculate linear trend over last N periods."""
        if len(self.values) < periods:
            return 0.0
        recent = list(self.values)[-periods:]
        x = np.arange(len(recent))
        slope = np.polyfit(x, recent, 1)[0]
        return float(slope)

    def is_degrading(self, min_periods: int = 20, threshold: float = -0.001) -> bool:
        """Check if metric is trending downward."""
        if len(self.values) < min_periods:
            return False
        return bool(self.trend(min_periods) < threshold)


class DriftMonitor:
    """
    Monitors performance drift and system reliability.

    Detects:
    - Prediction accuracy degradation
    - Model calibration deterioration
    - Strategy underperformance
    - Feature distribution shifts
    - Market regime changes
    - Data quality failures
    - System resource exhaustion

    Generates structured alerts with recovery recommendations.
    """

    def __init__(
        self,
        repo: Repository,
        risk_engine: Optional[AdaptiveRiskEngine] = None,
        thresholds: Optional[DriftThresholds] = None,
    ):
        self.repo = repo
        self.risk_engine = risk_engine
        self.thresholds = thresholds or DriftThresholds()
        self._lock = threading.RLock()

        # Rolling metrics
        self._prediction_accuracy = RollingMetrics(window_size=200)
        self._model_calibration = RollingMetrics(window_size=200)
        self._strategy_performance: dict[str, RollingMetrics] = {}
        self._feature_distributions: dict[str, RollingMetrics] = {}
        self._data_quality = RollingMetrics(window_size=100)
        self._system_resources = {
            "cpu": RollingMetrics(window_size=100),
            "memory": RollingMetrics(window_size=100),
            "disk": RollingMetrics(window_size=100),
        }

        # Baseline values (set during initialization or first stable period)
        self._baselines: dict[str, float] = {}
        self._baseline_established = False

        # Alerts
        self._alerts: list[DriftAlert] = []
        self._max_alerts = 500

        # Regime tracking
        self._regime_history: deque = deque(maxlen=1000)
        self._last_regime = "UNKNOWN"
        self._regime_stability_days = 0
        self._regime_start_time: Optional[datetime] = None

        # State
        self._last_check = datetime.now(timezone.utc)

    def check_all(
        self,
        current_accuracy: Optional[float] = None,
        current_calibration: Optional[float] = None,
        strategy_metrics: Optional[dict[str, dict]] = None,
        feature_stats: Optional[dict[str, float]] = None,
        current_regime: Optional[str] = None,
        data_quality_score: Optional[float] = None,
        system_cpu_pct: Optional[float] = None,
        system_memory_pct: Optional[float] = None,
        system_disk_pct: Optional[float] = None,
    ) -> list[DriftAlert]:
        """
        Run all drift checks and return new alerts.

        Args:
            current_accuracy: Current prediction accuracy (0-1)
            current_calibration: Current Brier score (lower is better)
            strategy_metrics: Dict of strategy -> {sharpe, win_rate, trades, ...}
            feature_stats: Dict of feature -> PSI/statistic value
            current_regime: Current market regime
            data_quality_score: Data quality score (0-1)
            system_cpu_pct: CPU usage %
            system_memory_pct: Memory usage %
            system_disk_pct: Disk usage %

        Returns:
            List of new DriftAlert objects
        """
        with self._lock:
            new_alerts = []

            # 1. Prediction accuracy drift
            if current_accuracy is not None:
                alert = self._check_accuracy_drift(current_accuracy)
                if alert:
                    new_alerts.append(alert)

            # 2. Model calibration drift
            if current_calibration is not None:
                alert = self._check_calibration_drift(current_calibration)
                if alert:
                    new_alerts.append(alert)

            # 3. Strategy performance drift
            if strategy_metrics:
                alerts = self._check_strategy_drift(strategy_metrics)
                new_alerts.extend(alerts)

            # 4. Feature distribution drift
            if feature_stats:
                alerts = self._check_feature_drift(feature_stats)
                new_alerts.extend(alerts)

            # 5. Market regime shift
            if current_regime:
                alert = self._check_regime_shift(current_regime)
                if alert:
                    new_alerts.append(alert)

            # 6. Data quality degradation
            if data_quality_score is not None:
                alert = self._check_data_quality(data_quality_score)
                if alert:
                    new_alerts.append(alert)

            # 7. System resource exhaustion
            if system_cpu_pct is not None or system_memory_pct is not None or system_disk_pct is not None:
                alerts = self._check_system_resources(
                    system_cpu_pct, system_memory_pct, system_disk_pct
                )
                new_alerts.extend(alerts)

            # Store alerts
            for alert in new_alerts:
                self._alerts.append(alert)
                if len(self._alerts) > self._max_alerts:
                    self._alerts.pop(0)

            # Update last check
            self._last_check = datetime.now(timezone.utc)

            # Log alerts
            for alert in new_alerts:
                logger.warning(f"DRIFT ALERT [{alert.severity.value}]: {alert.drift_type.value} - {alert.message}")

            return new_alerts

    def _check_accuracy_drift(self, current_accuracy: float) -> Optional[DriftAlert]:
        """Check prediction accuracy degradation."""
        # Establish baseline BEFORE adding current value
        if not self._baseline_established and len(self._prediction_accuracy.values) >= self.thresholds.min_samples_for_accuracy:
            self._baselines["accuracy"] = self._prediction_accuracy.mean()
            self._baseline_established = True

        # Now add the current value
        self._prediction_accuracy.add(current_accuracy)

        if "accuracy" not in self._baselines:
            return None

        baseline = self._baselines["accuracy"]
        drop = baseline - current_accuracy

        # Check for degrading trend FIRST (before absolute drop)
        # This catches trend degradation BEFORE it hits absolute thresholds
        trend_alert = None
        if len(self._prediction_accuracy.values) >= 20 and self._prediction_accuracy.is_degrading(threshold=-0.0005):
            trend_alert = DriftAlert(
                drift_type=DriftType.PREDICTION_ACCURACY,
                severity=AlertSeverity.WARNING,
                message="Prediction accuracy shows consistent degrading trend",
                metric_name="accuracy_trend",
                current_value=self._prediction_accuracy.trend(),
                baseline_value=0.0,
                threshold=-0.0005,
                recovery_recommendations=[
                    "Investigate recent prediction failures",
                    "Check for feature drift",
                    "Schedule model retraining",
                ],
            )

        # Check absolute drop
        drop = baseline - current_accuracy

        if drop >= self.thresholds.accuracy_critical_drop:
            return DriftAlert(
                drift_type=DriftType.PREDICTION_ACCURACY,
                severity=AlertSeverity.CRITICAL,
                message=f"Prediction accuracy dropped {drop:.1%} from baseline ({baseline:.1%} -> {current_accuracy:.1%})",
                metric_name="accuracy",
                current_value=current_accuracy,
                baseline_value=baseline,
                threshold=self.thresholds.accuracy_critical_drop,
                recovery_recommendations=[
                    "Retrain models with recent data",
                    "Check for data quality issues",
                    "Verify feature engineering pipeline",
                    "Consider rolling back to previous model version",
                    "Increase walk-forward validation frequency",
                ],
            )
        elif drop >= self.thresholds.accuracy_warning_drop:
            return DriftAlert(
                drift_type=DriftType.PREDICTION_ACCURACY,
                severity=AlertSeverity.WARNING,
                message=f"Prediction accuracy dropped {drop:.1%} from baseline ({baseline:.1%} -> {current_accuracy:.1%})",
                metric_name="accuracy",
                current_value=current_accuracy,
                baseline_value=baseline,
                threshold=self.thresholds.accuracy_warning_drop,
                recovery_recommendations=[
                    "Monitor closely for continued degradation",
                    "Prepare retraining pipeline",
                    "Review recent market regime changes",
                ],
            )

        # Return trend alert if no absolute threshold was hit but trend is degrading
        if trend_alert:
            return trend_alert

        return None

    def _check_calibration_drift(self, current_brier: float) -> Optional[DriftAlert]:
        """Check model calibration deterioration (Brier score increase = worse)."""
        # Establish baseline BEFORE adding current value
        if "calibration" not in self._baselines and len(self._model_calibration.values) >= 50:
            self._baselines["calibration"] = self._model_calibration.mean()

        # Now add the current value
        self._model_calibration.add(current_brier)

        if "calibration" not in self._baselines:
            return None

        baseline = self._baselines["calibration"]
        increase = current_brier - baseline  # Higher Brier = worse calibration

        if increase >= self.thresholds.calibration_critical_increase:
            return DriftAlert(
                drift_type=DriftType.MODEL_CALIBRATION,
                severity=AlertSeverity.CRITICAL,
                message=f"Model calibration deteriorated: Brier score increased {increase:.4f} ({baseline:.4f} -> {current_brier:.4f})",
                metric_name="brier_score",
                current_value=current_brier,
                baseline_value=baseline,
                threshold=self.thresholds.calibration_critical_increase,
                recovery_recommendations=[
                    "Recalibrate model probabilities (Platt scaling / isotonic regression)",
                    "Retrain with proper probability calibration",
                    "Check for outcome labeling errors",
                    "Verify prediction horizon alignment",
                ],
            )
        elif increase >= self.thresholds.calibration_warning_increase:
            return DriftAlert(
                drift_type=DriftType.MODEL_CALIBRATION,
                severity=AlertSeverity.WARNING,
                message=f"Model calibration degrading: Brier score increased {increase:.4f}",
                metric_name="brier_score",
                current_value=current_brier,
                baseline_value=baseline,
                threshold=self.thresholds.calibration_warning_increase,
                recovery_recommendations=[
                    "Monitor calibration metrics closely",
                    "Prepare recalibration pipeline",
                ],
            )

        return None

    def _check_strategy_drift(self, strategy_metrics: dict[str, dict]) -> list[DriftAlert]:
        """Check strategy performance degradation."""
        alerts = []

        for strategy, metrics in strategy_metrics.items():
            if strategy not in self._strategy_performance:
                self._strategy_performance[strategy] = RollingMetrics(window_size=200)

            sharpe = metrics.get("sharpe", 0.0)
            trades = metrics.get("trades", 0)

            if trades < self.thresholds.min_trades_for_strategy:
                continue  # Insufficient data

            perf = self._strategy_performance[strategy]

            # Establish baseline BEFORE adding current value
            if f"strategy_{strategy}_sharpe" not in self._baselines and len(perf.values) >= 30:
                self._baselines[f"strategy_{strategy}_sharpe"] = perf.mean()

            # Now add current value
            perf.add(sharpe)

            key = f"strategy_{strategy}_sharpe"
            if key not in self._baselines:
                continue

            baseline = self._baselines[key]
            drop = baseline - sharpe

            if drop >= self.thresholds.strategy_sharpe_critical_drop:
                alerts.append(DriftAlert(
                    drift_type=DriftType.STRATEGY_PERFORMANCE,
                    severity=AlertSeverity.CRITICAL,
                    message=f"Strategy '{strategy}' Sharpe dropped {drop:.2f} ({baseline:.2f} -> {sharpe:.2f})",
                    metric_name=f"{strategy}_sharpe",
                    current_value=sharpe,
                    baseline_value=baseline,
                    threshold=self.thresholds.strategy_sharpe_critical_drop,
                    recovery_recommendations=[
                        f"Reduce weight for strategy '{strategy}' in selector",
                        "Investigate regime mismatch",
                        "Check for parameter decay",
                        "Consider strategy retirement if persistent",
                    ],
                ))
            elif drop >= self.thresholds.strategy_sharpe_warning_drop:
                alerts.append(DriftAlert(
                    drift_type=DriftType.STRATEGY_PERFORMANCE,
                    severity=AlertSeverity.WARNING,
                    message=f"Strategy '{strategy}' Sharpe dropped {drop:.2f}",
                    metric_name=f"{strategy}_sharpe",
                    current_value=sharpe,
                    baseline_value=baseline,
                    threshold=self.thresholds.strategy_sharpe_warning_drop,
                    recovery_recommendations=[
                        f"Monitor strategy '{strategy}' closely",
                        "Review recent trades for pattern changes",
                    ],
                ))

            # Check trend
            if perf.is_degrading(threshold=-0.01):
                alerts.append(DriftAlert(
                    drift_type=DriftType.STRATEGY_PERFORMANCE,
                    severity=AlertSeverity.WARNING,
                    message=f"Strategy '{strategy}' shows consistent Sharpe degradation trend",
                    metric_name=f"{strategy}_sharpe_trend",
                    current_value=perf.trend(),
                    baseline_value=0.0,
                    threshold=-0.01,
                    recovery_recommendations=[
                        f"Deep dive into '{strategy}' recent trades",
                        "Check for parameter sensitivity",
                    ],
                ))

        return alerts

    def _check_feature_drift(self, feature_stats: dict[str, float]) -> list[DriftAlert]:
        """Check feature distribution shifts using PSI."""
        alerts = []

        for feature, psi in feature_stats.items():
            if feature not in self._feature_distributions:
                self._feature_distributions[feature] = RollingMetrics(window_size=100)

            dist = self._feature_distributions[feature]
            dist.add(psi)

            if psi >= self.thresholds.feature_psi_critical:
                alerts.append(DriftAlert(
                    drift_type=DriftType.FEATURE_DISTRIBUTION,
                    severity=AlertSeverity.CRITICAL,
                    message=f"Feature '{feature}' distribution shifted critically (PSI={psi:.3f})",
                    metric_name=f"{feature}_psi",
                    current_value=psi,
                    baseline_value=0.0,
                    threshold=self.thresholds.feature_psi_critical,
                    recovery_recommendations=[
                        f"Retrain models with updated feature distributions",
                        f"Investigate data source changes for '{feature}'",
                        "Check for upstream data pipeline changes",
                        "Consider feature engineering adjustments",
                    ],
                ))
            elif psi >= self.thresholds.feature_psi_warning:
                alerts.append(DriftAlert(
                    drift_type=DriftType.FEATURE_DISTRIBUTION,
                    severity=AlertSeverity.WARNING,
                    message=f"Feature '{feature}' distribution shifting (PSI={psi:.3f})",
                    metric_name=f"{feature}_psi",
                    current_value=psi,
                    baseline_value=0.0,
                    threshold=self.thresholds.feature_psi_warning,
                    recovery_recommendations=[
                        f"Monitor feature '{feature}' closely",
                        "Prepare for potential retraining",
                    ],
                ))

        return alerts

    def _check_regime_shift(self, current_regime: str) -> Optional[DriftAlert]:
        """Check for unexpected market regime changes."""
        now = datetime.now(timezone.utc)
        self._regime_history.append({
            "regime": current_regime,
            "timestamp": now,
        })

        if self._last_regime == "UNKNOWN" or current_regime != self._last_regime:
            if self._last_regime != "UNKNOWN" and current_regime != self._last_regime:
                self._regime_stability_days = 0
            self._regime_start_time = now
        elif self._regime_start_time is not None:
            elapsed_days = int((now - self._regime_start_time).total_seconds() // 86400)
            self._regime_stability_days = max(self._regime_stability_days, elapsed_days)

        self._last_regime = current_regime

        # Alert if regime changes too frequently (instability)
        recent_changes = sum(
            1 for i in range(1, min(len(self._regime_history), 20))
            if self._regime_history[-i]["regime"] != self._regime_history[-i-1]["regime"]
        )

        if recent_changes >= 5:  # 5 changes in last 20 periods
            return DriftAlert(
                drift_type=DriftType.MARKET_REGIME_SHIFT,
                severity=AlertSeverity.WARNING,
                message=f"High regime instability: {recent_changes} changes in recent periods",
                metric_name="regime_changes",
                current_value=recent_changes,
                baseline_value=0.0,
                threshold=5,
                recovery_recommendations=[
                    "Reduce position sizes during regime uncertainty",
                    "Increase strategy diversification",
                    "Verify regime detection logic",
                    "Consider regime-agnostic strategies",
                ],
            )

        # Alert if stuck in adverse regime
        adverse_regimes = ["BEAR_TREND", "HIGH_VOLATILITY", "CRISIS"]
        if current_regime in adverse_regimes and self._regime_stability_days > self.thresholds.regime_shift_warning_days:
            return DriftAlert(
                drift_type=DriftType.MARKET_REGIME_SHIFT,
                severity=AlertSeverity.WARNING,
                message=f"Extended adverse regime: {current_regime} for {self._regime_stability_days} days",
                metric_name="adverse_regime_days",
                current_value=self._regime_stability_days,
                baseline_value=0.0,
                threshold=self.thresholds.regime_shift_warning_days,
                recovery_recommendations=[
                    "Activate defensive risk controls",
                    "Reduce leverage and position sizes",
                    "Focus on regime-appropriate strategies",
                ],
            )

        return None

    def _check_data_quality(self, quality_score: float) -> Optional[DriftAlert]:
        """Check data quality degradation."""
        self._data_quality.add(quality_score)

        if quality_score <= self.thresholds.data_quality_critical_score:
            return DriftAlert(
                drift_type=DriftType.DATA_QUALITY,
                severity=AlertSeverity.CRITICAL,
                message=f"Data quality critical: score={quality_score:.2f}",
                metric_name="data_quality",
                current_value=quality_score,
                baseline_value=1.0,
                threshold=self.thresholds.data_quality_critical_score,
                recovery_recommendations=[
                    "Investigate data source issues immediately",
                    "Check Binance API connectivity",
                    "Verify candle completeness and deduplication",
                    "Activate fallback data sources",
                    "Pause signal generation until resolved",
                ],
            )
        elif quality_score <= self.thresholds.data_quality_warning_score:
            return DriftAlert(
                drift_type=DriftType.DATA_QUALITY,
                severity=AlertSeverity.WARNING,
                message=f"Data quality degrading: score={quality_score:.2f}",
                metric_name="data_quality",
                current_value=quality_score,
                baseline_value=1.0,
                threshold=self.thresholds.data_quality_warning_score,
                recovery_recommendations=[
                    "Monitor data feeds closely",
                    "Check for missing candles or gaps",
                    "Verify timestamp synchronization",
                ],
            )

        return None

    def _check_system_resources(
        self,
        cpu_pct: Optional[float] = None,
        memory_pct: Optional[float] = None,
        disk_pct: Optional[float] = None,
    ) -> list[DriftAlert]:
        """Check system resource exhaustion across CPU, memory, and disk."""
        alerts: list[DriftAlert] = []

        if cpu_pct is not None:
            self._system_resources["cpu"].add(cpu_pct)
            if cpu_pct >= self.thresholds.cpu_critical_pct:
                alerts.append(DriftAlert(
                    drift_type=DriftType.SYSTEM_RESOURCES,
                    severity=AlertSeverity.CRITICAL,
                    message=f"CPU usage critical: {cpu_pct:.1f}%",
                    metric_name="cpu_usage",
                    current_value=cpu_pct,
                    baseline_value=0.0,
                    threshold=self.thresholds.cpu_critical_pct,
                    recovery_recommendations=[
                        "Reduce scanning frequency",
                        "Limit concurrent WebSocket connections",
                        "Disable non-critical ML inference",
                        "Consider restarting to clear memory leaks",
                    ],
                ))
            elif cpu_pct >= self.thresholds.cpu_warning_pct:
                alerts.append(DriftAlert(
                    drift_type=DriftType.SYSTEM_RESOURCES,
                    severity=AlertSeverity.WARNING,
                    message=f"CPU usage elevated: {cpu_pct:.1f}%",
                    metric_name="cpu_usage",
                    current_value=cpu_pct,
                    baseline_value=0.0,
                    threshold=self.thresholds.cpu_warning_pct,
                    recovery_recommendations=[
                        "Monitor CPU trends",
                        "Optimize indicator calculations",
                    ],
                ))

        if memory_pct is not None:
            self._system_resources["memory"].add(memory_pct)
            if memory_pct >= self.thresholds.memory_critical_pct:
                alerts.append(DriftAlert(
                    drift_type=DriftType.SYSTEM_RESOURCES,
                    severity=AlertSeverity.CRITICAL,
                    message=f"Memory usage critical: {memory_pct:.1f}%",
                    metric_name="memory_usage",
                    current_value=memory_pct,
                    baseline_value=0.0,
                    threshold=self.thresholds.memory_critical_pct,
                    recovery_recommendations=[
                        "Clear old candle data",
                        "Reduce cache sizes",
                        "Check for memory leaks",
                        "Restart if necessary",
                    ],
                ))
            elif memory_pct >= self.thresholds.memory_warning_pct:
                alerts.append(DriftAlert(
                    drift_type=DriftType.SYSTEM_RESOURCES,
                    severity=AlertSeverity.WARNING,
                    message=f"Memory usage elevated: {memory_pct:.1f}%",
                    metric_name="memory_usage",
                    current_value=memory_pct,
                    baseline_value=0.0,
                    threshold=self.thresholds.memory_warning_pct,
                    recovery_recommendations=[
                        "Monitor memory growth",
                        "Trim old cached candles",
                    ],
                ))

        if disk_pct is not None:
            self._system_resources["disk"].add(disk_pct)
            if disk_pct >= self.thresholds.disk_critical_pct:
                alerts.append(DriftAlert(
                    drift_type=DriftType.SYSTEM_RESOURCES,
                    severity=AlertSeverity.CRITICAL,
                    message=f"Disk usage critical: {disk_pct:.1f}%",
                    metric_name="disk_usage",
                    current_value=disk_pct,
                    baseline_value=0.0,
                    threshold=self.thresholds.disk_critical_pct,
                    recovery_recommendations=[
                        "Archive old data to backup",
                        "Clean log files",
                        "Remove old model checkpoints",
                        "Run database vacuum",
                    ],
                ))
            elif disk_pct >= self.thresholds.disk_warning_pct:
                alerts.append(DriftAlert(
                    drift_type=DriftType.SYSTEM_RESOURCES,
                    severity=AlertSeverity.WARNING,
                    message=f"Disk usage elevated: {disk_pct:.1f}%",
                    metric_name="disk_usage",
                    current_value=disk_pct,
                    baseline_value=0.0,
                    threshold=self.thresholds.disk_warning_pct,
                    recovery_recommendations=[
                        "Monitor disk usage",
                        "Clean old log files or checkpoints",
                    ],
                ))

        return alerts

    def get_recent_alerts(
        self,
        severity: Optional[AlertSeverity] = None,
        drift_type: Optional[DriftType] = None,
        hours: int = 24
    ) -> list[DriftAlert]:
        """Get recent alerts, optionally filtered."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        with self._lock:
            alerts = [a for a in self._alerts if a.timestamp >= cutoff]

            if severity:
                alerts = [a for a in alerts if a.severity == severity]
            if drift_type:
                alerts = [a for a in alerts if a.drift_type == drift_type]

            return sorted(alerts, key=lambda a: a.timestamp, reverse=True)

    def acknowledge_alert(self, alert: DriftAlert) -> None:
        """Mark an alert as acknowledged."""
        with self._lock:
            alert.acknowledged = True

    def get_status(self) -> dict[str, Any]:
        """Get current monitor status."""
        with self._lock:
            return {
                "baselines_established": self._baseline_established,
                "baselines": self._baselines.copy(),
                "recent_alerts_24h": len(self.get_recent_alerts(hours=24)),
                "critical_alerts_24h": len(self.get_recent_alerts(severity=AlertSeverity.CRITICAL, hours=24)),
                "warning_alerts_24h": len(self.get_recent_alerts(severity=AlertSeverity.WARNING, hours=24)),
                "last_check": self._last_check.isoformat(),
                "regime_stability_days": self._regime_stability_days,
                "current_regime": self._last_regime,
                "rolling_metrics": {
                    "prediction_accuracy_samples": len(self._prediction_accuracy.values),
                    "model_calibration_samples": len(self._model_calibration.values),
                    "strategies_tracked": len(self._strategy_performance),
                    "features_tracked": len(self._feature_distributions),
                },
            }

    def reset_baselines(self) -> None:
        """Reset all baselines (use after model retraining)."""
        with self._lock:
            self._baselines.clear()
            self._baseline_established = False
            self._prediction_accuracy.values.clear()
            self._model_calibration.values.clear()
            for perf in self._strategy_performance.values():
                perf.values.clear()
            for dist in self._feature_distributions.values():
                dist.values.clear()
            logger.info("Drift monitor baselines reset")