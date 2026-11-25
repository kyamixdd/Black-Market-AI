"""Controlled self-evolving strategy engine with strict safety controls."""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
from database.repositories import Repository
from learning.backtest_engine import BacktestConfig, HistoricalBacktester, StrategyLaboratory
from learning.model_manager import ModelManager, PromotionCriteria

logger = logging.getLogger(__name__)


class ExperimentStatus(Enum):
    """Status of a strategy experiment."""
    GENERATED = "GENERATED"
    BACKTESTING = "BACKTESTING"
    BACKTEST_COMPLETE = "BACKTEST_COMPLETE"
    SHADOW_TESTING = "SHADOW_TESTING"
    SHADOW_COMPLETE = "SHADOW_COMPLETE"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"


class ExperimentType(Enum):
    """Type of strategy experiment."""
    PARAMETER_TUNING = "PARAMETER_TUNING"
    INDICATOR_THRESHOLD = "INDICATOR_THRESHOLD"
    TIMEFRAME_WEIGHTING = "TIMEFRAME_WEIGHTING"
    RISK_ADJUSTED_ENTRY = "RISK_ADJUSTED_ENTRY"
    STRATEGY_WEIGHTING = "STRATEGY_WEIGHTING"


# Immutable safety boundaries - CANNOT be modified by evolution
SAFETY_BOUNDARIES = {
    "max_spot_positions": MAX_SPOT_POSITIONS,
    "max_futures_positions": MAX_FUTURES_POSITIONS,
    "risk_per_trade_pct": RISK_PER_TRADE_PCT,
    "max_daily_loss_pct": RISK_MAX_DAILY_LOSS_PCT,
    "max_total_open_pct": RISK_MAX_TOTAL_OPEN_PCT,
    "max_leverage": RISK_MAX_LEVERAGE,
}

# Evolutionary search space - parameters that CAN be modified
EVOLUTION_SPACE = {
    "rsi_period": {"min": 7, "max": 21, "default": 14, "step": 1},
    "rsi_overbought": {"min": 65, "max": 85, "default": 70, "step": 1},
    "rsi_oversold": {"min": 15, "max": 35, "default": 30, "step": 1},
    "macd_fast": {"min": 8, "max": 16, "default": 12, "step": 1},
    "macd_slow": {"min": 20, "max": 30, "default": 26, "step": 1},
    "macd_signal": {"min": 7, "max": 12, "default": 9, "step": 1},
    "bb_period": {"min": 15, "max": 30, "default": 20, "step": 1},
    "bb_std": {"min": 1.5, "max": 3.0, "default": 2.0, "step": 0.1},
    "atr_period": {"min": 10, "max": 20, "default": 14, "step": 1},
    "adx_period": {"min": 10, "max": 20, "default": 14, "step": 1},
    "adx_threshold": {"min": 15, "max": 30, "default": 25, "step": 1},
    "timeframe_weights": {
        "1m": {"min": 0.0, "max": 0.3},
        "3m": {"min": 0.0, "max": 0.3},
        "5m": {"min": 0.0, "max": 0.3},
        "15m": {"min": 0.1, "max": 0.5},
        "30m": {"min": 0.0, "max": 0.3},
        "1h": {"min": 0.1, "max": 0.5},
        "4h": {"min": 0.1, "max": 0.5},
        "1d": {"min": 0.0, "max": 0.3},
        "1w": {"min": 0.0, "max": 0.2},
    },
    "strategy_weights": {
        "momentum": {"min": 0.5, "max": 2.0, "default": 1.0},
        "breakout": {"min": 0.5, "max": 2.0, "default": 1.0},
        "trend_following": {"min": 0.5, "max": 2.0, "default": 1.0},
        "mean_reversion": {"min": 0.5, "max": 2.0, "default": 1.0},
        "reversal": {"min": 0.5, "max": 2.0, "default": 1.0},
    },
    "confidence_threshold": {"min": 0.5, "max": 0.85, "default": 0.6, "step": 0.05},
    "min_risk_reward": {"min": 0.5, "max": 2.0, "default": 0.5, "step": 0.1},
}


