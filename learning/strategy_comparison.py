"""Leakage-aware walk-forward comparison of trading strategies."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from learning.confidence_gate import select_confidence_threshold


STRATEGY_NAMES = (
    "Buy-and-hold",
    "Rule-based",
    "Random Forest",
    "XGBoost",
    "Hybrid ML",
)


def compare_strategies(candles: list[dict[str, Any]], fee_rate: float = 0.0004, timeframe: str = "1h") -> dict[str, Any]:
    """Compare strategies on one chronologically ordered candle series.

    Feature row t uses candles through t. Its target is the direction of close
    t+1. Models are refit on expanding historical windows and predict only
    subsequent unseen rows. Each strategy's signal at t earns candle t+1 return.
    A fee is charged on each position change; B&H pays entry and exit costs.
    """
    if not 0 <= fee_rate < 0.1:
        raise ValueError("fee_rate must be between 0 and 0.1")
    frame = pd.DataFrame(candles)
    required = {"open_time", "close", "volume"}
    if not required.issubset(frame.columns):
        return {"status": "insufficient_data", "reason": "missing_candle_fields", "strategies": []}
    frame = frame.sort_values("open_time").drop_duplicates("open_time").reset_index(drop=True)
    close = pd.to_numeric(frame["close"], errors="coerce").to_numpy(dtype=float)
    volume = pd.to_numeric(frame["volume"], errors="coerce").to_numpy(dtype=float)
    if len(close) < 180 or not np.isfinite(close).all() or np.any(close <= 0):
        return {"status": "insufficient_data", "minimum_candles": 180, "candles": len(close), "strategies": []}

    returns = np.zeros(len(close), dtype=float)
    returns[1:] = close[1:] / close[:-1] - 1.0
    features = _make_features(close, volume)
    # Align label with the *next* candle return: feature row t predicts t+1.
    target = np.zeros(len(close), dtype=int)
    target[:-1] = (returns[1:] > 0).astype(int)
    valid_start = 60
    feature_rows = np.arange(valid_start, len(close) - 1)
    # The next candle's return is the outcome for a signal formed at row t.
    test_start = max(valid_start + 100, int(len(feature_rows) * 0.45) + valid_start)
    test_indices = feature_rows[feature_rows >= test_start]
    if len(test_indices) < 30:
        return {"status": "insufficient_data", "reason": "too_short_for_walk_forward", "candles": len(close), "strategies": []}

    rf_signal = np.zeros(len(close), dtype=float)
    xgb_signal = np.zeros(len(close), dtype=float)
    rf_prob = np.full(len(close), 0.5)
    xgb_prob = np.full(len(close), 0.5)
    hybrid_threshold = np.full(len(close), 1.01)
    fold_count = 0
    # Use sequential expanding folds. Training targets end strictly before
    # the test block; no row from a test block is included in its fit.
    blocks = np.array_split(test_indices, min(4, max(1, len(test_indices) // 30)))
    for block in blocks:
        if not len(block):
            continue
        first_test = int(block[0])
        train_idx = feature_rows[feature_rows < first_test]
        if len(train_idx) < 100 or len(np.unique(target[train_idx])) < 2:
            continue
        rf = RandomForestClassifier(
            n_estimators=120, max_depth=8, min_samples_leaf=4,
            random_state=42, n_jobs=1, class_weight="balanced",
        )
        xgb = XGBClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.04,
            subsample=0.9, colsample_bytree=0.9, reg_lambda=2.0,
            random_state=42, n_jobs=1, eval_metric="logloss",
        )
        # Tune thresholds on an earlier calibration slice, never on this test block.
        calibration_size = max(30, int(len(train_idx) * 0.2))
        calibration_idx = train_idx[-calibration_size:]
        fit_idx = train_idx[: max(0, len(train_idx) - calibration_size - 1)]
        if len(fit_idx) < 100 or len(calibration_idx) < 20:
            continue
        rf_cal = RandomForestClassifier(
            n_estimators=100, max_depth=8, min_samples_leaf=4,
            random_state=42, n_jobs=1, class_weight="balanced",
        )
        xgb_cal = XGBClassifier(
            n_estimators=90, max_depth=4, learning_rate=0.04,
            subsample=0.9, colsample_bytree=0.9, reg_lambda=2.0,
            random_state=42, n_jobs=1, eval_metric="logloss",
        )
        rf_cal.fit(features[fit_idx], target[fit_idx])
        xgb_cal.fit(features[fit_idx], target[fit_idx])
        rf_cal_prob = _positive_probability(rf_cal, features[calibration_idx])
        xgb_cal_prob = _positive_probability(xgb_cal, features[calibration_idx])
        calibration_returns = returns[calibration_idx + 1]
        rf_threshold = select_confidence_threshold(
            rf_cal_prob, calibration_returns, fee_rate=fee_rate, min_trades=10,
        )["threshold"]
        xgb_threshold = select_confidence_threshold(
            xgb_cal_prob, calibration_returns, fee_rate=fee_rate, min_trades=10,
        )["threshold"]
        hybrid_cal_prob = (rf_cal_prob + xgb_cal_prob) / 2.0
        hybrid_threshold_for_fold = select_confidence_threshold(
            hybrid_cal_prob, calibration_returns, fee_rate=fee_rate, min_trades=10,
        )["threshold"]

        # Refit with all prior rows, then score only the unseen fold.
        rf.fit(features[train_idx], target[train_idx])
        xgb.fit(features[train_idx], target[train_idx])
        rf_prob[block] = _positive_probability(rf, features[block])
        xgb_prob[block] = _positive_probability(xgb, features[block])
        rf_conf = np.maximum(rf_prob[block], 1.0 - rf_prob[block])
        xgb_conf = np.maximum(xgb_prob[block], 1.0 - xgb_prob[block])
        rf_signal[block] = np.where(
            rf_conf >= rf_threshold, np.where(rf_prob[block] >= 0.5, 1.0, -1.0), 0.0,
        )
        xgb_signal[block] = np.where(
            xgb_conf >= xgb_threshold, np.where(xgb_prob[block] >= 0.5, 1.0, -1.0), 0.0,
        )
        hybrid_threshold[block] = hybrid_threshold_for_fold
        fold_count += 1

    # A crossover strategy uses only rolling means available at close t.
    fast = pd.Series(close).rolling(12, min_periods=12).mean().to_numpy()
    slow = pd.Series(close).rolling(36, min_periods=36).mean().to_numpy()
    rule_signal = np.where(fast > slow, 1.0, np.where(fast < slow, -1.0, 0.0))
    rule_signal[:valid_start] = 0.0

    # Hybrid combines model probabilities with a conservative rule filter.
    hybrid_prob = (rf_prob + xgb_prob) / 2.0
    hybrid_conf = np.maximum(hybrid_prob, 1.0 - hybrid_prob)
    hybrid_signal = np.where(
        (hybrid_conf >= hybrid_threshold) & (hybrid_prob >= 0.5) & (rule_signal > 0), 1.0,
        np.where((hybrid_conf >= hybrid_threshold) & (hybrid_prob < 0.5) & (rule_signal < 0), -1.0, 0.0),
    )

    evaluation_start = int(test_indices[0])
    eval_returns = returns[evaluation_start + 1:]
    signals = {
        "Buy-and-hold": np.ones(len(eval_returns), dtype=float),
        "Rule-based": rule_signal[evaluation_start:-1],
        "Random Forest": rf_signal[evaluation_start:-1],
        "XGBoost": xgb_signal[evaluation_start:-1],
        "Hybrid ML": hybrid_signal[evaluation_start:-1],
    }
    # Only the later walk-forward evaluation interval is scored. Model
    # strategies stay flat where no fold produced an out-of-sample prediction.
    results = []
    for name in STRATEGY_NAMES:
        signal = signals[name]
        pnl = signal * eval_returns
        changes = np.abs(np.diff(np.concatenate(([0.0], signal))))
        costs = changes * fee_rate
        if name == "Buy-and-hold":
            costs[-1:] += fee_rate  # exit fee at evaluation end
        net = pnl - costs
        results.append(_metrics(name, net, signal, eval_returns, timeframe))
    return {
        "status": "ok",
        "symbol": str(frame.iloc[0].get("symbol", "")),
        "market": str(frame.iloc[0].get("market", "")),
        "timeframe": str(frame.iloc[0].get("timeframe", "")),
        "candles": len(close),
        "evaluation_start_time": str(frame.iloc[evaluation_start]["open_time"]),
        "evaluation_end_time": str(frame.iloc[-1]["open_time"]),
        "walk_forward_folds": fold_count,
        "confidence_filter": "RF, XGBoost, and Hybrid thresholds selected per fold from prior chronological calibration outcomes using net expectancy after fees; insufficient calibration disables trades",
        "training_policy": "expanding chronological folds; fit labels strictly before each test fold",
        "cost_policy": f"fixed fee {fee_rate * 100:.4f}% per position change; no slippage/funding modeled",
        "strategies": results,
    }


def _make_features(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    frame = pd.DataFrame({"close": close, "volume": volume})
    features = []
    for lag in (1, 2, 3, 5, 10, 20):
        features.append(frame["close"].pct_change(lag).replace([np.inf, -np.inf], np.nan).fillna(0).to_numpy())
    features.extend([
        frame["close"].rolling(5).mean().div(frame["close"]).sub(1).fillna(0).to_numpy(),
        frame["close"].rolling(20).mean().div(frame["close"]).sub(1).fillna(0).to_numpy(),
        frame["close"].pct_change().rolling(20).std().fillna(0).to_numpy(),
        frame["volume"].div(frame["volume"].rolling(20).mean()).replace([np.inf, -np.inf], np.nan).fillna(1).to_numpy(),
    ])
    matrix = np.column_stack(features).astype(np.float32)
    return np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)


def _positive_probability(model: Any, X: np.ndarray) -> np.ndarray:
    probabilities = model.predict_proba(X)
    classes = list(model.classes_)
    if 1 not in classes:
        return np.zeros(len(X), dtype=float)
    return probabilities[:, classes.index(1)]


def _metrics(name: str, net_returns: np.ndarray, signal: np.ndarray, gross_returns: np.ndarray, timeframe: str) -> dict[str, Any]:
    if len(net_returns) == 0:
        return {"strategy": name, "status": "insufficient_data"}
    equity = np.cumprod(1.0 + net_returns)
    total_return = (float(equity[-1]) - 1.0) * 100.0
    peaks = np.maximum.accumulate(np.concatenate(([1.0], equity)))[1:]
    drawdowns = (peaks - equity) / np.maximum(peaks, 1e-12)
    volatility = float(np.std(net_returns, ddof=1)) if len(net_returns) > 1 else 0.0
    seconds_per_bar = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}.get(timeframe, 3600)
    bars_per_year = 365.0 * 86400.0 / seconds_per_bar
    sharpe = float(np.mean(net_returns) / volatility * np.sqrt(bars_per_year)) if volatility > 0 else None
    active = signal != 0
    previous = np.concatenate(([0.0], signal[:-1]))
    trade_count = int(np.count_nonzero((signal != 0) & ((previous == 0) | (np.sign(previous) != np.sign(signal)))))
    winning = net_returns[active & (net_returns > 0)]
    losing = net_returns[active & (net_returns < 0)]
    gross_profit = float(winning.sum())
    gross_loss = abs(float(losing.sum()))
    factor = gross_profit / gross_loss if gross_loss else (None if gross_profit == 0 else "infinite")
    return {
        "strategy": name,
        "status": "evaluated",
        "total_return_pct": total_return,
        "max_drawdown_pct": float(np.max(drawdowns) * 100.0) if len(drawdowns) else 0.0,
        "sharpe_ratio": sharpe,
        "win_rate_pct": float(len(winning) / max(1, len(winning) + len(losing)) * 100.0),
        "profit_factor": factor,
        "trades_evaluated": trade_count,
        "evaluation_bars": len(net_returns),
    }
