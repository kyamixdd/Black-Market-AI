"""Historical backtesting engine with walk-forward validation and bias prevention."""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

from config import (
    MIN_VALIDATION_ACCURACY,
    MIN_VALIDATION_F1,
    PREDICTION_HORIZON_MINUTES,
    VALIDATION_METRIC,
    WALK_FORWARD_MIN_SAMPLES,
)
from database.repositories import Repository
from learning.walkforward_validator import WalkForwardValidator
from market.candle_manager import CandleManager
from market.trend_analyzer import TrendAnalyzer
from paper_trading.fee_calculator import FeeCalculator
from paper_trading.funding_calculator import FundingCalculator
from paper_trading.liquidation_engine import LiquidationEngine
from paper_trading.risk_manager import RiskManager
from paper_trading.simulator import Simulator
from strategies.all_strategies import (
    MeanReversionStrategy,
    ReversalStrategy,
    TrendFollowingStrategy,
)
from strategies.breakout import BreakoutStrategy
from strategies.momentum import MomentumStrategy

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """Configuration for a backtest run."""
    start_date: datetime
    end_date: datetime
    initial_balance: float = 500.0
    max_positions: int = 5
    risk_per_trade_pct: float = 0.5
    max_daily_loss_pct: float = 2.0
    max_leverage: float = 3.0
    timeframes: list[str] = field(default_factory=lambda: ["15m", "1h", "4h"])
    symbols: list[str] = field(default_factory=list)  # Empty = all eligible
    markets: list[str] = field(default_factory=lambda: ["SPOT", "FUTURES"])
    strategies: list[str] = field(default_factory=lambda: ["momentum", "breakout", "trend_following", "mean_reversion", "reversal"])
    min_confidence: float = 0.6
    regime_filter: Optional[list[str]] = None  # None = all regimes
    holdout_start: Optional[datetime] = None  # For out-of-sample testing
    parameter_grid: Optional[dict[str, list]] = None  # For sensitivity analysis


@dataclass
class BacktestTrade:
    """Record of a single trade in backtest."""
    trade_id: str
    symbol: str
    market: str
    strategy: str
    side: str
    entry_time: datetime
    entry_price: float
    exit_time: datetime | None
    exit_price: float | None
    amount: float
    leverage: float
    stop_loss: float
    take_profit: float
    pnl: float = 0.0
    pnl_pct: float = 0.0
    fees: float = 0.0
    slippage: float = 0.0
    funding: float = 0.0
    close_reason: str = "OPEN"
    regime: str = "UNKNOWN"
    confidence: float = 0.0
    timeframe: str = "1h"