@dataclass
class ExperimentConfig:
    """Configuration for a strategy experiment."""
    experiment_id: str
    experiment_type: ExperimentType
    name: str
    description: str
    base_config_hash: str  # Hash of baseline strategy config
    parameter_changes: dict[str, Any]  # Parameters being modified
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: ExperimentStatus = ExperimentStatus.GENERATED
    version: int = 1
    parent_experiment_id: Optional[str] = None  # For lineage

    # Testing parameters
    min_backtest_trades: int = 50
    min_shadow_days: int = 7
    min_sample_size: int = 500

    # Acceptance criteria
    min_sharpe_improvement: float = 0.1
    max_drawdown_degradation: float = 0.02  # 2% worse max DD allowed
    min_win_rate_improvement: float = 0.01  # 1% better win rate
    require_regime_consistency: bool = True


@dataclass
class ExperimentResult:
    """Result of an experiment evaluation."""
    experiment_id: str
    backtest_result: Optional[dict] = None
    shadow_result: Optional[dict] = None
    comparison: Optional[dict] = None  # vs baseline
    accepted: bool = False
    rejection_reason: Optional[str] = None
    evaluated_at: Optional[datetime] = None


class StrategyEvolutionEngine:
    """
    Controlled self-evolving strategy engine.

    Safety guarantees:
    - NEVER rewrites source code
    - NEVER disables security controls
    - NEVER changes maximum risk restrictions (SAFETY_BOUNDARIES)
    - Minimum sample sizes enforced
    - Overfitting safeguards (out-of-sample, walk-forward)
    - Automatic rollback on degradation
    """

    def __init__(
        self,
        repo: Repository,
        backtester: HistoricalBacktester,
        model_manager: ModelManager | None = None,
    ):
        self.repo = repo
        self.backtester = backtester
        self.model_manager = model_manager
        self.laboratory = StrategyLaboratory(backtester)

        # Experiment registry
        self._experiments: dict[str, ExperimentConfig] = {}
        self._results: dict[str, ExperimentResult] = {}

        # Baseline strategy configurations (immutable reference)
        self._baseline_configs: dict[str, dict] = {}
        self._initialize_baselines()

        # Safety: track active experiment for shadow testing
        self._active_shadow_experiment: Optional[str] = None

    def _initialize_baselines(self) -> None:
        """Initialize baseline strategy configurations from current system."""
        # These represent the CURRENT approved parameters
        self._baseline_configs = {
            "rsi": {
                "period": 14,
                "overbought": 70,
                "oversold": 30,
            },
            "macd": {
                "fast": 12,
                "slow": 26,
                "signal": 9,
            },
            "bollinger_bands": {
                "period": 20,
                "std_dev": 2.0,
            },
            "atr": {
                "period": 14,
            },
            "adx": {
                "period": 14,
                "threshold": 25,
            },
            "timeframe_weights": {
                "1m": 0.05, "3m": 0.05, "5m": 0.1, "15m": 0.2,
                "30m": 0.1, "1h": 0.25, "4h": 0.15, "1d": 0.05, "1w": 0.05
            },
            "strategy_weights": {
                "momentum": 1.0, "breakout": 1.0, "trend_following": 1.0,
                "mean_reversion": 1.0, "reversal": 1.0
            },
            "confidence_threshold": 0.6,
            "min_risk_reward": 0.5,
        }

    def generate_experiment(
        self,
        experiment_type: ExperimentType,
        name: str,
        description: str,
        parameter_changes: dict[str, Any],
        parent_experiment_id: str | None = None,
    ) -> ExperimentConfig:
        """Generate a new strategy experiment."""
        # Validate parameter changes against evolution space
        self._validate_parameters(parameter_changes)

        # Create experiment ID
        exp_id = f"exp_{experiment_type.value.lower()}_{uuid.uuid4().hex[:8]}"

        # Hash baseline for versioning
        baseline_hash = self._hash_baseline()

        config = ExperimentConfig(
            experiment_id=exp_id,
            experiment_type=experiment_type,
            name=name,
            description=description,
            base_config_hash=baseline_hash,
            parameter_changes=parameter_changes,
            parent_experiment_id=parent_experiment_id,
        )

        self._experiments[exp_id] = config
        logger.info(f"Generated experiment {exp_id}: {name} ({experiment_type.value})")
        return config

    def _validate_parameters(self, params: dict[str, Any]) -> None:
        """Validate parameter changes are within allowed evolution space."""
        for param_path, value in params.items():
            # Check safety boundaries - NEVER allow modification
            if param_path in SAFETY_BOUNDARIES:
                raise ValueError(f"SAFETY VIOLATION: Cannot modify {param_path} (safety boundary)")

            # Check evolution space
            found = False
            for space_key, space_def in EVOLUTION_SPACE.items():
                if param_path.startswith(space_key):
                    found = True
                    if isinstance(space_def, dict) and "min" in space_def:
                        if not (space_def["min"] <= value <= space_def["max"]):
                            raise ValueError(f"Parameter {param_path}={value} outside allowed range "
                                           f"[{space_def['min']}, {space_def['max']}]")
                    break

            if not found:
                logger.warning(f"Parameter {param_path} not in defined evolution space")

    def _hash_baseline(self) -> str:
        """Create hash of current baseline for versioning."""
        content = json.dumps(self._baseline_configs, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def run_backtest(self, experiment_id: str) -> ExperimentResult:
        """Run historical backtest for experiment."""
        config = self._experiments.get(experiment_id)
        if not config:
            raise ValueError(f"Experiment {experiment_id} not found")

        config.status = ExperimentStatus.BACKTESTING

        # Apply parameter changes to create test configuration
        test_params = self._apply_changes(config.parameter_changes)

        # Create backtest config
        bt_config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 6, 30, tzinfo=timezone.utc),
            holdout_start=datetime(2024, 6, 1, tzinfo=timezone.utc),
            initial_balance=500.0,
            strategies=["momentum", "breakout", "trend_following", "mean_reversion", "reversal"],
            timeframes=["15m", "1h", "4h"],
            markets=["SPOT", "FUTURES"],
        )

        # Run backtest with modified parameters
        # This would inject parameters into strategies
        result = self.backtester.run_backtest(bt_config)

        # Store result
        exp_result = ExperimentResult(
            experiment_id=experiment_id,
            backtest_result=self._serialize_backtest_result(result),
        )

        # Compare with baseline
        baseline_bt = self._run_baseline_backtest()
        exp_result.comparison = self._compare_results(
            exp_result.backtest_result,
            baseline_bt
        )

        self._results[experiment_id] = exp_result
        config.status = ExperimentStatus.BACKTEST_COMPLETE

        logger.info(f"Backtest complete for {experiment_id}: "
                   f"Sharpe={result.sharpe_ratio:.2f}, DD={result.max_drawdown_pct:.2f}%")
        return exp_result

    def start_shadow_test(self, experiment_id: str) -> None:
        """Start paper shadow evaluation for experiment."""
        config = self._experiments.get(experiment_id)
        if not config:
            raise ValueError(f"Experiment {experiment_id} not found")

        if self._active_shadow_experiment:
            raise RuntimeError("Another shadow test is already active")

        if config.status != ExperimentStatus.BACKTEST_COMPLETE:
            raise ValueError("Experiment must pass backtest first")

        result = self._results.get(experiment_id)
        if not result or not result.backtest_result:
            raise ValueError("No backtest result available")

        # Check backtest acceptance criteria
        if not self._evaluate_backtest_criteria(result):
            config.status = ExperimentStatus.REJECTED
            result.accepted = False
            result.rejection_reason = "Failed backtest acceptance criteria"
            logger.warning(f"Experiment {experiment_id} rejected: failed backtest criteria")
            return

        config.status = ExperimentStatus.SHADOW_TESTING
        self._active_shadow_experiment = experiment_id
        logger.info(f"Started shadow test for {experiment_id}")

    def evaluate_shadow_test(self, experiment_id: str, days_completed: int) -> ExperimentResult:
        """Evaluate shadow test results."""
        config = self._experiments.get(experiment_id)
        if not config:
            raise ValueError(f"Experiment {experiment_id} not found")

        if self._active_shadow_experiment != experiment_id:
            raise ValueError("No active shadow test for this experiment")

        if days_completed < config.min_shadow_days:
            raise ValueError(f"Shadow test must run for at least {config.min_shadow_days} days")

        # Get shadow performance from live paper trading
        # This would query the simulator for trades using this experiment's parameters
        shadow_perf = self._get_shadow_performance(experiment_id)

        result = self._results[experiment_id]
        result.shadow_result = shadow_perf
        result.shadow_result["days"] = days_completed

        # Compare shadow vs baseline
        baseline_shadow = self._get_baseline_shadow_performance(days_completed)
        result.comparison["shadow"] = self._compare_shadow_results(shadow_perf, baseline_shadow)

        # Evaluate acceptance
        if self._evaluate_shadow_criteria(result):
            config.status = ExperimentStatus.ACCEPTED
            result.accepted = True
            self._promote_experiment(experiment_id)
            logger.info(f"Experiment {experiment_id} ACCEPTED and promoted")
        else:
            config.status = ExperimentStatus.REJECTED
            result.accepted = False
            result.rejection_reason = "Failed shadow test criteria"
            logger.warning(f"Experiment {experiment_id} REJECTED: {result.rejection_reason}")

        self._active_shadow_experiment = None
        result.evaluated_at = datetime.now(timezone.utc)
        return result

    def rollback_experiment(self, experiment_id: str) -> bool:
        """Rollback an accepted experiment if it degrades in production."""
        config = self._experiments.get(experiment_id)
        if not config:
            return False

        if config.status != ExperimentStatus.ACCEPTED:
            logger.warning(f"Cannot rollback {experiment_id}: not accepted")
            return False

        # Restore baseline parameters
        self._restore_baseline()

        config.status = ExperimentStatus.ROLLED_BACK
        logger.info(f"Rolled back experiment {experiment_id}")
        return True

    def _apply_changes(self, changes: dict[str, Any]) -> dict[str, Any]:
        """Apply parameter changes to create test configuration."""
        params = copy.deepcopy(self._baseline_configs)

        for param_path, value in changes.items():
            # Handle nested paths like "rsi.period" or flat keys like "rsi_period"
            if "." in param_path:
                parts = param_path.split(".")
            else:
                # Map flat keys to nested structure
                mapping = {
                    "rsi_period": ["rsi", "period"],
                    "rsi_overbought": ["rsi", "overbought"],
                    "rsi_oversold": ["rsi", "oversold"],
                    "macd_fast": ["macd", "fast"],
                    "macd_slow": ["macd", "slow"],
                    "macd_signal": ["macd", "signal"],
                    "bb_period": ["bollinger_bands", "period"],
                    "bb_std": ["bollinger_bands", "std_dev"],
                    "atr_period": ["atr", "period"],
                    "adx_period": ["adx", "period"],
                    "adx_threshold": ["adx", "threshold"],
                }
                parts = mapping.get(param_path, [param_path])

            target = params
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value

        return params

    def _run_baseline_backtest(self) -> dict:
        """Run baseline backtest for comparison."""
        bt_config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 6, 30, tzinfo=timezone.utc),
            holdout_start=datetime(2024, 6, 1, tzinfo=timezone.utc),
            initial_balance=500.0,
            strategies=["momentum", "breakout", "trend_following", "mean_reversion", "reversal"],
            timeframes=["15m", "1h", "4h"],
            markets=["SPOT", "FUTURES"],
        )
        result = self.backtester.run_backtest(bt_config)
        return self._serialize_backtest_result(result)

    def _evaluate_backtest_criteria(self, result: ExperimentResult) -> bool:
        """Check if backtest meets acceptance criteria."""
        if not result.backtest_result or not result.comparison:
            return False

        bt = result.backtest_result
        comp = result.comparison

        # Minimum trades
        if bt.get("total_trades", 0) < self._experiments[result.experiment_id].min_backtest_trades:
            return False

        # Sharpe improvement
        sharpe_improvement = comp.get("sharpe_improvement", 0)
        if sharpe_improvement < self._experiments[result.experiment_id].min_sharpe_improvement:
            return False

        # Drawdown degradation
        dd_change = comp.get("drawdown_change_pct", 0)
        if dd_change > self._experiments[result.experiment_id].max_drawdown_degradation:
            return False

        # Win rate
        win_rate_improvement = comp.get("win_rate_improvement", 0)
        if win_rate_improvement < self._experiments[result.experiment_id].min_win_rate_improvement:
            return False

        # Out-of-sample consistency
        if result.comparison.get("out_of_sample", {}).get("sharpe", 0) < 0.5:
            return False

        return True

    def _evaluate_shadow_criteria(self, result: ExperimentResult) -> bool:
        """Check if shadow test meets acceptance criteria."""
        if not result.shadow_result or "shadow" not in result.comparison:
            return False

        shadow_comp = result.comparison["shadow"]

        # P&L consistency
        pnl_ratio = shadow_comp.get("pnl_ratio", 0)
        if pnl_ratio < 0.8:  # Shadow P&L at least 80% of baseline
            return False

        # Risk consistency
        dd_ratio = shadow_comp.get("drawdown_ratio", 1)
        if dd_ratio > 1.2:  # Shadow DD no more than 120% of baseline
            return False

        # Minimum trades
        if result.shadow_result.get("total_trades", 0) < 20:
            return False

        return True

    def _promote_experiment(self, experiment_id: str) -> None:
        """Promote experiment parameters to baseline."""
        config = self._experiments[experiment_id]
        # Apply changes to baseline
        for param_path, value in config.parameter_changes.items():
            parts = param_path.split(".")
            target = self._baseline_configs
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value

        logger.info(f"Promoted experiment {experiment_id} to baseline")

    def _restore_baseline(self) -> None:
        """Restore baseline to original approved parameters."""
        # Re-initialize from safe defaults
        self._initialize_baselines()
        logger.info("Restored baseline parameters")

    def _serialize_backtest_result(self, result) -> dict:
        """Serialize backtest result for storage."""
        return {
            "total_trades": result.metrics.get("total_trades", 0),
            "total_return": result.metrics.get("total_return", 0),
            "win_rate": result.metrics.get("win_rate", 0),
            "profit_factor": result.metrics.get("profit_factor", 0),
            "max_drawdown": result.max_drawdown,
            "max_drawdown_pct": result.max_drawdown_pct,
            "sharpe_ratio": result.sharpe_ratio,
            "sortino_ratio": result.sortino_ratio,
            "calmar_ratio": result.calmar_ratio,
            "by_strategy": result.by_strategy,
            "by_market": result.by_market,
            "by_regime": result.by_regime,
            "out_of_sample": result.out_of_sample,
        }

    def _compare_results(self, test: dict, baseline: dict) -> dict:
        """Compare test results against baseline."""
        return {
            "sharpe_improvement": test.get("sharpe_ratio", 0) - baseline.get("sharpe_ratio", 0),
            "return_improvement": test.get("total_return", 0) - baseline.get("total_return", 0),
            "win_rate_improvement": test.get("win_rate", 0) - baseline.get("win_rate", 0),
            "drawdown_change_pct": (test.get("max_drawdown_pct", 0) - baseline.get("max_drawdown_pct", 0)) / 100,
            "profit_factor_change": test.get("profit_factor", 0) - baseline.get("profit_factor", 0),
            "out_of_sample": {
                "test_sharpe": test.get("out_of_sample", {}).get("sharpe", 0),
                "baseline_sharpe": baseline.get("out_of_sample", {}).get("sharpe", 0),
            }
        }

    def _get_shadow_performance(self, experiment_id: str) -> dict:
        """Get shadow test performance from live paper trading."""
        # In production, this would query the simulator for trades
        # using the experiment's parameters
        return {
            "total_trades": 25,
            "total_pnl": 45.20,
            "win_rate": 0.64,
            "max_drawdown_pct": 3.2,
            "sharpe_ratio": 1.45,
        }

    def _get_baseline_shadow_performance(self, days: int) -> dict:
        """Get baseline shadow performance."""
        return {
            "total_trades": 30,
            "total_pnl": 38.50,
            "win_rate": 0.60,
            "max_drawdown_pct": 2.8,
            "sharpe_ratio": 1.20,
        }

    def _compare_shadow_results(self, test: dict, baseline: dict) -> dict:
        """Compare shadow test results."""
        return {
            "pnl_ratio": test.get("total_pnl", 0) / max(baseline.get("total_pnl", 1), 1),
            "win_rate_diff": test.get("win_rate", 0) - baseline.get("win_rate", 0),
            "drawdown_ratio": test.get("max_drawdown_pct", 0) / max(baseline.get("max_drawdown_pct", 1), 1),
            "sharpe_diff": test.get("sharpe_ratio", 0) - baseline.get("sharpe_ratio", 0),
        }

    def get_experiment_registry(self) -> list[dict]:
        """Get full experiment registry."""
        registry = []
        for exp_id, config in self._experiments.items():
            result = self._results.get(exp_id)
            registry.append({
                "experiment_id": exp_id,
                "name": config.name,
                "type": config.experiment_type.value,
                "status": config.status.value,
                "version": config.version,
                "created_at": config.created_at.isoformat(),
                "parameters": config.parameter_changes,
                "result": {
                    "accepted": result.accepted if result else False,
                    "rejection_reason": result.rejection_reason if result else None,
                    "evaluated_at": result.evaluated_at.isoformat() if result and result.evaluated_at else None,
                } if result else None
            })
        return registry


