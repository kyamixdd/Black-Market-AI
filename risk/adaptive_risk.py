"""Adaptive Risk Intelligence: independent risk monitoring and dynamic risk reduction."""
from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from config import (
    MAX_SPOT_POSITIONS,
    MAX_FUTURES_POSITIONS,
    RISK_MAX_DAILY_LOSS_PCT,
    RISK_MAX_LEVERAGE,
    RISK_MAX_TOTAL_OPEN_PCT,
    RISK_PER_TRADE_PCT,
)

logger = logging.getLogger(__name__)


class RiskAction(Enum):
    """Actions the adaptive risk engine can take."""
    NONE = "NONE"
    REDUCE_POSITION_SIZE = "REDUCE_POSITION_SIZE"
    REDUCE_MAX_POSITIONS = "REDUCE_MAX_POSITIONS"
    REDUCE_LEVERAGE = "REDUCE_LEVERAGE"
    PAUSE_NEW_ENTRIES = "PAUSE_NEW_ENTRIES"
    ACTIVATE_COOLDOWN = "ACTIVATE_COOLDOWN"
    REDUCE_DAILY_LOSS_LIMIT = "REDUCE_DAILY_LOSS_LIMIT"
    CLOSE_RISKIEST_POSITIONS = "CLOSE_RISKIEST_POSITIONS"


class RiskLevel(Enum):
    """Current risk level assessment."""
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass
class RiskThresholds:
    """Configurable thresholds for each risk factor."""
    # Volatility (ATR-based)
    volatility_warning_pct: float = 2.0  # 2% daily ATR
    volatility_critical_pct: float = 5.0

    # Portfolio drawdown
    drawdown_warning_pct: float = 5.0
    drawdown_critical_pct: float = 10.0

    # Consecutive losses
    consecutive_losses_warning: int = 3
    consecutive_losses_critical: int = 5

    # Correlation exposure (max % in correlated assets)
    correlation_warning_pct: float = 60.0
    correlation_critical_pct: float = 80.0

    # Asset concentration (max % in single asset)
    concentration_warning_pct: float = 20.0
    concentration_critical_pct: float = 35.0

    # Funding risk (for futures)
    funding_warning_pct: float = 0.05  # 5% of balance per funding period
    funding_critical_pct: float = 0.10

    # Liquidation distance (for futures)
    liquidation_distance_warning_pct: float = 20.0  # 20% from liq price
    liquidation_distance_critical_pct: float = 10.0

    # Daily loss (relative to admin limit)
    daily_loss_warning_pct: float = 0.5  # 50% of admin limit
    daily_loss_critical_pct: float = 0.8  # 80% of admin limit

    # Data quality
    data_quality_warning_score: float = 0.7  # 70% health
    data_quality_critical_score: float = 0.4

    # System health
    system_health_warning_score: float = 0.7
    system_health_critical_score: float = 0.4


@dataclass
class RiskFactor:
    """Individual risk factor assessment."""
    name: str
    current_value: Optional[float]
    warning_threshold: float
    critical_threshold: float
    level: RiskLevel
    message: str
    basis: Optional[str] = None


@dataclass
class RiskAssessment:
    """Complete risk assessment result."""
    timestamp: datetime
    overall_level: RiskLevel
    factors: list[RiskFactor]
    actions: list[RiskAction]
    cooldown_until: Optional[datetime] = None
    risk_budget_used_pct: float = 0.0
    unavailable_factors: list[str] = field(default_factory=list)