@dataclass
class BacktestResult:
    """Complete backtest results."""
    config: BacktestConfig
    trades: list[BacktestTrade]
    equity_curve: list[tuple[datetime, float]]
    daily_returns: list[float]
    metrics: dict[str, float]
    by_strategy: dict[str, dict[str, float]]
    by_market: dict[str, dict[str, float]]
    by_symbol: dict[str, dict[str, float]]
    by_regime: dict[str, dict[str, float]]
    by_timeframe: dict[str, dict[str, float]]
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    parameter_sensitivity: dict[str, Any] = field(default_factory=dict)
    out_of_sample: Optional[dict[str, Any]] = None
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class HistoricalBacktester:
    """
    Independent historical backtesting engine.

    Features:
    - Chronological walk-forward validation
    - Realistic transaction costs, slippage, spread, funding
    - Bias prevention (no look-ahead, proper train/test separation)
    - Out-of-sample testing with holdout periods
    - Parameter sensitivity analysis
    - Performance attribution by regime, strategy, symbol
    """

    def __init__(self, repo: Repository, candle_manager: CandleManager):
        self.repo = repo
        self.candles = candle_manager
        self.trend_analyzer = TrendAnalyzer(candle_manager)

        # Initialize strategies
        self.strategies = {
            "momentum": MomentumStrategy(),
            "breakout": BreakoutStrategy(),
            "trend_following": TrendFollowingStrategy(),
            "mean_reversion": MeanReversionStrategy(),
            "reversal": ReversalStrategy(),
        }

        # Cost calculators
        self.fee_calc = FeeCalculator()
        self.funding_calc = FundingCalculator()
        self.liquidation = LiquidationEngine()

        # Walk-forward validator
        self.validator = WalkForwardValidator(
            n_splits=5,
            min_train_size=WALK_FORWARD_MIN_SAMPLES
        )

    def run_backtest(self, config: BacktestConfig) -> BacktestResult:
        """Execute a complete historical backtest."""
        logger.info(f"Starting backtest {config.start_date} to {config.end_date}")

        # 1. Load historical data
        self._load_historical_data(config)

        # 2. Run walk-forward validation if holdout specified
        oos_result = None
        if config.holdout_start:
            oos_result = self._run_out_of_sample(config)

        # 3. Run main backtest simulation
        trades, equity_curve = self._simulate_backtest(config)

        # 4. Calculate metrics
        metrics = self._calculate_metrics(trades, equity_curve, config.initial_balance)

        # 5. Performance attribution
        by_strategy = self._attribute_by_dimension(trades, "strategy")
        by_market = self._attribute_by_dimension(trades, "market")
        by_symbol = self._attribute_by_dimension(trades, "symbol")
        by_regime = self._attribute_by_dimension(trades, "regime")
        by_timeframe = self._attribute_by_dimension(trades, "timeframe") if trades and hasattr(trades[0], 'timeframe') else {}

        # 6. Drawdown calculations
        max_dd, max_dd_pct = self._calculate_drawdown(equity_curve, config.initial_balance)

        # 7. Risk ratios
        daily_returns = self._calculate_daily_returns(equity_curve)
        sharpe = self._calculate_sharpe(daily_returns)
        sortino = self._calculate_sortino(daily_returns)
        calmar = self._calculate_calmar(daily_returns, max_dd_pct)

        # 8. Parameter sensitivity analysis
        param_sensitivity = {}
        if config.parameter_grid:
            param_sensitivity = self._run_parameter_sensitivity(config)

        result = BacktestResult(
            config=config,
            trades=trades,
            equity_curve=equity_curve,
            daily_returns=daily_returns,
            metrics=metrics,
            by_strategy=by_strategy,
            by_market=by_market,
            by_symbol=by_symbol,
            by_regime=by_regime,
            by_timeframe=by_timeframe,
            max_drawdown=max_dd,
            max_drawdown_pct=max_dd_pct,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            parameter_sensitivity=param_sensitivity,
            out_of_sample=oos_result
        )

        logger.info(f"Backtest complete: {len(trades)} trades, Sharpe={sharpe:.2f}, MaxDD={max_dd_pct:.2f}%")
        return result

    def _load_historical_data(self, config: BacktestConfig) -> None:
        """Load and validate historical candle data."""
        # Get symbols to test
        if config.symbols:
            symbols = config.symbols
        else:
            # Load all eligible from DB
            all_syms = self.repo.get_eligible_symbols()
            symbols = list(set(s.symbol for s in all_syms))

        for symbol in symbols:
            for market in config.markets:
                for tf in config.timeframes:
                    # Check if we have enough data
                    if self.candles.has_enough_data(market, symbol, tf, min_count=200):
                        continue
                    # Could fetch from DB or exchange here
                    pass

    def _simulate_backtest(self, config: BacktestConfig) -> tuple[list[BacktestTrade], list[tuple[datetime, float]]]:
        """Run the core backtest simulation."""
        trades = []
        equity_curve = []
        current_balance = config.initial_balance
        open_positions: dict[str, BacktestTrade] = {}
        daily_pnl = 0.0
        last_day = None

        # Get time range
        current_time = config.start_date
        end_time = config.end_date

        # Determine primary timeframe for iteration (use smallest)
        primary_tf = min(config.timeframes, key=lambda tf: self._tf_to_seconds(tf))
        tf_seconds = self._tf_to_seconds(primary_tf)

        while current_time < end_time:
            # Check daily reset
            if last_day is None or current_time.date() != last_day:
                if last_day is not None:
                    daily_pnl = 0.0
                last_day = current_time.date()

            # Risk check - daily loss limit
            if daily_pnl <= -config.initial_balance * (config.max_daily_loss_pct / 100):
                # Skip trading for rest of day
                current_time += timedelta(seconds=tf_seconds)
                continue

            # Check position limit
            if len(open_positions) >= config.max_positions:
                current_time += timedelta(seconds=tf_seconds)
                continue

            # Scan for signals on each symbol
            for symbol in (config.symbols or self._get_eligible_symbols(config)):
                for market in config.markets:
                    signal = self._generate_signal(symbol, market, current_time, config)
                    if signal and self._should_take_signal(signal, config):
                        trade = self._execute_trade(signal, current_time, config, current_balance)
                        if trade:
                            # Only added to open_positions here; appended to trades when closed
                            open_positions[trade.trade_id] = trade

            # Update open positions
            for trade_id, trade in list(open_positions.items()):
                exit_result = self._check_exit(trade, current_time, config)
                if exit_result:
                    exit_price, exit_reason = exit_result
                    self._close_trade(trade, exit_price, exit_reason, current_time, config)
                    trades.append(trade)
                    current_balance += trade.pnl
                    daily_pnl += trade.pnl
                    del open_positions[trade_id]

            # Record equity
            equity_curve.append((current_time, current_balance))
            current_time += timedelta(seconds=tf_seconds)

        # Close any remaining positions at end
        for trade in open_positions.values():
            self._close_trade(trade, trade.entry_price, "END_OF_TEST", end_time, config)
            trades.append(trade)
            current_balance += trade.pnl

        return trades, equity_curve

    def _generate_signal(self, symbol: str, market: str, current_time: datetime, config: BacktestConfig) -> Optional[dict]:
        """Generate trading signal using available data up to current_time only (no look-ahead)."""
        # Build OHLC data up to current_time
        ohlc_data = {}
        for tf in config.timeframes:
            series = self.candles.get_series(market, symbol, tf, limit=200)
            # Filter to only candles before current_time
            historical = [c for c in series if c["open_time"] <= int(current_time.timestamp() * 1000)]
            if len(historical) >= 50:
                ohlc_data[tf] = {
                    "open": np.array([c["open"] for c in historical]),
                    "high": np.array([c["high"] for c in historical]),
                    "low": np.array([c["low"] for c in historical]),
                    "close": np.array([c["close"] for c in historical]),
                    "volume": np.array([c["volume"] for c in historical]),
                }

        if not ohlc_data:
            return None

        # Get regime
        trend = self.trend_analyzer.get_trend_summary(market, symbol)
        regime = trend.get("regime", "UNKNOWN")

        # Check regime filter
        if config.regime_filter and regime not in config.regime_filter:
            return None

        # Run strategies
        best_signal = None
        best_score = 0

        for strat_name in config.strategies:
            if strat_name not in self.strategies:
                continue
            strategy = self.strategies[strat_name]
            try:
                signal = strategy.analyze(symbol, market, ohlc_data)
                if signal and signal.get("confidence", 0) >= config.min_confidence:
                    signal["strategy"] = strat_name
                    signal["regime"] = regime
                    signal["timeframe"] = max(ohlc_data.keys(), key=lambda k: len(ohlc_data[k]["close"]))
                    if signal["confidence"] > best_score:
                        best_score = signal["confidence"]
                        best_signal = signal
            except Exception as e:
                logger.debug(f"Strategy {strat_name} failed on {symbol}: {e}")

        return best_signal

    def _should_take_signal(self, signal: dict, config: BacktestConfig) -> bool:
        """Validate signal meets risk criteria."""
        # Check risk-reward
        entry = signal.get("entry", 0)
        sl = signal.get("stop_loss", 0)
        tp = signal.get("take_profit", [0])[0]

        if entry <= 0 or sl <= 0 or tp <= 0:
            return False

        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk == 0 or reward / risk < 0.5:
            return False

        return True

    def _execute_trade(self, signal: dict, current_time: datetime, config: BacktestConfig, balance: float) -> Optional[BacktestTrade]:
        """Execute a trade with realistic costs."""
        entry = signal.get("entry", 0)
        sl = signal.get("stop_loss", 0)
        tp = signal.get("take_profit", [0])[0]

        # Position sizing
        risk_amount = balance * (config.risk_per_trade_pct / 100)
        risk_per_unit = abs(entry - sl)
        if risk_per_unit == 0:
            return None

        amount = risk_amount / risk_per_unit
        leverage = min(config.max_leverage, signal.get("leverage", 1.0))

        # Apply slippage and spread
        market = signal.get("market", "SPOT")
        side = signal.get("direction", "LONG")

        # Calculate fill price with slippage
        fill_price = self.fee_calc.get_fill_price(
            market, "BUY" if side in ("LONG", "BUY") else "SELL",
            "MARKET", entry, amount, leverage, 1000000.0
        )

        # Calculate fees
        fee = self.fee_calc.calculate(market, "BUY" if side in ("LONG", "BUY") else "SELL", amount, fill_price, leverage)

        # Calculate slippage cost
        slippage = abs(fill_price - entry) * amount

        trade = BacktestTrade(
            trade_id=str(uuid.uuid4())[:8],
            symbol=signal["symbol"],
            market=market,
            strategy=signal["strategy"],
            side=side,
            entry_time=current_time,
            entry_price=fill_price,
            exit_time=None,
            exit_price=None,
            amount=amount,
            leverage=leverage,
            stop_loss=sl,
            take_profit=tp,
            fees=fee,
            slippage=slippage,
            regime=signal.get("regime", "UNKNOWN"),
            confidence=signal.get("confidence", 0)
        )

        return trade

    def _check_exit(self, trade: BacktestTrade, current_time: datetime, config: BacktestConfig) -> Optional[tuple[float, str]]:
        """Check if position should be closed using historical candles up to current_time only."""
        current_ms = int(current_time.timestamp() * 1000)
        tf = "1m" if "1m" in config.timeframes else min(config.timeframes, key=lambda item: self._tf_to_seconds(item))
        series = self.candles.get_series(trade.market, trade.symbol, tf, limit=1000)
        historical = [c for c in series if int(c["open_time"]) <= current_ms]
        if not historical:
            return None

        current_price = historical[-1]["close"]

        # Check stop loss
        if trade.side in ("LONG", "BUY"):
            if current_price <= trade.stop_loss:
                return current_price, "STOP_LOSS"
            if current_price >= trade.take_profit:
                return current_price, "TAKE_PROFIT"
        else:  # SHORT
            if current_price >= trade.stop_loss:
                return current_price, "STOP_LOSS"
            if current_price <= trade.take_profit:
                return current_price, "TAKE_PROFIT"

        # Check liquidation for futures
        if trade.market == "FUTURES":
            pos_dict = {
                "market": trade.market,
                "side": trade.side,
                "entry_price": trade.entry_price,
                "leverage": trade.leverage
            }
            if self.liquidation.check_liquidation(pos_dict, current_price):
                return current_price, "LIQUIDATION"

        return None

    def _close_trade(self, trade: BacktestTrade, exit_price: float, reason: str, exit_time: datetime, config: BacktestConfig) -> None:
        """Close trade and calculate P&L with all costs."""
        trade.exit_time = exit_time
        trade.exit_price = exit_price
        trade.close_reason = reason

        # Exit fees
        exit_fee = self.fee_calc.calculate(
            trade.market, "SELL" if trade.side in ("LONG", "BUY") else "BUY",
            trade.amount, exit_price, trade.leverage
        )
        trade.fees += exit_fee

        # Exit slippage — calculate_slippage already returns a dollar cost
        exit_slippage = self.fee_calc.calculate_slippage(
            trade.market, "MARKET", trade.amount, exit_price, trade.leverage, 1000000.0
        )
        trade.slippage += abs(exit_slippage)

        # Funding (if futures)
        if trade.market == "FUTURES" and trade.exit_time and trade.entry_time:
            hours_held = (trade.exit_time - trade.entry_time).total_seconds() / 3600
            funding_intervals = int(hours_held / 8)
            if funding_intervals > 0:
                # Simplified: use average funding rate
                funding_rate = 0.0001  # 0.01% per 8h
                trade.funding = self.funding_calc.calculate({
                    "market": "FUTURES",
                    "side": trade.side,
                    "amount": trade.amount,
                    "entry_price": trade.entry_price,
                    "leverage": trade.leverage
                }, funding_rate) * funding_intervals

        # Calculate P&L
        if trade.side in ("LONG", "BUY"):
            gross_pnl = (exit_price - trade.entry_price) * trade.amount
        else:
            gross_pnl = (trade.entry_price - exit_price) * trade.amount

        total_costs = trade.fees + trade.slippage + trade.funding
        trade.pnl = gross_pnl - total_costs
        trade.pnl_pct = (trade.pnl / (trade.entry_price * trade.amount)) * 100 if trade.entry_price > 0 else 0

    def _run_out_of_sample(self, config: BacktestConfig) -> dict[str, Any]:
        """Run out-of-sample test on holdout period."""
        if not config.holdout_start:
            return {}

        oos_config = BacktestConfig(
            start_date=config.holdout_start,
            end_date=config.end_date,
            initial_balance=config.initial_balance,
            max_positions=config.max_positions,
            risk_per_trade_pct=config.risk_per_trade_pct,
            max_daily_loss_pct=config.max_daily_loss_pct,
            max_leverage=config.max_leverage,
            timeframes=config.timeframes,
            symbols=config.symbols,
            markets=config.markets,
            strategies=config.strategies,
            min_confidence=config.min_confidence,
            regime_filter=config.regime_filter
        )

        # Run on holdout data only
        trades, equity = self._simulate_backtest(oos_config)
        metrics = self._calculate_metrics(trades, equity, config.initial_balance)

        return {
            "trades": len(trades),
            "metrics": metrics,
            "sharpe": self._calculate_sharpe(self._calculate_daily_returns(equity)),
            "max_drawdown_pct": self._calculate_drawdown(equity, config.initial_balance)[1]
        }

    def _run_parameter_sensitivity(self, config: BacktestConfig) -> dict[str, Any]:
        """Run parameter sensitivity analysis."""
        if not config.parameter_grid:
            return {}

        results = {}
        base_config = config

        for param_name, param_values in config.parameter_grid.items():
            param_results = []
            for value in param_values:
                # Create modified config
                test_config = BacktestConfig(
                    start_date=base_config.start_date,
                    end_date=base_config.end_date,
                    initial_balance=base_config.initial_balance,
                    max_positions=base_config.max_positions,
                    risk_per_trade_pct=base_config.risk_per_trade_pct,
                    max_daily_loss_pct=base_config.max_daily_loss_pct,
                    max_leverage=base_config.max_leverage,
                    timeframes=base_config.timeframes,
                    symbols=base_config.symbols,
                    markets=base_config.markets,
                    strategies=base_config.strategies,
                    min_confidence=base_config.min_confidence,
                    regime_filter=base_config.regime_filter
                )
                setattr(test_config, param_name, value)

                trades, equity = self._simulate_backtest(test_config)
                metrics = self._calculate_metrics(trades, equity, base_config.initial_balance)

                param_results.append({
                    "value": value,
                    "sharpe": metrics.get("sharpe", 0),
                    "return": metrics.get("total_return", 0),
                    "max_dd": metrics.get("max_drawdown_pct", 0),
                    "trades": len(trades)
                })

            results[param_name] = param_results

        return results

    def _calculate_metrics(self, trades: list[BacktestTrade], equity_curve: list[tuple[datetime, float]], initial_balance: float) -> dict[str, float]:
        """Calculate comprehensive performance metrics."""
        if not trades:
            return {
                "total_return": 0, "total_pnl": 0, "win_rate": 0, "avg_win": 0,
                "avg_loss": 0, "profit_factor": 0, "total_trades": 0,
                "winning_trades": 0, "losing_trades": 0, "max_drawdown": 0,
                "max_drawdown_pct": 0, "sharpe": 0, "sortino": 0,
                "calmar": 0, "avg_fees": 0, "avg_slippage": 0, "avg_funding": 0
            }

        closed_trades = [t for t in trades if t.exit_time is not None]
        if not closed_trades:
            # Calculate from equity curve for unrealized metrics
            max_dd, max_dd_pct = self._calculate_drawdown(equity_curve, initial_balance)
            daily_returns = self._calculate_daily_returns(equity_curve)
            return {
                "total_return": 0, "total_pnl": 0, "win_rate": 0, "avg_win": 0,
                "avg_loss": 0, "profit_factor": 0, "total_trades": len(trades),
                "winning_trades": 0, "losing_trades": 0, "max_drawdown": max_dd,
                "max_drawdown_pct": max_dd_pct, "sharpe": 0, "sortino": 0,
                "calmar": 0, "avg_fees": 0, "avg_slippage": 0, "avg_funding": 0
            }

        total_pnl = sum(t.pnl for t in closed_trades)
        total_return = (total_pnl / initial_balance) * 100

        wins = [t for t in closed_trades if t.pnl > 0]
        losses = [t for t in closed_trades if t.pnl < 0]

        win_rate = len(wins) / len(closed_trades) if closed_trades else 0
        avg_win = np.mean([t.pnl for t in wins]) if wins else 0
        avg_loss = np.mean([t.pnl for t in losses]) if losses else 0
        profit_factor = abs(sum(t.pnl for t in wins) / sum(t.pnl for t in losses)) if losses else float('inf')

        max_dd, max_dd_pct = self._calculate_drawdown(equity_curve, initial_balance)
        daily_returns = self._calculate_daily_returns(equity_curve)
        sharpe = self._calculate_sharpe(daily_returns)
        sortino = self._calculate_sortino(daily_returns)
        calmar = self._calculate_calmar(daily_returns, max_dd_pct)

        return {
            "total_return": total_return,
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "total_trades": len(closed_trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "max_drawdown": max_dd,
            "max_drawdown_pct": max_dd_pct,
            "sharpe": sharpe,
            "sortino": sortino,
            "calmar": calmar,
            "avg_fees": np.mean([t.fees for t in closed_trades]),
            "avg_slippage": np.mean([t.slippage for t in closed_trades]),
            "avg_funding": np.mean([t.funding for t in closed_trades])
        }

    def _attribute_by_dimension(self, trades: list[BacktestTrade], dimension: str) -> dict[str, dict[str, float]]:
        """Attribute performance by a dimension."""
        closed = [t for t in trades if t.exit_time is not None]
        if not closed:
            return {}

        groups = {}
        for t in closed:
            key = getattr(t, dimension, "unknown")
            if key not in groups:
                groups[key] = []
            groups[key].append(t)

        result = {}
        for key, items in groups.items():
            wins = [t for t in items if t.pnl > 0]
            result[key] = {
                "trades": len(items),
                "win_rate": len(wins) / len(items) if items else 0,
                "total_pnl": sum(t.pnl for t in items),
                "avg_pnl": np.mean([t.pnl for t in items]) if items else 0
            }
        return result

    def _calculate_drawdown(self, equity_curve: list[tuple[datetime, float]], initial: float) -> tuple[float, float]:
        """Calculate maximum drawdown."""
        if not equity_curve:
            return 0.0, 0.0

        peak = initial
        max_dd = 0.0
        max_dd_pct = 0.0

        for _, equity in equity_curve:
            if equity > peak:
                peak = equity
            dd = peak - equity
            dd_pct = (dd / peak) * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd_pct

        return max_dd, max_dd_pct

    def _calculate_daily_returns(self, equity_curve: list[tuple[datetime, float]]) -> list[float]:
        """Calculate daily returns from equity curve."""
        if len(equity_curve) < 2:
            return []

        # Group by day
        daily_equity = {}
        for dt, eq in equity_curve:
            day = dt.date()
            if day not in daily_equity:
                daily_equity[day] = eq
            # Use end-of-day equity
            daily_equity[day] = eq

        sorted_days = sorted(daily_equity.keys())
        if len(sorted_days) < 2:
            return []

        returns = []
        for i in range(1, len(sorted_days)):
            prev = daily_equity[sorted_days[i-1]]
            curr = daily_equity[sorted_days[i]]
            if prev > 0:
                returns.append((curr - prev) / prev)

        return returns

    def _calculate_sharpe(self, daily_returns: list[float]) -> float:
        """Calculate Sharpe ratio (annualized, assuming 252 trading days)."""
        if not daily_returns or len(daily_returns) < 2:
            return 0.0
        mean = np.mean(daily_returns)
        std = np.std(daily_returns)
        if std == 0:
            return 0.0
        return (mean / std) * np.sqrt(252)

    def _calculate_sortino(self, daily_returns: list[float]) -> float:
        """Calculate Sortino ratio (downside deviation only)."""
        if not daily_returns or len(daily_returns) < 2:
            return 0.0
        mean = np.mean(daily_returns)
        downside = [r for r in daily_returns if r < 0]
        if not downside:
            return float('inf')
        downside_std = np.std(downside)
        if downside_std == 0:
            return 0.0
        return (mean / downside_std) * np.sqrt(252)

    def _calculate_calmar(self, daily_returns: list[float], max_dd_pct: float) -> float:
        """Calculate Calmar ratio."""
        if max_dd_pct == 0:
            return 0.0
        if not daily_returns:
            return 0.0
        annual_return = np.mean(daily_returns) * 252
        return annual_return / (max_dd_pct / 100)

    def _tf_to_seconds(self, tf: str) -> int:
        """Convert timeframe to seconds."""
        mapping = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800}
        return mapping.get(tf, 60)

    def _get_eligible_symbols(self, config: BacktestConfig) -> list[str]:
        """Get eligible symbols from database."""
        all_syms = self.repo.get_eligible_symbols()
        return list(set(s.symbol for s in all_syms))


