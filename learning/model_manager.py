"""Champion/Challenger model management with rigorous promotion criteria."""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from config import (
    MIN_VALIDATION_ACCURACY,
    MIN_VALIDATION_F1,
    MODEL_RETRAIN_MIN_DAYS,
    MODEL_VALIDATION_REQUIRED,
)
from database.models import ModelRegistryModel
from database.repositories import Repository
from learning.walkforward_validator import WalkForwardValidator
from learning.confidence_gate import ModelPromotionGate, PromotionGateCriteria

logger = logging.getLogger(__name__)


@dataclass
class PromotionCriteria:
    """Criteria for model promotion from challenger to champion."""
    min_net_expectancy: float = 0.001  # Positive edge after costs
    max_drawdown_pct: float = 10.0  # Maximum acceptable drawdown
    min_calibration_score: float = 0.7  # Brier score or similar
    min_stability_score: float = 0.6  # Performance consistency across folds
    min_regime_coverage: int = 2  # Must perform well in at least N regimes
    min_samples: int = 500  # Minimum evaluation samples
    min_improvement_over_champion: float = 0.02  # 2% better on primary metric

    def to_dict(self) -> dict:
        return {
            "min_net_expectancy": self.min_net_expectancy,
            "max_drawdown_pct": self.max_drawdown_pct,
            "min_calibration_score": self.min_calibration_score,
            "min_stability_score": self.min_stability_score,
            "min_regime_coverage": self.min_regime_coverage,
            "min_samples": self.min_samples,
            "min_improvement_over_champion": self.min_improvement_over_champion,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PromotionCriteria":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class EvaluationResult:
    """Result of model evaluation."""
    model_version: str
    model_type: str
    net_expectancy: float
    max_drawdown_pct: float
    calibration_score: float
    stability_score: float
    regime_performance: dict[str, Any]
    total_samples: int
    primary_metric: str
    primary_value: float
    passes_criteria: bool
    failure_reasons: list[str] = field(default_factory=list)
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    promotion_evidence: dict[str, Any] = field(default_factory=dict)


class ModelManager:
    """
    Manages champion/challenger model lifecycle with strict promotion criteria.

    Principles:
    - Challenger must pass ALL predefined criteria to replace champion
    - Evaluation on identical unseen chronological data
    - Transaction costs accounted for
    - Minimum sample sizes enforced
    - Champion retained if any criteria fail
    - Full audit trail of promotions/rollbacks
    """

    def __init__(self, repo: Repository, validator: WalkForwardValidator | None = None):
        self.repo = repo
        self.validator = validator or WalkForwardValidator()
        self.criteria = PromotionCriteria()
        self._champion: Optional[ModelRegistryModel] = None

    def get_champion(self, model_type: str) -> Optional[ModelRegistryModel]:
        """Get current champion model for a type."""
        with self.repo._get_session() as session:
            from sqlalchemy import select
            stmt = (
                select(ModelRegistryModel)
                .where(
                    ModelRegistryModel.model_type == model_type,
                    ModelRegistryModel.is_champion.is_(True)
                )
                .limit(1)
            )
            result = session.execute(stmt).scalar()
            if result:
                # Detach from session
                session.expunge(result)
            return result

    def get_challengers(self, model_type: str) -> list[ModelRegistryModel]:
        """Get all challenger models for a type."""
        with self.repo._get_session() as session:
            from sqlalchemy import select
            stmt = (
                select(ModelRegistryModel)
                .where(
                    ModelRegistryModel.model_type == model_type,
                    ModelRegistryModel.status.in_(["CHALLENGER", "CANDIDATE", "VALIDATED"])
                )
                .order_by(ModelRegistryModel.trained_at.desc())
            )
            results = list(session.scalars(stmt).all())
            for r in results:
                session.expunge(r)
            return results

    def register_challenger(
        self,
        version: str,
        model_type: str,
        file_path: str,
        metrics: dict,
        parent_version: str | None = None
    ) -> ModelRegistryModel:
        """Register a new challenger model."""
        model = ModelRegistryModel(
            version=version,
            model_type=model_type,
            file_path=file_path,
            metrics=json.dumps(metrics),
            status="CHALLENGER",
            is_active=False,
            is_champion=False,
            parent_version=parent_version,
            rollback_checkpoint=True
        )
        with self.repo._get_session() as session:
            session.add(model)
            session.commit()
            session.refresh(model)
            session.expunge(model)
        logger.info(f"Registered challenger {version} ({model_type})")
        return model

    def evaluate_challenger(
        self,
        challenger: ModelRegistryModel,
        X: Any,
        y: Any,
        regime_labels: Any | None = None,
        cost_per_trade: float = 0.001,
        economic_metadata: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        """Evaluate challenger with the same fail-closed promotion gate used by training.

        Economic metadata must contain aligned realized returns, round-trip fees/
        slippage, market, timestamp, horizon and regime. Missing evidence blocks
        automated promotion instead of substituting F1-based return estimates.
        """
        def model_factory():
            import joblib
            return joblib.load(challenger.file_path)

        wf_result = self.validator.validate(X, y, model_factory, metric="f1")
        champion = self.get_champion(challenger.model_type)
        champion_result: dict[str, Any] = {}
        if champion and champion.file_path:
            def champion_factory():
                import joblib
                return joblib.load(champion.file_path)
            champion_result = self.validator.validate(X, y, champion_factory, metric="f1")

        # The shared gate's RF/XGB slots represent this single model family
        # here; both entries use the identical folds and evidence.
        validation_payload = {
            "rf": wf_result, "xgb": wf_result,
            "ensemble_passes": bool(wf_result.get("valid") and wf_result.get("passes_threshold")),
        }
        champion_payload = {"rf": champion_result, "xgb": champion_result} if champion_result else {}
        gate_criteria = PromotionGateCriteria(
            min_samples=self.criteria.min_samples,
            min_net_expectancy=self.criteria.min_net_expectancy,
            max_drawdown_pct=self.criteria.max_drawdown_pct,
            min_calibration_score=self.criteria.min_calibration_score,
            min_stability_score=self.criteria.min_stability_score,
            min_regime_coverage=self.criteria.min_regime_coverage,
            min_improvement_over_champion=self.criteria.min_improvement_over_champion,
        )
        gate = ModelPromotionGate(gate_criteria).evaluate(
            validation_payload, sample_count=len(y),
            economic_metadata=economic_metadata,
            champion_validation=champion_payload,
        )
        evidence = gate.get("economic_evidence", {}).get("rf", {})
        result = EvaluationResult(
            model_version=challenger.version,
            model_type=challenger.model_type,
            net_expectancy=float(evidence.get("net_expectancy") or 0.0),
            max_drawdown_pct=float(evidence.get("max_drawdown_pct") or 0.0),
            calibration_score=float((gate.get("models", {}).get("rf") or {}).get("calibration_score") or 0.0),
            stability_score=float(evidence.get("stability_score") or 0.0),
            regime_performance=evidence.get("regime_performance") or {},
            total_samples=len(y),
            primary_metric="f1",
            primary_value=float((wf_result.get("aggregated") or {}).get("mean_f1") or 0.0),
            passes_criteria=bool(gate.get("passes")),
            failure_reasons=list(gate.get("failure_reasons") or []),
            promotion_evidence=gate,
        )
        self._store_evaluation(challenger, result)
        logger.info("Evaluated %s: passes=%s, reasons=%s", challenger.version, result.passes_criteria, result.failure_reasons)
        return result

    def compare_with_champion(
        self,
        challenger: ModelRegistryModel,
        X: Any,
        y: Any,
        regime_labels: Any | None = None
    ) -> dict[str, Any]:
        """Compare challenger directly with current champion on identical data."""
        champion = self.get_champion(challenger.model_type)
        if not champion:
            return {"has_champion": False, "message": "No champion exists, challenger can be promoted if criteria met"}

        # Evaluate both on identical data
        def champion_factory():
            import joblib
            return joblib.load(champion.file_path)

        def challenger_factory():
            import joblib
            return joblib.load(challenger.file_path)

        champ_result = self.validator.validate(X, y, champion_factory, metric="f1")
        chal_result = self.validator.validate(X, y, challenger_factory, metric="f1")

        champ_f1 = champ_result.get("aggregated", {}).get("mean_f1", 0)
        chal_f1 = chal_result.get("aggregated", {}).get("mean_f1", 0)

        improvement = (chal_f1 - champ_f1) / max(champ_f1, 0.001)

        return {
            "has_champion": True,
            "champion_version": champion.version,
            "champion_f1": champ_f1,
            "challenger_version": challenger.version,
            "challenger_f1": chal_f1,
            "improvement_pct": improvement * 100,
            "meets_improvement_threshold": improvement >= self.criteria.min_improvement_over_champion,
            "threshold_pct": self.criteria.min_improvement_over_champion * 100
        }

    def promote_challenger(self, challenger_version: str, evaluation: EvaluationResult) -> bool:
        """Promote challenger to champion if all criteria pass."""
        if (not evaluation.passes_criteria
                or evaluation.model_version != challenger_version
                or evaluation.promotion_evidence.get("passes") is not True):
            logger.warning(f"Cannot promote {challenger_version}: comprehensive gate evidence missing or failed - {evaluation.failure_reasons}")
            return False

        # Get champion for comparison
        with self.repo._get_session() as session:
            challenger = session.get(ModelRegistryModel, challenger_version)
            if not challenger:
                logger.error(f"Challenger {challenger_version} not found")
                return False

            # Compare with champion
            champ = self.get_champion(challenger.model_type)
            if champ:
                # Would need X, y for comparison - skip for now
                pass

            # Demote current champion
            if champ:
                champ.is_champion = False
                champ.status = "ROLLED_BACK"

            # Promote challenger
            challenger.is_champion = True
            challenger.is_active = True
            challenger.status = "CHAMPION"
            challenger.evaluation_data = json.dumps({
                "net_expectancy": evaluation.net_expectancy,
                "max_drawdown_pct": evaluation.max_drawdown_pct,
                "calibration_score": evaluation.calibration_score,
                "stability_score": evaluation.stability_score,
                "regime_performance": evaluation.regime_performance,
                "primary_metric": evaluation.primary_metric,
                "primary_value": evaluation.primary_value,
                "evaluated_at": evaluation.evaluated_at.isoformat()
            })
            challenger.promotion_criteria = json.dumps(self.criteria.to_dict())
            challenger.rollback_checkpoint = True

            session.commit()
            logger.info(f"Promoted {challenger_version} to CHAMPION")
            return True

    def rollback_champion(self, model_type: str, target_version: str | None = None) -> bool:
        """Rollback champion to previous version."""
        with self.repo._get_session() as session:
            current = session.execute(
                session.query(ModelRegistryModel).filter_by(model_type=model_type, is_champion=True)
            ).scalar()

            if not current:
                logger.warning(f"No champion to rollback for {model_type}")
                return False

            # Demote current
            current.is_champion = False
            current.is_active = False
            current.status = "ROLLED_BACK"

            # Find target
            if target_version:
                target = session.get(ModelRegistryModel, target_version)
            else:
                # Find previous checkpoint
                target = session.execute(
                    session.query(ModelRegistryModel)
                    .filter_by(model_type=model_type, rollback_checkpoint=True)
                    .filter(ModelRegistryModel.version != current.version)
                    .order_by(ModelRegistryModel.trained_at.desc())
                    .limit(1)
                ).scalar()

            if not target:
                logger.error(f"No rollback target found for {model_type}")
                return False

            target.is_champion = True
            target.is_active = True
            target.status = "CHAMPION"
            session.commit()
            logger.info(f"Rolled back {model_type} champion to {target.version}")
            return True

    def get_model_history(self, model_type: str) -> list[ModelRegistryModel]:
        """Get full history of models for a type."""
        with self.repo._get_session() as session:
            from sqlalchemy import select
            stmt = (
                select(ModelRegistryModel)
                .where(ModelRegistryModel.model_type == model_type)
                .order_by(ModelRegistryModel.trained_at.desc())
            )
            results = list(session.scalars(stmt).all())
            for r in results:
                session.expunge(r)
            return results

    def _calculate_net_expectancy(self, wf_result: dict, cost_per_trade: float) -> float:
        """Calculate net expectancy after transaction costs."""
        # Simplified: use F1 as proxy for win rate, assume 1:1 risk/reward
        f1 = wf_result.get("aggregated", {}).get("mean_f1", 0)
        win_rate = f1  # Approximation
        expectancy = win_rate * 1.0 - (1 - win_rate) * 1.0  # 1R win, 1R loss
        return expectancy - cost_per_trade * 2  # Entry + exit

    def _calculate_walkforward_drawdown(self, wf_result: dict) -> float:
        """Calculate max drawdown from walk-forward results."""
        folds = wf_result.get("folds", [])
        if not folds:
            return 0.0

        # Simulate equity curve from fold results
        equity = 1.0
        peak = 1.0
        max_dd = 0.0

        for fold in folds:
            # Approximate return from F1
            ret = (fold.get("f1_macro", 0) - 0.5) * 0.1  # Scale
            equity *= (1 + ret)
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100
            max_dd = max(max_dd, dd)

        return max_dd

    def _calculate_calibration(self, wf_result: dict) -> float:
        """Calculate calibration score (Brier score inverse)."""
        # Simplified: higher F1 and lower variance = better calibration
        f1 = wf_result.get("aggregated", {}).get("mean_f1", 0)
        std = wf_result.get("aggregated", {}).get("std_f1", 0)
        return max(0, f1 - std)

    def _calculate_stability(self, wf_result: dict) -> float:
        """Calculate performance stability across folds."""
        folds = wf_result.get("folds", [])
        if len(folds) < 2:
            return 0.0

        f1_scores = [f.get("f1_macro", 0) for f in folds]
        if not f1_scores:
            return 0.0

        # Stability = 1 - coefficient of variation
        mean_f1 = sum(f1_scores) / len(f1_scores)
        if mean_f1 == 0:
            return 0.0
        std_f1 = (sum((x - mean_f1)**2 for x in f1_scores) / len(f1_scores))**0.5
        cv = std_f1 / mean_f1
        return max(0, 1 - cv)

    def _evaluate_by_regime(self, X, y, regime_labels, model_factory) -> dict[str, float]:
        """Evaluate model performance by market regime."""
        import numpy as np
        regimes = np.unique(regime_labels)
        results = {}

        for regime in regimes:
            mask = regime_labels == regime
            if mask.sum() < 50:
                continue
            X_regime = X[mask]
            y_regime = y[mask]
            model = model_factory()
            model.fit(X_regime, y_regime)
            pred = model.predict(X_regime)
            from sklearn.metrics import f1_score
            f1 = f1_score(y_regime, pred, average="macro", zero_division=0)
            results[regime] = f1

        return results

    def _store_evaluation(self, model: ModelRegistryModel, evaluation: EvaluationResult) -> None:
        """Store evaluation result in model record."""
        with self.repo._get_session() as session:
            m = session.get(ModelRegistryModel, model.version)
            if m:
                m.evaluation_data = json.dumps({
                    "net_expectancy": evaluation.net_expectancy,
                    "max_drawdown_pct": evaluation.max_drawdown_pct,
                    "calibration_score": evaluation.calibration_score,
                    "stability_score": evaluation.stability_score,
                    "regime_performance": evaluation.regime_performance,
                    "primary_metric": evaluation.primary_metric,
                    "primary_value": evaluation.primary_value,
                    "passes_criteria": evaluation.passes_criteria,
                    "failure_reasons": evaluation.failure_reasons,
                    "promotion_evidence": evaluation.promotion_evidence,
                    "evaluated_at": evaluation.evaluated_at.isoformat()
                })
                session.commit()