class AdaptiveRiskEngine:
    """
    Independent adaptive risk engine.

    Monitors 10 risk factors and can:
    - Reduce position sizes
    - Reduce max positions
    - Reduce leverage
    - Pause new entries
    - Activate cooldown
    - Reduce daily loss limit
    - Close riskiest positions

    NEVER increases risk limits beyond admin-configured maximums.
    """

    def __init__(
        self,
        thresholds: Optional[RiskThresholds] = None,
        admin_max_risk_per_trade: float = RISK_PER_TRADE_PCT,
        admin_max_daily_loss: float = RISK_MAX_DAILY_LOSS_PCT,
        admin_max_total_open: float = RISK_MAX_TOTAL_OPEN_PCT,
        admin_max_leverage: float = RISK_MAX_LEVERAGE,
        admin_max_spot_positions: int = MAX_SPOT_POSITIONS,
        admin_max_futures_positions: int = MAX_FUTURES_POSITIONS,
    ):
        self.thresholds = thresholds or RiskThresholds()

        # Admin-configured maximums (IMMUTABLE - can only reduce from these)
        self._admin_max_risk_per_trade = admin_max_risk_per_trade
        self._admin_max_daily_loss = admin_max_daily_loss
        self._admin_max_total_open = admin_max_total_open
        self._admin_max_leverage = admin_max_leverage
        self._admin_max_spot_positions = admin_max_spot_positions
        self._admin_max_futures_positions = admin_max_futures_positions

        # Current effective limits (can be reduced by adaptive engine)
        self._effective_risk_per_trade = admin_max_risk_per_trade
        self._effective_daily_loss = admin_max_daily_loss
        self._effective_total_open = admin_max_total_open
        self._effective_leverage = admin_max_leverage
        self._effective_max_spot_positions = admin_max_spot_positions
        self._effective_max_futures_positions = admin_max_futures_positions

        # State
        self._consecutive_losses = 0
        self._cooldown_until: Optional[datetime] = None
        self._paused = False
        self._lock = threading.RLock()

        # History for trend analysis
        self._risk_history: list[RiskAssessment] = []
        self._max_history = 100
        self.close_riskiest_callback: Any = None

    @property
    def effective_risk_per_trade(self) -> float:
        return self._effective_risk_per_trade

    @property
    def effective_daily_loss_limit(self) -> float:
        return self._effective_daily_loss

    @property
    def effective_total_open_limit(self) -> float:
        return self._effective_total_open

    @property
    def effective_leverage(self) -> float:
        return self._effective_leverage

    @property
    def effective_max_spot_positions(self) -> int:
        return self._effective_max_spot_positions

    @property
    def effective_max_futures_positions(self) -> int:
        return self._effective_max_futures_positions

    def _sync_cooldown_locked(self) -> None:
        """Clear expired cooldown and its pause flag (caller must hold self._lock)."""
        if self._cooldown_until is not None and datetime.now(timezone.utc) >= self._cooldown_until:
            self._cooldown_until = None
            self._paused = False
            logger.info("Cooldown expired; entries unpaused")

    @property
    def is_paused(self) -> bool:
        with self._lock:
            self._sync_cooldown_locked()
            return self._paused

    @property
    def cooldown_remaining_seconds(self) -> float:
        if self._cooldown_until:
            remaining = (self._cooldown_until - datetime.now(timezone.utc)).total_seconds()
            return max(0, remaining)
        return 0

    def assess_risk(
        self,
        portfolio_value: float,
        daily_pnl: float,
        open_positions: dict[str, Any],
        current_volatility: Optional[dict[str, float]],  # symbol -> ATR %
        correlation_matrix: Optional[dict] = None,
        data_quality_score: Optional[float] = None,
        system_health_score: Optional[float] = None,
        *,
        asset_returns: Optional[Mapping[str, Sequence[tuple[datetime, float]]]] = None,
        equity_high_water_mark: Optional[float] = None,
        equity_high_water_mark_since: Optional[datetime] = None,
    ) -> RiskAssessment:
        """
        Perform complete risk assessment.

        Args:
            portfolio_value: Total portfolio value (spot + futures)
            daily_pnl: Current daily P&L
            open_positions: Dict of open positions with symbol, market, side, size, entry, current, liq_price
            current_volatility: Symbol -> current ATR as % of price
            correlation_matrix: Deprecated; a matrix alone is not validated evidence.
            data_quality_score: Optional 0-1 score from DataIntegrityGuardian
            system_health_score: Optional 0-1 score from HealthMonitor
            asset_returns: Per-symbol ordered (UTC timestamp, return) observations.
            equity_high_water_mark: Persisted all-time equity high including this observation.
            equity_high_water_mark_since: UTC time when that high-water tracking began.

        Returns:
            RiskAssessment with level, factors, and recommended actions
        """
        with self._lock:
            self._sync_cooldown_locked()
            factors = []

            # 1. Current volatility
            volatility_values = list((current_volatility or {}).values())
            if volatility_values and all(
                math.isfinite(value) and value >= 0 for value in volatility_values
            ):
                avg_vol = sum(volatility_values) / len(volatility_values)
                factors.append(self._assess_factor(
                    "volatility", avg_vol,
                    self.thresholds.volatility_warning_pct,
                    self.thresholds.volatility_critical_pct,
                    higher_is_worse=True
                ))
            else:
                factors.append(self._unavailable_factor(
                    "volatility",
                    self.thresholds.volatility_warning_pct,
                    self.thresholds.volatility_critical_pct,
                    "validated volatility observations are unavailable",
                ))

            # 2. Portfolio drawdown
            drawdown_pct = self._calculate_drawdown(
                portfolio_value,
                equity_high_water_mark,
                equity_high_water_mark_since,
            )
            if drawdown_pct is None:
                factors.append(self._unavailable_factor(
                    "drawdown",
                    self.thresholds.drawdown_warning_pct,
                    self.thresholds.drawdown_critical_pct,
                    "persisted all-time equity high-water mark and tracking start are required",
                ))
            else:
                factors.append(self._assess_factor(
                    "drawdown", drawdown_pct,
                    self.thresholds.drawdown_warning_pct,
                    self.thresholds.drawdown_critical_pct,
                    higher_is_worse=True,
                    basis=f"all-time high-water mark since {equity_high_water_mark_since.isoformat()}",
                ))

            # 3. Consecutive losses
            factors.append(self._assess_factor(
                "consecutive_losses", float(self._consecutive_losses),
                self.thresholds.consecutive_losses_warning,
                self.thresholds.consecutive_losses_critical,
                higher_is_worse=True
            ))

            # 4. Correlation exposure
            corr_exposure = self._calculate_correlation_exposure(
                open_positions, asset_returns, portfolio_value
            )
            if corr_exposure is None:
                reason = (
                    "a supplied correlation matrix is not a substitute for validated aligned returns"
                    if correlation_matrix is not None and asset_returns is None
                    else "validated aligned return series are unavailable or insufficient"
                )
                factors.append(self._unavailable_factor(
                    "correlation",
                    self.thresholds.correlation_warning_pct,
                    self.thresholds.correlation_critical_pct,
                    reason,
                ))
            else:
                factors.append(self._assess_factor(
                    "correlation", corr_exposure,
                    self.thresholds.correlation_warning_pct,
                    self.thresholds.correlation_critical_pct,
                    higher_is_worse=True,
                    basis="gross notional in positive-correlation clusters / portfolio value",
                ))

            # 5. Asset concentration
            conc_exposure = self._calculate_concentration(open_positions, portfolio_value)
            if conc_exposure is None:
                factors.append(self._unavailable_factor(
                    "concentration",
                    self.thresholds.concentration_warning_pct,
                    self.thresholds.concentration_critical_pct,
                    "valid portfolio value and position notionals are required",
                ))
            else:
                factors.append(self._assess_factor(
                    "concentration", conc_exposure,
                    self.thresholds.concentration_warning_pct,
                    self.thresholds.concentration_critical_pct,
                    higher_is_worse=True
                ))

            # 6. Funding risk (futures only)
            funding_risk = self._calculate_funding_risk(open_positions, portfolio_value)
            if funding_risk is None:
                factors.append(self._unavailable_factor(
                    "funding",
                    self.thresholds.funding_warning_pct,
                    self.thresholds.funding_critical_pct,
                    "valid portfolio value is required to assess futures funding exposure",
                ))
            else:
                factors.append(self._assess_factor(
                    "funding", funding_risk,
                    self.thresholds.funding_warning_pct,
                    self.thresholds.funding_critical_pct,
                    higher_is_worse=True
                ))

            # 7. Liquidation distance
            liq_distance = self._calculate_liquidation_distance(open_positions)
            if liq_distance is None:
                factors.append(self._not_applicable_factor(
                    "liquidation",
                    self.thresholds.liquidation_distance_warning_pct,
                    self.thresholds.liquidation_distance_critical_pct,
                    "no open Futures positions",
                ))
            elif not math.isfinite(liq_distance):
                factors.append(self._unavailable_factor(
                    "liquidation",
                    self.thresholds.liquidation_distance_warning_pct,
                    self.thresholds.liquidation_distance_critical_pct,
                    "valid current and liquidation prices are required for every Futures position",
                ))
            else:
                factors.append(self._assess_factor(
                    "liquidation", liq_distance,
                    self.thresholds.liquidation_distance_warning_pct,
                    self.thresholds.liquidation_distance_critical_pct,
                    higher_is_worse=False  # Lower distance = worse
                ))

            # 8. Daily loss (only when P&L is negative)
            if (
                math.isfinite(portfolio_value) and portfolio_value > 0
                and math.isfinite(daily_pnl) and self._admin_max_daily_loss > 0
            ):
                daily_loss_pct = max(0.0, -daily_pnl) / portfolio_value * 100
                daily_loss_ratio = daily_loss_pct / self._admin_max_daily_loss
                factors.append(self._assess_factor(
                    "daily_loss", daily_loss_ratio * 100,
                    self.thresholds.daily_loss_warning_pct * 100,
                    self.thresholds.daily_loss_critical_pct * 100,
                    higher_is_worse=True
                ))
            else:
                factors.append(self._unavailable_factor(
                    "daily_loss",
                    self.thresholds.daily_loss_warning_pct * 100,
                    self.thresholds.daily_loss_critical_pct * 100,
                    "valid portfolio value, daily P&L, and configured daily-loss limit are required",
                ))

            # 9. Data quality
            if self._valid_unit_score(data_quality_score):
                factors.append(self._assess_factor(
                    "data_quality", data_quality_score * 100,
                    self.thresholds.data_quality_warning_score * 100,
                    self.thresholds.data_quality_critical_score * 100,
                    higher_is_worse=False  # Lower score = worse
                ))
            else:
                factors.append(self._unavailable_factor(
                    "data_quality",
                    self.thresholds.data_quality_warning_score * 100,
                    self.thresholds.data_quality_critical_score * 100,
                    "validated data-quality score is unavailable",
                ))

            # 10. System health
            if self._valid_unit_score(system_health_score):
                factors.append(self._assess_factor(
                    "system_health", system_health_score * 100,
                    self.thresholds.system_health_warning_score * 100,
                    self.thresholds.system_health_critical_score * 100,
                    higher_is_worse=False
                ))
            else:
                factors.append(self._unavailable_factor(
                    "system_health",
                    self.thresholds.system_health_warning_score * 100,
                    self.thresholds.system_health_critical_score * 100,
                    "validated system-health score is unavailable",
                ))

            # Determine overall level
            levels = [f.level for f in factors if f.level not in {
                RiskLevel.UNAVAILABLE, RiskLevel.NOT_APPLICABLE,
            }]
            if RiskLevel.CRITICAL in levels:
                overall = RiskLevel.CRITICAL
            elif RiskLevel.HIGH in levels:
                overall = RiskLevel.HIGH
            elif RiskLevel.ELEVATED in levels:
                overall = RiskLevel.ELEVATED
            elif any(f.level == RiskLevel.UNAVAILABLE for f in factors):
                overall = RiskLevel.UNAVAILABLE
            else:
                overall = RiskLevel.NORMAL

            # Determine actions
            actions = self._determine_actions(overall, factors)

            # Calculate risk budget used
            risk_budget = self._calculate_risk_budget(open_positions, portfolio_value)

            assessment = RiskAssessment(
                timestamp=datetime.now(timezone.utc),
                overall_level=overall,
                factors=factors,
                actions=actions,
                cooldown_until=self._cooldown_until,
                risk_budget_used_pct=risk_budget,
                unavailable_factors=[f.name for f in factors if f.level == RiskLevel.UNAVAILABLE],
            )

            # Apply automatic actions
            self._apply_actions(actions, assessment)

            # Store history
            self._risk_history.append(assessment)
            if len(self._risk_history) > self._max_history:
                self._risk_history.pop(0)

            logger.info(f"Risk assessment: {overall.value}, actions: {[a.value for a in actions]}")
            return assessment

    def _assess_factor(
        self,
        name: str,
        value: float,
        warning: float,
        critical: float,
        higher_is_worse: bool = True,
        basis: Optional[str] = None,
    ) -> RiskFactor:
        """Assess a single risk factor."""
        if higher_is_worse:
            # Higher value = worse (e.g., volatility, drawdown)
            if value >= critical:
                level = RiskLevel.CRITICAL
                msg = f"{name}={value:.2f} exceeds critical threshold {critical}"
            elif value >= warning:
                level = RiskLevel.HIGH
                msg = f"{name}={value:.2f} exceeds warning threshold {warning}"
            elif value >= warning * 0.5:
                level = RiskLevel.ELEVATED
                msg = f"{name}={value:.2f} approaching warning threshold {warning}"
            else:
                level = RiskLevel.NORMAL
                msg = f"{name}={value:.2f} within normal range"
        else:  # Lower value = worse (higher is better, e.g., data quality, system health)
            if value <= critical:
                level = RiskLevel.CRITICAL
                msg = f"{name}={value:.2f} below critical threshold {critical}"
            elif value <= warning:
                level = RiskLevel.HIGH
                msg = f"{name}={value:.2f} below warning threshold {warning}"
            elif value < warning * 1.2:
                # Between warning and 1.2*warning: "approaching warning from above"
                level = RiskLevel.ELEVATED
                msg = f"{name}={value:.2f} above warning but within approach zone"
            else:
                level = RiskLevel.NORMAL
                msg = f"{name}={value:.2f} well above warning threshold {warning}"

        return RiskFactor(
            name=name,
            current_value=value,
            warning_threshold=warning,
            critical_threshold=critical,
            level=level,
            message=msg,
            basis=basis,
        )

    @staticmethod
    def _valid_unit_score(value: Optional[float]) -> bool:
        return value is not None and math.isfinite(value) and 0 <= value <= 1

    @staticmethod
    def _unavailable_factor(
        name: str,
        warning: float,
        critical: float,
        reason: str,
    ) -> RiskFactor:
        return RiskFactor(
            name=name,
            current_value=None,
            warning_threshold=warning,
            critical_threshold=critical,
            level=RiskLevel.UNAVAILABLE,
            message=f"{name} unavailable: {reason}",
        )

    @staticmethod
    def _not_applicable_factor(
        name: str,
        warning: float,
        critical: float,
        reason: str,
    ) -> RiskFactor:
        return RiskFactor(
            name=name,
            current_value=None,
            warning_threshold=warning,
            critical_threshold=critical,
            level=RiskLevel.NOT_APPLICABLE,
            message=f"{name} not applicable: {reason}",
        )

    @staticmethod
    def _calculate_drawdown(
        portfolio_value: float,
        high_water_mark: Optional[float],
        high_water_mark_since: Optional[datetime],
    ) -> Optional[float]:
        """Calculate drawdown from a persisted all-time high-water mark."""
        if (
            not math.isfinite(portfolio_value) or portfolio_value <= 0
            or high_water_mark is None or not math.isfinite(high_water_mark)
            or high_water_mark <= 0 or high_water_mark < portfolio_value
            or high_water_mark_since is None or high_water_mark_since.tzinfo is None
            or high_water_mark_since.utcoffset() is None
            or high_water_mark_since > datetime.now(timezone.utc)
        ):
            return None
        return max(0.0, (high_water_mark - portfolio_value) / high_water_mark * 100)

    def _calculate_correlation_exposure(
        self,
        positions: dict[str, Any],
        asset_returns: Optional[Mapping[str, Sequence[tuple[datetime, float]]]],
        portfolio_value: float,
    ) -> Optional[float]:
        """Calculate gross notional in positively correlated clusters as % of equity."""
        if not positions:
            return 0.0
        if not math.isfinite(portfolio_value) or portfolio_value <= 0:
            return None

        notionals: dict[str, float] = {}
        for key, position in positions.items():
            symbol = str(position.get("symbol") or key).upper()
            amount = position.get("amount")
            price = position.get("current_price", position.get("entry_price"))
            if (
                not symbol or amount is None or price is None
                or not math.isfinite(amount) or not math.isfinite(price)
                or amount < 0 or price <= 0
            ):
                return None
            notionals[symbol] = notionals.get(symbol, 0.0) + amount * price

        symbols = sorted(symbol for symbol, notional in notionals.items() if notional > 0)
        if len(symbols) < 2:
            return 0.0
        if asset_returns is None:
            return None

        normalized_returns: dict[str, dict[datetime, float]] = {}
        for symbol in symbols:
            series = asset_returns.get(symbol)
            if series is None:
                series = asset_returns.get(symbol.lower())
            if series is None or len(series) < 30:
                return None
            observations: dict[datetime, float] = {}
            previous: Optional[datetime] = None
            for timestamp, value in series:
                if (
                    not isinstance(timestamp, datetime)
                    or timestamp.tzinfo is None or timestamp.utcoffset() is None
                    or not math.isfinite(value)
                ):
                    return None
                timestamp = timestamp.astimezone(timezone.utc)
                if previous is not None and timestamp <= previous:
                    return None
                observations[timestamp] = value
                previous = timestamp
            normalized_returns[symbol] = observations

        aligned_times = set.intersection(
            *(set(observations) for observations in normalized_returns.values())
        )
        if len(aligned_times) < 30:
            return None
        ordered_times = sorted(aligned_times)
        values = {
            symbol: [observations[timestamp] for timestamp in ordered_times]
            for symbol, observations in normalized_returns.items()
        }

        adjacency = {symbol: set() for symbol in symbols}
        for index, left in enumerate(symbols):
            for right in symbols[index + 1:]:
                correlation = self._pearson_correlation(values[left], values[right])
                if correlation is None:
                    return None
                if correlation >= 0.7:
                    adjacency[left].add(right)
                    adjacency[right].add(left)

        largest_cluster_notional = 0.0
        remaining = set(symbols)
        while remaining:
            start = remaining.pop()
            cluster = {start}
            stack = [start]
            while stack:
                current = stack.pop()
                for neighbor in adjacency[current] & remaining:
                    remaining.remove(neighbor)
                    cluster.add(neighbor)
                    stack.append(neighbor)
            if len(cluster) > 1:
                largest_cluster_notional = max(
                    largest_cluster_notional,
                    sum(notionals[symbol] for symbol in cluster),
                )
        return largest_cluster_notional / portfolio_value * 100

    @staticmethod
    def _pearson_correlation(left: Sequence[float], right: Sequence[float]) -> Optional[float]:
        """Return Pearson correlation, or None when either return series is constant."""
        if len(left) != len(right) or len(left) < 2:
            return None
        left_mean = sum(left) / len(left)
        right_mean = sum(right) / len(right)
        left_delta = [value - left_mean for value in left]
        right_delta = [value - right_mean for value in right]
        left_variance = sum(value * value for value in left_delta)
        right_variance = sum(value * value for value in right_delta)
        denominator = math.sqrt(left_variance * right_variance)
        if denominator <= 0 or not math.isfinite(denominator):
            return None
        return sum(a * b for a, b in zip(left_delta, right_delta)) / denominator

    def _calculate_concentration(
        self,
        positions: dict[str, Any],
        portfolio_value: float
    ) -> Optional[float]:
        """Calculate max single-asset concentration."""
        if not positions:
            return 0.0
        if not math.isfinite(portfolio_value) or portfolio_value <= 0:
            return None

        exposure_by_asset: dict[str, float] = {}
        for key, position in positions.items():
            amount = position.get("amount")
            price = position.get("current_price", position.get("entry_price"))
            if (
                amount is None or price is None
                or not math.isfinite(amount) or not math.isfinite(price)
                or amount < 0 or price <= 0
            ):
                return None
            symbol = str(position.get("symbol") or key).upper()
            exposure_by_asset[symbol] = exposure_by_asset.get(symbol, 0.0) + amount * price
        return max(exposure_by_asset.values(), default=0.0) / portfolio_value * 100

    def _calculate_funding_risk(
        self,
        positions: dict[str, Any],
        portfolio_value: float
    ) -> Optional[float]:
        """Calculate funding payment risk as % of portfolio."""
        futures_positions = [pos for pos in positions.values() if pos.get("market") == "FUTURES"]
        if not futures_positions:
            return 0.0
        if not math.isfinite(portfolio_value) or portfolio_value <= 0:
            return None

        total_funding = 0.0
        for pos in futures_positions:
            amount = pos.get("amount")
            price = pos.get("current_price", pos.get("entry_price"))
            leverage = pos.get("leverage", 1)
            if (
                amount is None or price is None or leverage is None
                or not math.isfinite(amount) or not math.isfinite(price)
                or not math.isfinite(leverage) or amount < 0 or price <= 0 or leverage < 1
            ):
                return None
            notional = abs(amount * price)
            # Funding is charged on notional, not multiplied by leverage again.
            total_funding += notional * 0.0001

        return (total_funding / portfolio_value) * 100

    def _calculate_liquidation_distance(
        self,
        positions: dict[str, Any]
    ) -> Optional[float]:
        """Calculate minimum distance to liquidation across futures positions."""
        futures_positions = [pos for pos in positions.values() if pos.get("market") == "FUTURES"]
        if not futures_positions:
            return None
        min_distance = math.inf

        for pos in futures_positions:
            current = pos.get("current_price")
            liquidation = pos.get("liq_price")
            side = str(pos.get("side", "")).upper()
            if (
                current is None or liquidation is None
                or not math.isfinite(current) or not math.isfinite(liquidation)
                or current <= 0 or liquidation <= 0 or side not in {"LONG", "SHORT"}
            ):
                return math.nan
            if side == "LONG":
                distance_pct = (current - liquidation) / current * 100
            else:
                distance_pct = (liquidation - current) / current * 100
            min_distance = min(min_distance, max(0.0, distance_pct))

        return min_distance

    def _determine_actions(
        self,
        overall: RiskLevel,
        factors: list[RiskFactor]
    ) -> list[RiskAction]:
        """Determine risk mitigation actions based on assessment."""
        actions = []

        critical_factors = [f for f in factors if f.level == RiskLevel.CRITICAL]
        high_factors = [f for f in factors if f.level == RiskLevel.HIGH]
        elevated_factors = [f for f in factors if f.level == RiskLevel.ELEVATED]

        factor_names = {f.name for f in critical_factors + high_factors}

        if overall == RiskLevel.CRITICAL:
            # Maximum protection
            actions.extend([
                RiskAction.PAUSE_NEW_ENTRIES,
                RiskAction.ACTIVATE_COOLDOWN,
                RiskAction.REDUCE_POSITION_SIZE,
                RiskAction.REDUCE_MAX_POSITIONS,
                RiskAction.REDUCE_LEVERAGE,
            ])
            if "daily_loss" in factor_names:
                actions.append(RiskAction.REDUCE_DAILY_LOSS_LIMIT)
            if "liquidation" in factor_names:
                actions.append(RiskAction.CLOSE_RISKIEST_POSITIONS)

        elif overall == RiskLevel.HIGH:
            # Strong protection
            actions.extend([
                RiskAction.REDUCE_POSITION_SIZE,
                RiskAction.REDUCE_MAX_POSITIONS,
                RiskAction.REDUCE_LEVERAGE,
            ])
            if "daily_loss" in factor_names:
                actions.append(RiskAction.REDUCE_DAILY_LOSS_LIMIT)
            if "consecutive_losses" in factor_names:
                actions.append(RiskAction.PAUSE_NEW_ENTRIES)

        elif overall == RiskLevel.ELEVATED:
            # Moderate protection
            actions.extend([
                RiskAction.REDUCE_POSITION_SIZE,
                RiskAction.REDUCE_LEVERAGE,
            ])

        return list(set(actions))  # Deduplicate

    def _calculate_risk_budget(self, positions: dict[str, Any], portfolio_value: float) -> float:
        """Calculate % of risk budget currently used."""
        if portfolio_value <= 0:
            return 0.0

        total_risk = 0.0
        for pos in positions.values():
            entry = pos.get("entry_price", 0)
            sl = pos.get("stop_loss", 0)
            amount = pos.get("amount", 0)
            if entry > 0 and sl > 0 and amount > 0:
                risk_per_unit = abs(entry - sl)
                total_risk += risk_per_unit * amount

        return (total_risk / portfolio_value) * 100 if portfolio_value > 0 else 0

    def _apply_actions(self, actions: list[RiskAction], assessment: RiskAssessment) -> None:
        """Apply risk mitigation actions (reduce effective limits)."""
        if assessment.overall_level == RiskLevel.NORMAL and not actions:
            self._restore_limits()
            if self._cooldown_until is None:
                self._paused = False
            return
        if not actions:
            return

        # Reduce position size (risk per trade)
        if RiskAction.REDUCE_POSITION_SIZE in actions:
            reduction = 0.5 if assessment.overall_level == RiskLevel.CRITICAL else 0.7
            self._effective_risk_per_trade = max(
                self._admin_max_risk_per_trade * reduction,
                0.1  # Floor at 0.1%
            )
            logger.warning(f"Reduced risk per trade to {self._effective_risk_per_trade}%")

        # Reduce max positions
        if RiskAction.REDUCE_MAX_POSITIONS in actions:
            reduction = 0.5 if assessment.overall_level == RiskLevel.CRITICAL else 0.7
            self._effective_max_spot_positions = max(
                int(self._admin_max_spot_positions * reduction),
                1
            )
            self._effective_max_futures_positions = max(
                int(self._admin_max_futures_positions * reduction),
                1
            )
            logger.warning(f"Reduced max positions: spot={self._effective_max_spot_positions}, "
                         f"futures={self._effective_max_futures_positions}")

        # Reduce leverage
        if RiskAction.REDUCE_LEVERAGE in actions:
            reduction = 0.5 if assessment.overall_level == RiskLevel.CRITICAL else 0.7
            self._effective_leverage = max(
                self._admin_max_leverage * reduction,
                1.0
            )
            logger.warning(f"Reduced max leverage to {self._effective_leverage}x")

        # Pause new entries
        if RiskAction.PAUSE_NEW_ENTRIES in actions:
            self._paused = True
            logger.warning("PAUSED new position entries")

        # Activate cooldown
        if RiskAction.ACTIVATE_COOLDOWN in actions:
            cooldown_hours = 4 if assessment.overall_level == RiskLevel.CRITICAL else 2
            self._cooldown_until = datetime.now(timezone.utc) + timedelta(hours=cooldown_hours)
            self._paused = True
            logger.warning(f"Activated cooldown until {self._cooldown_until}")

        # Reduce daily loss limit
        if RiskAction.REDUCE_DAILY_LOSS_LIMIT in actions:
            reduction = 0.5 if assessment.overall_level == RiskLevel.CRITICAL else 0.7
            self._effective_daily_loss = self._admin_max_daily_loss * reduction
            logger.warning(f"Reduced daily loss limit to {self._effective_daily_loss}%")

        # Close riskiest positions via registered simulator callback
        if RiskAction.CLOSE_RISKIEST_POSITIONS in actions:
            if callable(self.close_riskiest_callback):
                try:
                    self.close_riskiest_callback()
                except Exception:
                    logger.exception("CLOSE_RISKIEST_POSITIONS callback failed")
            else:
                logger.critical("CLOSE_RISKIEST_POSITIONS action triggered - no simulator callback registered")

    def record_trade_result(self, pnl: float) -> None:
        """Record trade result for consecutive loss tracking."""
        with self._lock:
            if pnl < 0:
                self._consecutive_losses += 1
            else:
                self._consecutive_losses = 0

    def reset_cooldown(self) -> None:
        """Manually reset cooldown (admin action)."""
        with self._lock:
            self._cooldown_until = None
            self._paused = False
            # Restore limits to admin maximums
            self._restore_limits()
            logger.info("Cooldown reset, limits restored to admin maximums")

    def _restore_limits(self) -> None:
        """Restore all effective limits to admin maximums."""
        self._effective_risk_per_trade = self._admin_max_risk_per_trade
        self._effective_daily_loss = self._admin_max_daily_loss
        self._effective_total_open = self._admin_max_total_open
        self._effective_leverage = self._admin_max_leverage
        self._effective_max_spot_positions = self._admin_max_spot_positions
        self._effective_max_futures_positions = self._admin_max_futures_positions

    def get_status(self) -> dict[str, Any]:
        """Get current risk engine status."""
        with self._lock:
            self._sync_cooldown_locked()
            return {
                "paused": self._paused,
                "cooldown_until": self._cooldown_until.isoformat() if self._cooldown_until else None,
                "cooldown_remaining_seconds": self.cooldown_remaining_seconds,
                "consecutive_losses": self._consecutive_losses,
                "effective_limits": {
                    "risk_per_trade_pct": self._effective_risk_per_trade,
                    "daily_loss_pct": self._effective_daily_loss,
                    "total_open_pct": self._effective_total_open,
                    "max_leverage": self._effective_leverage,
                    "max_spot_positions": self._effective_max_spot_positions,
                    "max_futures_positions": self._effective_max_futures_positions,
                },
                "admin_maximums": {
                    "risk_per_trade_pct": self._admin_max_risk_per_trade,
                    "daily_loss_pct": self._admin_max_daily_loss,
                    "total_open_pct": self._admin_max_total_open,
                    "max_leverage": self._admin_max_leverage,
                    "max_spot_positions": self._admin_max_spot_positions,
                    "max_futures_positions": self._admin_max_futures_positions,
                },
                "reduction_active": (
                    self._effective_risk_per_trade < self._admin_max_risk_per_trade or
                    self._effective_daily_loss < self._admin_max_daily_loss or
                    self._effective_leverage < self._admin_max_leverage
                ),
            }

    def can_open_position(self, market: str, current_positions: int) -> tuple[bool, str]:
        """Check if a new position can be opened."""
        with self._lock:
            self._sync_cooldown_locked()
            if self._paused:
                if self._cooldown_until:
                    return False, f"Cooldown active until {self._cooldown_until}"
                return False, "New entries paused by risk engine"

            max_pos = self._effective_max_spot_positions if market == "SPOT" else self._effective_max_futures_positions
            if current_positions >= max_pos:
                return False, f"Max {market} positions reached ({max_pos})"

            return True, "OK"

    def get_effective_risk_per_trade(self) -> float:
        """Get current effective risk per trade (for position sizing)."""
        with self._lock:
            return self._effective_risk_per_trade

    def get_effective_leverage(self, market: str, requested: float) -> float:
        """Get effective leverage cap for a position."""
        with self._lock:
            if market == "FUTURES":
                return min(requested, self._effective_leverage)
            return 1.0