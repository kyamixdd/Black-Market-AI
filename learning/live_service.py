"""Live market-data bootstrap, inference, outcome labeling, and online updates."""
from __future__ import annotations

import asyncio
import json
import logging
from core.observability import traced_operation
import uuid
from datetime import datetime, timezone
from typing import Any

import joblib
import numpy as np
from river import compose, preprocessing, tree
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

from config import AUTO_MODEL_TRAINING, MODELS_DIR, SCANNER_ANALYSIS_BATCH_SIZE, MIN_VALIDATION_ACCURACY, MIN_VALIDATION_F1
from core.event_models import EventType, make_event
from learning.feature_engine import FeatureEngine
from learning.outcome_labeler import DIRECTIONAL_LABEL_THRESHOLD, OutcomeLabeler
from learning.trainer import ModelTrainer
from learning.walkforward_validator import WalkForwardValidator

logger = logging.getLogger(__name__)


class LiveLearningService:
    """Runs real historical bootstrap, then emits and labels live hourly predictions."""

    def __init__(self, orchestrator):
        self.orch = orchestrator
        self.repo = orchestrator.repo
        self.predictor = orchestrator.intelligence.predictor
        self.features = FeatureEngine()
        self.trainer = ModelTrainer(self.repo)
        self.trainer.validator = WalkForwardValidator(n_splits=3, min_train_size=100)
        self.state = "waiting"
        self.training_samples = 0
        self.last_training_at: str | None = None
        self.last_cycle_status = "waiting"
        self.last_training_result: dict[str, Any] | None = None
        self.river_updates = 0
        self._pairs: list[tuple[str, str]] = []
        self._last_prediction_open: dict[tuple[str, str], int] = {}
        self._river_seen: set[str] = set()
        self._last_retrain_count = 0
        self._river_model = self.predictor.river_model
        self._last_bootstrap_attempt = 0.0

    @traced_operation("learning.service", component="learning")

    async def run(self) -> None:
        self.state = "bootstrapping"
        try:
            await self._bootstrap()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Live model bootstrap failed")
            self.last_training_result = {"status": "error", "reason": str(exc) or type(exc).__name__}
            self.state = "error"
        while self.orch._running:
            try:
                await self._live_cycle()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Live learning cycle failed")
                self.last_cycle_status = "error"
            await asyncio.sleep(60)

    def _choose_pairs(self) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for market in ("SPOT", "FUTURES"):
            snapshots = self.orch.cache.get_market_tickers(market)
            usdt = [s for s in snapshots if str(s.get("symbol", "")).endswith("USDT") and (s.get("volume_24h") or 0) > 0]
            usdt.sort(key=lambda item: float(item.get("volume_24h") or 0), reverse=True)
            for item in usdt[:max(1, min(10, int(SCANNER_ANALYSIS_BATCH_SIZE)))]:
                pairs.append((market, str(item["symbol"])))
        if not pairs:
            pairs = [(market, symbol) for market in ("SPOT", "FUTURES")
                     for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT")
                     if self.orch.registry.is_eligible(symbol, market)]
        return pairs

    @staticmethod
    def _parse_klines(rows: list[list], now_ms: int) -> list[dict[str, float | int]]:
        parsed = []
        for row in rows:
            if len(row) < 7:
                continue
            try:
                candle = {
                    "open_time": int(row[0]), "open": float(row[1]),
                    "high": float(row[2]), "low": float(row[3]),
                    "close": float(row[4]), "volume": float(row[5]),
                    "close_time": int(row[6]),
                }
            except (TypeError, ValueError, OverflowError):
                continue
            numeric = [candle[name] for name in ("open", "high", "low", "close", "volume")]
            if (not all(np.isfinite(value) for value in numeric)
                    or min(numeric) < 0 or candle["open"] <= 0 or candle["low"] <= 0 or candle["close"] <= 0
                    or candle["high"] < max(candle["open"], candle["close"], candle["low"])
                    or candle["low"] > min(candle["open"], candle["close"])):
                continue
            if candle["close_time"] < now_ms:
                parsed.append(candle)
        return sorted(parsed, key=lambda item: item["open_time"])

    @staticmethod
    def _ohlc(candles: list[dict[str, Any]]) -> dict[str, np.ndarray]:
        return {
            name: np.asarray([candle[name] for candle in candles], dtype=np.float32)
            for name in ("open", "high", "low", "close", "volume")
        }

    @traced_operation("learning.historical_data", component="learning")

    async def _fetch_history(self, market: str, symbol: str, limit: int) -> list[dict[str, Any]]:
        client = self.orch.spot_client if market == "SPOT" else self.orch.futures_client
        rows = await client.get_klines(symbol, "1h", limit=limit)
        candles = self._parse_klines(rows, int(datetime.now(timezone.utc).timestamp() * 1000))
        self._cache_candles(market, symbol, candles)
        if candles:
            self.repo.save_candles(symbol, market, "1h", candles[-3:])
        return candles

    def _cache_candles(self, market: str, symbol: str, candles: list[dict[str, Any]]) -> None:
        manager = self.orch.candle_manager
        for candle in candles:
            if not manager.add_candle(
                market, symbol, "1h", candle["open_time"], candle["open"], candle["high"],
                candle["low"], candle["close"], candle["volume"], candle["close_time"],
            ):
                manager.update_current_candle(
                    market, symbol, "1h", candle["open_time"], candle["open"], candle["high"],
                    candle["low"], candle["close"], candle["volume"], candle["close_time"],
                )

    def _bootstrap_samples(self, pairs: list[tuple[str, str]], histories: dict[tuple[str, str], list[dict[str, Any]]], *, include_metadata: bool = False):
        samples: list[tuple[int, np.ndarray, int, float, float, str, str, int]] = []
        cost_labeler = OutcomeLabeler(self.repo)
        for market, symbol in pairs:
            candles = histories.get((market, symbol), [])
            for index in range(50, len(candles) - 1):
                window = candles[max(0, index - 199):index + 1]
                feature = self.features.build_features(symbol, market, {"1h": self._ohlc(window)})
                if feature.shape != (36,) or not np.isfinite(feature).all():
                    continue
                price = float(candles[index]["close"])
                next_price = float(candles[index + 1]["close"])
                forward_return = next_price / price - 1.0
                label = (
                    2 if forward_return > DIRECTIONAL_LABEL_THRESHOLD
                    else 0 if forward_return < -DIRECTIONAL_LABEL_THRESHOLD
                    else 1
                )
                close_time = int(candles[index]["close_time"])
                recent_close = np.asarray([float(item["close"]) for item in candles[max(0, index - 20):index + 1]], dtype=float)
                recent_returns = np.diff(np.log(recent_close)) if len(recent_close) > 1 else np.asarray([], dtype=float)
                trend_return = recent_close[-1] / recent_close[0] - 1.0 if len(recent_close) > 1 and recent_close[0] > 0 else 0.0
                volatility = float(np.std(recent_returns)) if len(recent_returns) else 0.0
                regime = "VOLATILE" if volatility >= 0.015 else "TREND_UP" if trend_return >= 0.02 else "TREND_DOWN" if trend_return <= -0.02 else "RANGE"
                # Fees and slippage are the same round-trip cost calculation used by outcome labeling.
                costs = cost_labeler._calculate_costs(market, "UP", price, next_price) / price
                samples.append((close_time, feature, label, forward_return * 100.0, costs, regime, market, 60))
        samples.sort(key=lambda item: item[0])
        if not samples:
            empty = (np.empty((0, 36), dtype=np.float32), np.empty((0,), dtype=np.int32), np.empty((0,), dtype=np.int64))
            if include_metadata:
                return (*empty, {key: np.array([]) for key in ("timestamps", "actual_return_pct", "transaction_costs", "regimes", "markets", "horizon_minutes")})
            return empty
        X = np.stack([item[1] for item in samples]).astype(np.float32)
        y = np.asarray([item[2] for item in samples], dtype=np.int32)
        timestamps = np.asarray([item[0] + 60 * 60 * 1000 for item in samples], dtype=np.int64)
        metadata = {
            "timestamps": timestamps.copy(),
            "actual_return_pct": np.asarray([item[3] for item in samples], dtype=np.float64),
            "transaction_costs": np.asarray([item[4] for item in samples], dtype=np.float64),
            "regimes": np.asarray([item[5] for item in samples], dtype=object),
            "markets": np.asarray([item[6] for item in samples], dtype=object),
            "horizon_minutes": np.asarray([item[7] for item in samples], dtype=np.int32),
        }
        return (X, y, timestamps, metadata) if include_metadata else (X, y, timestamps)

    @traced_operation("learning.bootstrap_training", component="learning")

    async def _bootstrap(self) -> None:
        self._last_bootstrap_attempt = asyncio.get_running_loop().time()
        for _ in range(20):
            self._pairs = self._choose_pairs()
            if self._pairs:
                break
            await asyncio.sleep(1)
        if not self._pairs:
            self.state = "waiting_for_market_data"
            self.last_cycle_status = "no_eligible_symbols"
            return

        histories: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for market, symbol in self._pairs:
            try:
                histories[(market, symbol)] = await self._fetch_history(market, symbol, 1000)
            except Exception as exc:
                logger.warning("Historical model bootstrap failed for %s %s: %s", market, symbol, exc)
        X, y, timestamps, metadata = self._bootstrap_samples(self._pairs, histories, include_metadata=True)
        self.training_samples = int(len(y))
        if len(y) < 300 or len(np.unique(y)) < 2:
            self.state = "waiting_for_history"
            self.last_cycle_status = f"insufficient_bootstrap_samples:{len(y)}"
            logger.warning("Model bootstrap needs at least 300 usable labeled hourly samples; got %d", len(y))
            return

        self.state = "training"
        self.last_cycle_status = f"validating:{len(y)}_historical_samples"
        result = await asyncio.to_thread(self.trainer.train_and_validate, X, y, timestamps, metadata)
        self.last_training_result = self._training_summary(result)
        if result.get("status") == "trained":
            if self._activate_batch_models(result):
                self.state = "trained"
                self.last_cycle_status = "validated_batch_models_trained_and_activated"
                logger.info("Historical model bootstrap validated and activated on %d samples", len(y))
            else:
                self.state = "validation_failed"
                self.last_cycle_status = "batch_model_activation_failed"
                self.last_training_result = {
                    **self.last_training_result,
                    "status": "activation_failed",
                    "reason": "validated candidates were not activated; existing champion remains unchanged",
                }
        else:
            river_result = await asyncio.to_thread(self._train_validate_river, X, y, timestamps)
            if river_result.get("passes", False) and river_result.get("model") is not None:
                # River's simple holdout accuracy/F1 is not the comprehensive
                # promotion evidence required for automated activation. Keep it
                # registered as an inactive candidate; never bypass the shared
                # cost-aware champion gate.
                self.repo.save_model_registry({
                    "version": river_result["version"], "model_type": "river",
                    "metrics": river_result["metrics"],
                    "file_path": str(river_result["path"]),
                    "status": "CANDIDATE", "is_active": False, "is_champion": False,
                })
                self.state = "validation_failed"
                self.last_cycle_status = "river_candidate_held_unpromoted_comprehensive_gate_required"
                self.last_training_result = {
                    "status": "validation_failed",
                    "reason": "river_candidate_held_unpromoted_comprehensive_gate_required",
                    "validation": self._validation_summary(result.get("validation")),
                    "river_metrics": river_result.get("metrics"),
                    "holdout_report": river_result.get("holdout_report"),
                }
            else:
                self.state = "validation_failed"
                reason = river_result.get("reason", result.get("status", "training_failed"))
                self.last_cycle_status = f"all_models_rejected:{reason}"
                self.last_training_result = {
                    "status": "validation_failed",
                    "reason": reason,
                    "validation": self._validation_summary(result.get("validation")),
                    "river_metrics": river_result.get("metrics"),
                    "holdout_report": river_result.get("holdout_report"),
                }
        self.last_training_at = datetime.now(timezone.utc).isoformat()
        self._river_seen.update(
            prediction.prediction_id
            for prediction in self.repo.get_predictions_history(10000)
            if prediction.is_correct is not None
        )
        await self._predict_latest(histories)

    @staticmethod
    def _validation_summary(validation: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(validation, dict):
            return None
        gate = validation.get("promotion_gate") or {}
        models = gate.get("models") or {}
        criteria = gate.get("criteria") or {}
        return {
            "promotion_gate": {
                "passes": gate.get("passes"),
                "failure_reasons": list(gate.get("failure_reasons") or []),
                "criteria": criteria,
                "models": {
                    name: {
                        "passes": (models.get(name) or {}).get("passes"),
                        "mean_f1": (models.get(name) or {}).get("mean_f1"),
                        "mean_accuracy": (models.get(name) or {}).get("mean_accuracy"),
                        "calibration_score": (models.get(name) or {}).get("calibration_score"),
                        "fold_count": (models.get(name) or {}).get("fold_count"),
                        "failure_reasons": list((models.get(name) or {}).get("failure_reasons") or []),
                        "economic_evidence": (gate.get("economic_evidence") or {}).get(name),
                    }
                    for name in ("rf", "xgb")
                },
            },
            "models": {
                name: {
                    "valid": (validation.get(name) or {}).get("valid"),
                    "reason": (validation.get(name) or {}).get("reason"),
                    "primary_metric": (validation.get(name) or {}).get("primary_metric"),
                    "primary_value": ((validation.get(name) or {}).get("aggregated") or {}).get("mean_f1"),
                    "aggregated": (validation.get(name) or {}).get("aggregated"),
                    "folds": [
                        {key: fold.get(key) for key in (
                            "fold", "train_size", "test_size", "purged_samples",
                            "accuracy", "precision_macro", "recall_macro", "f1_macro",
                            "calibration_score", "train_start_time", "train_end_time",
                            "test_start_time", "test_end_time",
                        ) if key in fold}
                        for fold in ((validation.get(name) or {}).get("folds") or [])
                    ],
                }
                for name in ("rf", "xgb")
            },
            "validation_provenance": gate.get("validation_provenance"),
        }

    @classmethod
    def _training_summary(cls, result: dict[str, Any]) -> dict[str, Any]:
        validation = result.get("validation")
        gate = validation.get("promotion_gate", {}) if isinstance(validation, dict) else {}
        return {
            "status": result.get("status", "unknown"),
            "reason": result.get("reason"),
            "samples": result.get("samples"),
            "version": result.get("version"),
            "metrics": result.get("metrics"),
            "validation": cls._validation_summary(validation),
            "failure_reasons": list(gate.get("failure_reasons") or []),
        }

    def _train_validate_river(self, X: np.ndarray, y: np.ndarray, timestamps: np.ndarray | None = None) -> dict[str, Any]:
        """Evaluate a frozen River model on a purged, chronological holdout."""
        if len(X) < 100 or len(np.unique(y)) < 2:
            return {"passes": False, "reason": "insufficient_validation_history"}
        split = max(1, int(len(X) * 0.8))
        train_end = split
        if timestamps is not None and len(timestamps) == len(X):
            timestamps = np.asarray(timestamps)
            if timestamps.ndim != 1 or any(timestamps[i] > timestamps[i + 1] for i in range(len(timestamps) - 1)):
                return {"passes": False, "reason": "timestamps_not_chronological"}
            cutoff = int(timestamps[split]) - 60 * 60 * 1000
            train_end = int(np.searchsorted(timestamps, cutoff, side="left"))
            if train_end < 100 or train_end >= split:
                return {"passes": False, "reason": "insufficient_purged_chronological_training"}
            split = train_end
        model = compose.Pipeline(
            ("scaler", preprocessing.StandardScaler()),
            ("model", tree.HoeffdingTreeClassifier(grace_period=100, delta=1e-5, tau=0.05)),
        )
        for features, label in zip(X[:split], y[:split]):
            model.learn_one(dict(enumerate(features.tolist())), int(label))
        predictions = []
        actual = []
        # Keep the full holdout untouched: do not update the candidate with any
        # held-out labels, so every prediction is produced by training data only.
        for features, label in zip(X[split:], y[split:]):
            prediction = model.predict_one(dict(enumerate(features.tolist())))
            if prediction is not None:
                predictions.append(int(prediction))
                actual.append(int(label))
        if not actual:
            return {"passes": False, "reason": "empty_holdout"}
        accuracy = float(accuracy_score(actual, predictions))
        f1 = float(f1_score(actual, predictions, average="macro", zero_division=0))
        precision = float(precision_score(actual, predictions, labels=[0, 1, 2], average="macro", zero_division=0))
        recall = float(recall_score(actual, predictions, labels=[0, 1, 2], average="macro", zero_division=0))
        metrics = {
            "samples": int(len(X)), "train_samples": int(split),
            "holdout_samples": len(actual), "accuracy": accuracy,
            "precision_macro": precision, "recall_macro": recall, "f1_macro": f1,
            "validation_method": "purged_chronological_80_20_frozen_holdout",
            "holdout_untouched": True,
            "purge_gap_ms": 60 * 60 * 1000 if timestamps is not None and len(timestamps) == len(X) else 0,
            "train_end_timestamp": int(timestamps[split - 1]) if timestamps is not None and len(timestamps) == len(X) else None,
            "holdout_start_timestamp": int(timestamps[split]) if timestamps is not None and len(timestamps) == len(X) else None,
            "holdout_end_timestamp": int(timestamps[-1]) if timestamps is not None and len(timestamps) == len(X) else None,
            "thresholds": {"accuracy_min": MIN_VALIDATION_ACCURACY, "f1_macro_min": MIN_VALIDATION_F1},
            "failure_reasons": [
                reason for failed, reason in (
                    (accuracy < MIN_VALIDATION_ACCURACY, f"accuracy {accuracy:.6f} below required {MIN_VALIDATION_ACCURACY:.6f}"),
                    (f1 < MIN_VALIDATION_F1, f"macro F1 {f1:.6f} below required {MIN_VALIDATION_F1:.6f}"),
                ) if failed
            ],
        }
        passes = accuracy >= MIN_VALIDATION_ACCURACY and f1 >= MIN_VALIDATION_F1
        if not passes:
            return {"passes": False, "reason": "holdout_threshold_not_met", "metrics": metrics, "holdout_report": metrics}
        version = f"river_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        path = MODELS_DIR / f"{version}.pkl"
        temporary = path.with_suffix(".tmp")
        joblib.dump(model, temporary)
        temporary.replace(path)
        return {"passes": True, "model": model, "version": version, "path": path, "metrics": metrics, "holdout_report": metrics}

    def _activate_batch_models(self, result: dict[str, Any]) -> bool:
        version = result.get("version")
        validation = result.get("validation") or {}
        gate = validation.get("promotion_gate") or {}
        if not version or not ModelTrainer._promotion_evidence_passes(gate):
            logger.error("Batch activation blocked: no complete out-of-sample promotion evidence")
            return False
        versions = [f"random_forest_{version}", f"xgboost_{version}"]
        if not self.repo.promote_models(versions):
            logger.error("Batch activation rejected by repository; models remain inactive")
            return False
        self.trainer._update_latest_symlinks(version)
        self.predictor._load_latest()
        return True

    @traced_operation("learning.prediction", component="learning")

    async def _predict_latest(self, histories: dict[tuple[str, str], list[dict[str, Any]]]) -> None:
        for market, symbol in self._pairs:
            candles = histories.get((market, symbol), [])
            if candles:
                await self._record_prediction(market, symbol, candles)

    @traced_operation("learning.live_inference_learning", component="learning")

    async def _live_cycle(self) -> None:
        if not self._pairs or (
            self.state in {"waiting_for_history", "error", "validation_failed"}
            and asyncio.get_running_loop().time() - self._last_bootstrap_attempt >= 900
        ):
            await self._bootstrap()
            if not self._pairs:
                self.last_cycle_status = "waiting_for_eligible_symbols"
                return
        self.last_cycle_status = "collecting_live_hourly_candles"
        histories: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for market, symbol in self._pairs:
            try:
                candles = await self._fetch_history(market, symbol, 3)
                if candles:
                    histories[(market, symbol)] = candles
                    series = self.orch.candle_manager.get_series(market, symbol, "1h", limit=200)
                    if series:
                        await self._record_prediction(market, symbol, series)
            except Exception as exc:
                logger.warning("Live hourly candle update failed for %s %s: %s", market, symbol, exc)

        labeler = OutcomeLabeler(self.repo, self.orch.simulator)
        labeled = labeler.evaluate_unresolved()
        online_updates = self._learn_resolved_predictions()
        self.last_cycle_status = f"live_ok:labeled={labeled}:online_updates={online_updates}"
        if online_updates and self._river_model is not None:
            self._persist_river()

        resolved_count = sum(
            1 for prediction in self.repo.get_predictions_history(10000)
            if prediction.is_correct is not None
        )
        if (AUTO_MODEL_TRAINING and resolved_count >= 500
                and resolved_count - self._last_retrain_count >= 100):
            await self._retrain_from_live_outcomes(resolved_count)

    @traced_operation("learning.prediction_record", component="learning")

    async def _record_prediction(self, market: str, symbol: str, candles: list[dict[str, Any]]) -> None:
        closed = [candle for candle in candles if int(candle["close_time"]) < int(datetime.now(timezone.utc).timestamp() * 1000)]
        if len(closed) < 50:
            return
        candle = closed[-1]
        key = (market, symbol)
        open_time = int(candle["open_time"])
        if self._last_prediction_open.get(key) == open_time:
            return
        series = [item for item in candles if int(item["close_time"]) <= int(candle["close_time"])] [-200:]
        feature = self.features.build_features(symbol, market, {"1h": self._ohlc(series)})
        if feature.shape != (36,) or not np.isfinite(feature).all():
            return
        prediction = self.predictor.predict(feature)
        created_at = datetime.fromtimestamp((int(candle["close_time"]) + 1) / 1000, timezone.utc)
        prediction_id = f"live:{market}:{symbol}:1h:{open_time}"
        self.repo.save_prediction({
            "prediction_id": prediction_id,
            "symbol": symbol,
            "market": market,
            "timeframe": "1h",
            "model_version": str(prediction.get("model_version") or "untrained")[:32],
            "strategy_version": "live_hourly_ensemble",
            "regime": "UNKNOWN",
            "horizon_minutes": 60,
            "prob_up": float(prediction["prob_up"]),
            "prob_down": float(prediction["prob_down"]),
            "prob_flat": float(prediction["prob_flat"]),
            "predicted_class": str(prediction["predicted_class"]),
            "confidence": float(prediction["confidence"]),
            "feature_values": json.dumps(feature.tolist()),
            "created_at": created_at,
        })
        self._last_prediction_open[key] = open_time

    @traced_operation("learning.online_learning", component="learning")

    def _learn_resolved_predictions(self) -> int:
        if self._river_model is None:
            self._river_model = compose.Pipeline(
                ("scale", preprocessing.StandardScaler()),
                ("model", tree.HoeffdingTreeClassifier(grace_period=50, delta=1e-4)),
            )
        updates = 0
        for prediction in self.repo.get_predictions_history(10000):
            if prediction.is_correct is None or prediction.prediction_id in self._river_seen or not prediction.feature_values:
                continue
            try:
                values = np.asarray(json.loads(prediction.feature_values), dtype=np.float32)
                if values.ndim != 1 or not np.isfinite(values).all():
                    continue
                label = {"DOWN": 0, "FLAT": 1, "UP": 2}.get(prediction.actual_outcome, 1)
                self._river_model.learn_one(dict(enumerate(values.tolist())), label)
                self._river_seen.add(prediction.prediction_id)
                updates += 1
            except Exception:
                logger.exception("Unable to apply online update for prediction %s", prediction.prediction_id)
        if updates:
            self.river_updates += updates
        return updates

    def _persist_river(self) -> None:
        path = MODELS_DIR / "river_live.pkl"
        temporary = path.with_suffix(".tmp")
        joblib.dump(self._river_model, temporary)
        temporary.replace(path)
        self.repo.save_model_registry({
            "version": "river_live",
            "model_type": "river",
            "metrics": {"online_updates": self.river_updates, "samples": self.training_samples},
            "file_path": str(path),
            "status": "CANDIDATE",
            "is_active": False,
            "is_champion": False,
        })
        # Online River updates are experimental candidates. They cannot activate
        # or replace a champion without the same purged OOF promotion gate.

    @traced_operation("learning.retraining", component="learning")

    async def _retrain_from_live_outcomes(self, resolved_count: int) -> None:
        self.last_cycle_status = f"retraining_from_{resolved_count}_resolved_predictions"
        result = await asyncio.to_thread(self.trainer.train_and_validate)
        self._last_retrain_count = resolved_count
        if result.get("status") == "trained":
            if self._activate_batch_models(result):
                self.state = "trained"
                self.last_training_at = datetime.now(timezone.utc).isoformat()
                await self.orch.event_bus.publish(make_event(
                    EventType.MODEL_TRAINED, "learning_service",
                    version=result.get("version"), samples=resolved_count,
                ))
                self.last_cycle_status = "live_retrain_validated_and_activated"
            else:
                self.last_cycle_status = "live_retrain_activation_failed_existing_champion_unchanged"
        else:
            self.last_cycle_status = f"live_retrain_not_activated:{result.get('status', 'unknown')}"

