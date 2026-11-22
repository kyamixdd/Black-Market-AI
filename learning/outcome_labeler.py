"""Outcome labeling: evaluates predictions after horizon with simulated transaction costs."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from config import PREDICTION_HORIZON_MINUTES
from database.models import PredictionModel
from database.repositories import Repository
from paper_trading.fee_calculator import FeeCalculator
from paper_trading.simulator import Simulator

logger = logging.getLogger(__name__)


class OutcomeLabeler:
    """Labels prediction outcomes after the prediction horizon completes."""

    def __init__(self, repo: Repository, simulator: Simulator | None = None):
        self.repo = repo
        self.simulator = simulator
        self.fee_calc = FeeCalculator()
        self.horizon_minutes = PREDICTION_HORIZON_MINUTES

    def evaluate_unresolved(self) -> int:
        """Evaluate all unresolved predictions. Returns count evaluated."""
        preds = self.repo.get_unresolved_predictions()
        evaluated = 0

        for pred in preds:
            try:
                outcome = self._evaluate_prediction(pred)
                if outcome:
                    self.repo.update_prediction_outcome(
                        pred.prediction_id,
                        outcome["actual_outcome"],
                        outcome["actual_return_pct"] * 100,
                        outcome["is_correct"],
                        simulated_pnl=outcome["simulated_pnl"],
                        transaction_costs=outcome["transaction_costs"],
                        evaluation_notes=outcome["evaluation_notes"]
                    )
                    evaluated += 1
            except Exception as exc:
                logger.error("Failed to evaluate prediction %s: %s", pred.prediction_id, exc)

        logger.info("Evaluated %d unresolved predictions", evaluated)
        return evaluated

    def _evaluate_prediction(self, pred: PredictionModel) -> dict[str, Any] | None:
        """Evaluate a single prediction's outcome."""
        # Check if enough time has passed
        created_at = pred.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        created_ms = int(created_at.timestamp() * 1000)
        horizon_ms = int(pred.horizon_minutes or self.horizon_minutes) * 60 * 1000
        current_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        if current_ms - created_ms < horizon_ms:
            return None  # Horizon not yet complete

        # Resolve both prices using candles that had fully closed at each
        # target timestamp. The entry is the last close available when the
        # prediction was created; the exit is the last close available at the
        # end of its forecast horizon.
        timeframe = pred.timeframe if pred.timeframe in {"1m", "1h"} else "1m"
        entry_timestamp_ms = created_ms
        exit_timestamp_ms = created_ms + horizon_ms
        entry_price = self._get_price_at_time(
            pred.symbol, pred.market, entry_timestamp_ms, timeframe
        )
        exit_price = self._get_price_at_time(
            pred.symbol, pred.market, exit_timestamp_ms, timeframe
        )

        if entry_price is None or exit_price is None or entry_price <= 0:
            return None

        # Actual market direction must be derived from price movement only,
        # never from the model's predicted class or prediction-side PnL.
        gross_market_return = (exit_price - entry_price) / entry_price
        threshold = 0.002  # 0.2% threshold for UP/DOWN
        if gross_market_return > threshold:
            actual_outcome = "UP"
        elif gross_market_return < -threshold:
            actual_outcome = "DOWN"
        else:
            actual_outcome = "FLAT"

        is_correct = actual_outcome == pred.predicted_class

        # Transaction costs and simulated PnL describe the predicted trade,
        # separately from the actual market-direction label.
        predicted_direction = pred.predicted_class
        costs = self._calculate_costs(
            pred.market, predicted_direction, entry_price, exit_price
        )
        predicted_gross_return = (
            gross_market_return if predicted_direction == "UP"
            else -gross_market_return if predicted_direction == "DOWN"
            else 0.0
        )
        simulated_pnl = predicted_gross_return - (
            costs / entry_price if entry_price > 0 else 0.0
        )
        actual_return_pct = gross_market_return
        eval_notes = (
            f"Entry: {entry_price:.4f}, Exit: {exit_price:.4f}, "
            f"Market Return: {gross_market_return:.4%}, "
            f"Predicted Trade PnL: {simulated_pnl:.4%}"
        )

        return {
            "actual_outcome": actual_outcome,
            "actual_return_pct": actual_return_pct,
            "is_correct": is_correct,
            "transaction_costs": costs / entry_price if entry_price > 0 else 0,
            "simulated_pnl": simulated_pnl,
            "evaluation_notes": eval_notes
        }

    def _get_price_at_time(self, symbol: str, market: str, timestamp_ms: int,
                           timeframe: str = "1m") -> float | None:
        """Get price for symbol at specific timestamp from candles."""
        # Use the prediction's source timeframe when resolving outcomes.
        from database.connection import get_session_maker
        session_maker = get_session_maker()
        from sqlalchemy import select

        from database.models import CandleModel

        with session_maker() as session:
            stmt = (
                select(CandleModel.close)
                .where(
                    CandleModel.symbol == symbol,
                    CandleModel.market == market,
                    CandleModel.timeframe == timeframe,
                    # open_time <= target is insufficient: the candle may
                    # still be forming. Only use candles closed by target.
                    CandleModel.close_time <= timestamp_ms,
                )
                .order_by(CandleModel.close_time.desc())
                .limit(1)
            )
            result = session.execute(stmt).scalar()
            return float(result) if result else None

    def _calculate_costs(self, market: str, direction: str, entry: float, exit: float) -> float:
        """Calculate transaction costs for round trip."""
        if direction == "FLAT":
            return 0.0

        fee_entry = self.fee_calc.calculate(market, "BUY" if direction == "UP" else "SELL", 1.0, entry, 1.0)
        fee_exit = self.fee_calc.calculate(market, "SELL" if direction == "UP" else "BUY", 1.0, exit, 1.0)
        slip_entry = self.fee_calc.calculate_slippage(market, "MARKET", 1.0, entry, 1.0, 1000000.0)
        slip_exit = self.fee_calc.calculate_slippage(market, "MARKET", 1.0, exit, 1.0, 1000000.0)
        return fee_entry + fee_exit + slip_entry + slip_exit

    def _calculate_return_with_costs(self, market: str, direction: str,
                                     entry: float, exit: float, costs: float | None = None) -> float:
        """Calculate return accounting for fees and slippage."""
        if direction == "FLAT":
            return 0.0

        if costs is None:
            costs = self._calculate_costs(market, direction, entry, exit)

        # Gross return
        if direction == "UP":
            gross = (exit - entry) / entry
        else:  # DOWN
            gross = (entry - exit) / entry

        # Net return after costs
        total_cost_pct = costs / entry if entry > 0 else 0.0
        return gross - total_cost_pct
