"""Adaptive Risk Intelligence: independent risk monitoring and dynamic risk reduction."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Optional

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
    current_value: float
    warning_threshold: float
    critical_threshold: float
    level: RiskLevel
    message: str


@dataclass
class RiskAssessment:
    """Complete risk assessment result."""
    timestamp: datetime
    overall_level: RiskLevel
    factors: list[RiskFactor]
    actions: list[RiskAction]
    cooldown_until: Optional[datetime] = None
    risk_budget_used_pct: float = 0.0


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

    @property
    def is_paused(self) -> bool:
        with self._lock:
            if self._cooldown_until and datetime.now(timezone.utc) < self._cooldown_until:
                return True
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
        current_volatility: dict[str, float],  # symbol -> ATR %
        correlation_matrix: Optional[dict] = None,
        data_quality_score: float = 1.0,
        system_health_score: float = 1.0,
    ) -> RiskAssessment:
        """
        Perform complete risk assessment.

        Args:
            portfolio_value: Total portfolio value (spot + futures)
            daily_pnl: Current daily P&L
            open_positions: Dict of open positions with symbol, market, side, size, entry, current, liq_price
            current_volatility: Symbol -> current ATR as % of price
            correlation_matrix: Optional correlation data
            data_quality_score: 0-1 score from DataIntegrityGuardian
            system_health_score: 0-1 score from HealthMonitor

        Returns:
            RiskAssessment with level, factors, and recommended actions
        """
        with self._lock:
            factors = []

            # 1. Current volatility
            avg_vol = sum(current_volatility.values()) / len(current_volatility) if current_volatility else 0
            factors.append(self._assess_factor(
                "volatility", avg_vol,
                self.thresholds.volatility_warning_pct,
                self.thresholds.volatility_critical_pct,
                higher_is_worse=True
            ))

            # 2. Portfolio drawdown
            # Calculate from peak (would need historical tracking in production)
            # For now, use a simplified measure
            drawdown_pct = self._calculate_drawdown(portfolio_value)
            factors.append(self._assess_factor(
                "drawdown", drawdown_pct,
                self.thresholds.drawdown_warning_pct,
                self.thresholds.drawdown_critical_pct,
                higher_is_worse=True
            ))

            # 3. Consecutive losses
            factors.append(self._assess_factor(
                "consecutive_losses", float(self._consecutive_losses),
                self.thresholds.consecutive_losses_warning,
                self.thresholds.consecutive_losses_critical,
                higher_is_worse=True
            ))

            # 4. Correlation exposure
            corr_exposure = self._calculate_correlation_exposure(open_positions, correlation_matrix)
            factors.append(self._assess_factor(
                "correlation", corr_exposure,
                self.thresholds.correlation_warning_pct,
                self.thresholds.correlation_critical_pct,
                higher_is_worse=True
            ))

            # 5. Asset concentration
            conc_exposure = self._calculate_concentration(open_positions, portfolio_value)
            factors.append(self._assess_factor(
                "concentration", conc_exposure,
                self.thresholds.concentration_warning_pct,
                self.thresholds.concentration_critical_pct,
                higher_is_worse=True
            ))

            # 6. Funding risk (futures only)
            funding_risk = self._calculate_funding_risk(open_positions, portfolio_value)
            factors.append(self._assess_factor(
                "funding", funding_risk,
                self.thresholds.funding_warning_pct,
                self.thresholds.funding_critical_pct,
                higher_is_worse=True
            ))

            # 7. Liquidation distance
            liq_distance = self._calculate_liquidation_distance(open_positions)
            factors.append(self._assess_factor(
                "liquidation", liq_distance,
                self.thresholds.liquidation_distance_warning_pct,
                self.thresholds.liquidation_distance_critical_pct,
                higher_is_worse=False  # Lower distance = worse
            ))

            # 8. Daily loss (only when P&L is negative)
            daily_loss_pct = 0.0
            if daily_pnl < 0 and portfolio_value > 0:
                daily_loss_pct = abs(daily_pnl) / portfolio_value * 100
            daily_loss_ratio = daily_loss_pct / self._admin_max_daily_loss if self._admin_max_daily_loss > 0 else 0
            factors.append(self._assess_factor(
                "daily_loss", daily_loss_ratio * 100,
                self.thresholds.daily_loss_warning_pct * 100,
                self.thresholds.daily_loss_critical_pct * 100,
                higher_is_worse=True
            ))

            # 9. Data quality
            factors.append(self._assess_factor(
                "data_quality", data_quality_score * 100,
                self.thresholds.data_quality_warning_score * 100,
                self.thresholds.data_quality_critical_score * 100,
                higher_is_worse=False  # Lower score = worse
            ))

            # 10. System health
            factors.append(self._assess_factor(
                "system_health", system_health_score * 100,
                self.thresholds.system_health_warning_score * 100,
                self.thresholds.system_health_critical_score * 100,
                higher_is_worse=False
            ))

            # Determine overall level
            levels = [f.level for f in factors]
            if RiskLevel.CRITICAL in levels:
                overall = RiskLevel.CRITICAL
            elif RiskLevel.HIGH in levels:
                overall = RiskLevel.HIGH
            elif RiskLevel.ELEVATED in levels:
                overall = RiskLevel.ELEVATED
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
                risk_budget_used_pct=risk_budget
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
        higher_is_worse: bool = True
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
            message=msg
        )

    def _calculate_drawdown(self, portfolio_value: float) -> float:
        """Calculate current drawdown from peak."""
        # In production, track peak portfolio value
        # For now, return 0 as placeholder
        return 0.0

    def _calculate_correlation_exposure(
        self,
        positions: dict[str, Any],
        correlation_matrix: Optional[dict]
    ) -> float:
        """Calculate % of portfolio in correlated assets."""
        if not positions or not correlation_matrix:
            return 0.0
        # Simplified: assume all positions are somewhat correlated
        total_notional = sum(
            abs(p.get("amount", 0) * p.get("current_price", p.get("entry_price", 0)))
            for p in positions.values()
        )
        if total_notional == 0:
            return 0.0
        # Return % of notional in top correlated group
        return 50.0  # Placeholder

    def _calculate_concentration(
        self,
        positions: dict[str, Any],
        portfolio_value: float
    ) -> float:
        """Calculate max single-asset concentration."""
        if portfolio_value <= 0 or not positions:
            return 0.0

        max_exposure = 0.0
        for pos in positions.values():
            notional = abs(pos.get("amount", 0) * pos.get("current_price", pos.get("entry_price", 0)))
            exposure_pct = (notional / portfolio_value) * 100
            max_exposure = max(max_exposure, exposure_pct)

        return max_exposure

    def _calculate_funding_risk(
        self,
        positions: dict[str, Any],
        portfolio_value: float
    ) -> float:
        """Calculate funding payment risk as % of portfolio."""
        if portfolio_value <= 0:
            return 0.0

        total_funding = 0.0
        for pos in positions.values():
            if pos.get("market") == "FUTURES":
                # Estimate funding per period
                notional = abs(pos.get("amount", 0) * pos.get("entry_price", 0))
                leverage = pos.get("leverage", 1)
                # Rough estimate: 0.01% per 8h * leverage
                funding_per_period = notional * leverage * 0.0001
                total_funding += funding_per_period

        return (total_funding / portfolio_value) * 100

    def _calculate_liquidation_distance(
        self,
        positions: dict[str, Any]
    ) -> float:
        """Calculate minimum distance to liquidation across futures positions."""
        min_distance = 100.0  # Default far from liquidation

        for pos in positions.values():
            if pos.get("market") == "FUTURES" and pos.get("liq_price"):
                current = pos.get("current_price", pos.get("entry_price", 0))
                liq = pos.get("liq_price", 0)
                entry = pos.get("entry_price", 0)

                if current > 0 and liq > 0 and entry > 0:
                    if pos.get("side") == "LONG":
                        distance_pct = (current - liq) / current * 100
                    else:
                        distance_pct = (liq - current) / current * 100
                    min_distance = min(min_distance, max(0, distance_pct))

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

        # Close riskiest positions - would need integration with simulator
        if RiskAction.CLOSE_RISKIEST_POSITIONS in actions:
            logger.critical("CLOSE_RISKIEST_POSITIONS action triggered - requires simulator integration")

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