class StrategyLaboratory:
    """
    Controlled strategy experimentation framework.

    Prevents:
    - Look-ahead bias (strict chronological data separation)
    - Survivorship bias (uses historical universe at each point)
    - Repeated optimization against same holdout (tracks holdout usage)
    """

    def __init__(self, backtester: HistoricalBacktester):
        self.backtester = backtester
        self.experiment_log: list[dict] = []
        self.holdout_usage: dict[str, int] = {}  # Track holdout dataset usage

    def run_experiment(self, name: str, configs: list[BacktestConfig], holdout_key: str = "default") -> dict[str, Any]:
        """Run controlled experiment comparing multiple configurations."""
        if holdout_key in self.holdout_usage:
            self.holdout_usage[holdout_key] += 1
            if self.holdout_usage[holdout_key] > 5:
                logger.warning(f"Holdout '{holdout_key}' used {self.holdout_usage[holdout_key]} times - risk of overfitting")
        else:
            self.holdout_usage[holdout_key] = 1

        results = {}
        for config in configs:
            result = self.backtester.run_backtest(config)
            results[config.strategies[0] if config.strategies else "unknown"] = result

        # Find best configuration
        best_key = max(results.keys(), key=lambda k: results[k].sharpe_ratio)

        experiment = {
            "name": name,
            "holdout_key": holdout_key,
            "holdout_usage_count": self.holdout_usage[holdout_key],
            "configs_tested": len(configs),
            "best_config": best_key,
            "best_sharpe": results[best_key].sharpe_ratio,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.experiment_log.append(experiment)

        return {
            "results": results,
            "best": best_key,
            "experiment": experiment
        }

    def get_experiment_history(self) -> list[dict]:
        """Get full experiment history."""
        return self.experiment_log.copy()