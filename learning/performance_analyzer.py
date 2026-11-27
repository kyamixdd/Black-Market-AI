"""Performance analysis and improvement proposal generation."""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any

from database.repositories import Repository

logger = logging.getLogger(__name__)


class PerformanceAnalyzer:
    """Analyzes prediction performance and generates improvement proposals."""

    def __init__(self, repo: Repository):
        self.repo = repo

    def generate_report(self, days: int = 7) -> dict[str, Any]:
        """Generate comprehensive performance report."""
        preds = self.repo.get_predictions_history(limit=10000)

        # Filter by date - handle both naive and aware datetimes
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent = []
        for p in preds:
            if p.is_correct is None:
                continue
            created_at = p.created_at
            if created_at is None:
                continue
            # Ensure both are timezone-aware for comparison
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if created_at >= cutoff:
                recent.append(p)

        if not recent:
            return {"status": "insufficient_data", "message": f"No evaluated predictions in last {days} days"}

        # Overall metrics
        total = len(recent)
        correct = sum(1 for p in recent if p.is_correct)
        accuracy = correct / total if total > 0 else 0

        # By dimension
        by_strategy = self._group_by(recent, lambda p: p.strategy_version or "unknown")
        by_market = self._group_by(recent, lambda p: p.market)
        by_symbol = self._group_by(recent, lambda p: p.symbol)
        by_timeframe = self._group_by(recent, lambda p: p.timeframe or "unknown")
        by_regime = self._group_by(recent, lambda p: p.regime or "unknown")
        by_model = self._group_by(recent, lambda p: p.model_version)
        by_confidence = self._group_by_confidence(recent)

        # Identify recurring failures
        failure_patterns = self._identify_failure_patterns(recent)

        # Generate improvement proposals
        proposals = self._generate_proposals(failure_patterns, by_strategy, by_regime, by_model)

        return {
            "period_days": days,
            "total_predictions": total,
            "accuracy": accuracy,
            "correct_predictions": correct,
            "by_strategy": by_strategy,
            "by_market": by_market,
            "by_symbol": by_symbol,
            "by_timeframe": by_timeframe,
            "by_regime": by_regime,
            "by_model_version": by_model,
            "by_confidence_range": by_confidence,
            "failure_patterns": failure_patterns,
            "improvement_proposals": proposals,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }

    def _group_by(self, preds: list, key_fn) -> dict[str, dict[str, Any]]:
        """Group predictions and calculate metrics for each group."""
        groups = defaultdict(list)
        for p in preds:
            groups[key_fn(p)].append(p)

        result = {}
        for key, items in groups.items():
            total = len(items)
            correct = sum(1 for p in items if p.is_correct)
            avg_conf = sum(p.confidence for p in items) / total if total > 0 else 0
            avg_return = sum(p.simulated_pnl or 0 for p in items) / total if total > 0 else 0
            result[key] = {
                "count": total,
                "accuracy": correct / total if total > 0 else 0,
                "avg_confidence": avg_conf,
                "avg_simulated_return": avg_return
            }
        return result

    def _group_by_confidence(self, preds: list) -> dict[str, dict[str, Any]]:
        """Group by confidence ranges."""
        ranges = {
            "0.0-0.5": (0.0, 0.5),
            "0.5-0.6": (0.5, 0.6),
            "0.6-0.7": (0.6, 0.7),
            "0.7-0.8": (0.7, 0.8),
            "0.8-0.9": (0.8, 0.9),
            "0.9-1.0": (0.9, 1.0),
        }
        result = {}
        for label, (lo, hi) in ranges.items():
            items = [p for p in preds if lo <= p.confidence < hi]
            if items:
                total = len(items)
                correct = sum(1 for p in items if p.is_correct)
                result[label] = {
                    "count": total,
                    "accuracy": correct / total if total > 0 else 0,
                    "avg_confidence": sum(p.confidence for p in items) / total
                }
        return result

    def _identify_failure_patterns(self, preds: list) -> list[dict[str, Any]]:
        """Identify systematic prediction failures."""
        failures = [p for p in preds if not p.is_correct]
        if not failures:
            return []

        patterns = []

        # 1. Low accuracy by strategy — group ALL preds so accuracy is meaningful
        by_strat = self._group_by(preds, lambda p: p.strategy_version or "unknown")
        for strat, metrics in by_strat.items():
            if metrics["accuracy"] < 0.4 and metrics["count"] >= 10:
                patterns.append({
                    "type": "strategy_failure",
                    "dimension": "strategy",
                    "value": strat,
                    "accuracy": metrics["accuracy"],
                    "count": metrics["count"],
                    "description": f"Strategy '{strat}' has {metrics['accuracy']:.1%} accuracy over {metrics['count']} predictions"
                })

        # 2. Low accuracy by regime
        by_reg = self._group_by(preds, lambda p: p.regime or "unknown")
        for regime, metrics in by_reg.items():
            if metrics["accuracy"] < 0.4 and metrics["count"] >= 10:
                patterns.append({
                    "type": "regime_failure",
                    "dimension": "regime",
                    "value": regime,
                    "accuracy": metrics["accuracy"],
                    "count": metrics["count"],
                    "description": f"Regime '{regime}' has {metrics['accuracy']:.1%} accuracy over {metrics['count']} predictions"
                })

        # 3. Confidence miscalibration (high confidence but wrong)
        high_conf_wrong = [p for p in failures if p.confidence > 0.75]
        if len(high_conf_wrong) >= 5:
            patterns.append({
                "type": "confidence_miscalibration",
                "dimension": "confidence",
                "value": "high_confidence_wrong",
                "count": len(high_conf_wrong),
                "description": f"{len(high_conf_wrong)} high-confidence (>75%) predictions were incorrect"
            })

        # 4. Low accuracy by symbol
        by_sym = self._group_by(preds, lambda p: p.symbol)
        for symbol, metrics in by_sym.items():
            if metrics["accuracy"] < 0.3 and metrics["count"] >= 5:
                patterns.append({
                    "type": "symbol_failure",
                    "dimension": "symbol",
                    "value": symbol,
                    "accuracy": metrics["accuracy"],
                    "count": metrics["count"],
                    "description": f"Symbol {symbol} has {metrics['accuracy']:.1%} accuracy"
                })

        return patterns

    def _generate_proposals(self, patterns: list[dict], by_strat: dict, by_regime: dict, by_model: dict) -> list[dict[str, Any]]:
        """Generate structured improvement proposals from failure patterns."""
        proposals = []

        for pattern in patterns:
            if pattern["type"] == "strategy_failure":
                proposals.append({
                    "priority": "HIGH",
                    "category": "Strategy Weight Adjustment",
                    "action": f"Reduce weight for strategy '{pattern['value']}' in regime-aware selector",
                    "rationale": pattern["description"],
                    "suggested_change": {"strategy_selector_weight": "decrease", "target_strategy": pattern["value"]},
                    "expected_impact": "Reduce false signals from underperforming strategy"
                })

            elif pattern["type"] == "regime_failure":
                proposals.append({
                    "priority": "HIGH",
                    "category": "Regime Detection Improvement",
                    "action": f"Improve regime detection for '{pattern['value']}' or exclude from trading",
                    "rationale": pattern["description"],
                    "suggested_change": {"regime_handling": "review", "target_regime": pattern["value"]},
                    "expected_impact": "Avoid trading in regimes where models perform poorly"
                })

            elif pattern["type"] == "confidence_miscalibration":
                proposals.append({
                    "priority": "MEDIUM",
                    "category": "Confidence Calibration",
                    "action": "Retrain confidence engine with recent data, adjust calibration curves",
                    "rationale": pattern["description"],
                    "suggested_change": {"confidence_engine": "recalibrate"},
                    "expected_impact": "Better alignment between confidence scores and actual accuracy"
                })

            elif pattern["type"] == "symbol_failure":
                proposals.append({
                    "priority": "MEDIUM",
                    "category": "Symbol Exclusion",
                    "action": f"Add symbol '{pattern['value']}' to temporary exclusion list or increase min_samples requirement",
                    "rationale": pattern["description"],
                    "suggested_change": {"symbol_eligibility": "review", "target_symbol": pattern["value"]},
                    "expected_impact": "Prevent capital allocation to consistently unprofitable symbols"
                })

        # Proposals based on model version performance
        for model_ver, metrics in by_model.items():
            if metrics["accuracy"] < 0.45 and metrics["count"] >= 20:
                proposals.append({
                    "priority": "HIGH",
                    "category": "Model Rollback",
                    "action": f"Rollback model '{model_ver}' and promote previous validated version",
                    "rationale": f"Model {model_ver} has {metrics['accuracy']:.1%} accuracy over {metrics['count']} predictions",
                    "suggested_change": {"model_registry": "rollback", "target_version": model_ver},
                    "expected_impact": "Restore prediction accuracy to validated levels"
                })

        return proposals

    def save_report(self, report: dict[str, Any], run_id: str | None = None) -> str:
        """Save performance report to database."""
        from database.models import LearningRunModel

        run_id = run_id or f"perf_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        with self.repo._get_session() as session:
            obj = LearningRunModel(
                run_id=run_id,
                finished_at=datetime.now(timezone.utc),
                samples_count=report.get("total_predictions", 0),
                accuracy=report.get("accuracy", 0),
                status="COMPLETED",
                summary=json.dumps(report)
            )
            session.add(obj)
            session.commit()
        return run_id