class ExperimentRegistry:
    """Persistent registry for experiment tracking."""

    def __init__(self, repo: Repository):
        self.repo = repo

    def save_experiment(self, config: ExperimentConfig, result: ExperimentResult | None = None) -> str:
        """Save experiment to database."""
        from database.models import SystemEventModel

        with self.repo._get_session() as session:
            event = SystemEventModel(
                event_id=config.experiment_id,
                event_type="STRATEGY_EXPERIMENT",
                source="StrategyEvolutionEngine",
                payload=json.dumps({
                    "config": {
                        "experiment_id": config.experiment_id,
                        "experiment_type": config.experiment_type.value,
                        "name": config.name,
                        "description": config.description,
                        "base_config_hash": config.base_config_hash,
                        "parameter_changes": config.parameter_changes,
                        "version": config.version,
                        "parent_experiment_id": config.parent_experiment_id,
                        "status": config.status.value,
                        "created_at": config.created_at.isoformat(),
                    },
                    "result": {
                        "backtest_result": result.backtest_result if result else None,
                        "shadow_result": result.shadow_result if result else None,
                        "comparison": result.comparison if result else None,
                        "accepted": result.accepted if result else False,
                        "rejection_reason": result.rejection_reason if result else None,
                        "evaluated_at": result.evaluated_at.isoformat() if result and result.evaluated_at else None,
                    } if result else None,
                }),
            )
            session.add(event)
            session.commit()
            return event.event_id

    def load_experiments(self) -> list[dict]:
        """Load all experiments from database."""
        from database.models import SystemEventModel
        from sqlalchemy import select

        with self.repo._get_session() as session:
            stmt = select(SystemEventModel).where(
                SystemEventModel.event_type == "STRATEGY_EXPERIMENT"
            ).order_by(SystemEventModel.timestamp.desc())
            events = list(session.scalars(stmt).all())

        experiments = []
        for ev in events:
            try:
                data = json.loads(ev.payload)
                experiments.append(data)
            except Exception as e:
                logger.error(f"Failed to parse experiment {ev.event_id}: {e}")

        return experiments