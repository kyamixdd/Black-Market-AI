"""Deterministic Strategy Lab backtesting on completed historical candles.

Signals are evaluated at a completed bar close and filled at the next bar open.
When both stop and target are touched in one candle, stop-loss is assumed first.
This conservative ordering avoids optimistic intrabar assumptions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import isfinite, sqrt
from typing import Any

import numpy as np

from paper_trading.fee_calculator import FeeCalculator
from strategies.all_strategies import MeanReversionStrategy, ReversalStrategy, TrendFollowingStrategy
from strategies.breakout import BreakoutStrategy
from strategies.momentum import MomentumStrategy


STRATEGIES = {
    "momentum": MomentumStrategy,
    "breakout": BreakoutStrategy,
    "trend_following": TrendFollowingStrategy,
    "mean_reversion": MeanReversionStrategy,
    "reversal": ReversalStrategy,
}


@dataclass(frozen=True)
class LabConfig:
    symbol: str
    market: str
    timeframe: str
    start_time: int
    end_time: int
    initial_capital: float = 1000.0
    sizing_mode: str = "risk_pct"
    risk_per_trade_pct: float = 1.0
    fixed_notional: float = 100.0
    max_position_pct: float = 50.0
    fee_rate: float | None = None
    slippage_bps: float | None = None
    spread_bps: float | None = None
    funding_rate: float | None = None
    strategy_parameters: dict[str, Any] | None = None


def _number(value: Any, name: str, minimum: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not isfinite(result) or result < minimum:
        raise ValueError(f"{name} must be finite and >= {minimum}")
    return result


def _validate_candles(rows: list[dict], config: LabConfig) -> list[dict]:
    unique: dict[int, dict] = {}
    for row in rows:
        try:
            ts = int(row["open_time"])
            close_time = int(row.get("close_time", ts))
            o, h, l, c, v = (float(row[k]) for k in ("open", "high", "low", "close", "volume"))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if not all(isfinite(x) for x in (o, h, l, c, v)) or min(o, h, l, c) <= 0 or v < 0:
            continue
        if h < max(o, c, l) or l > min(o, c):
            continue
        if ts < config.start_time or close_time > config.end_time:
            continue
        unique[ts] = {**row, "open_time": ts, "close_time": close_time,
                      "open": o, "high": h, "low": l, "close": c, "volume": v}
    return [unique[key] for key in sorted(unique)]


def _ohlc(rows: list[dict]) -> dict[str, np.ndarray]:
    return {key: np.asarray([float(row[key]) for row in rows], dtype=float)
            for key in ("open", "high", "low", "close", "volume")}


def _costs(config: LabConfig, market: str) -> tuple[float, float, float]:
    fee = config.fee_rate if config.fee_rate is not None else (0.001 if market == "SPOT" else 0.0005)
    spread = config.spread_bps if config.spread_bps is not None else (2.0 if market == "SPOT" else 1.0)
    slip = config.slippage_bps if config.slippage_bps is not None else (5.0 if market == "SPOT" else 3.0)
    return _number(fee, "fee_rate"), _number(spread, "spread_bps"), _number(slip, "slippage_bps")


def _metrics(trades: list[dict], equity: list[dict], initial: float, candles: list[dict]) -> dict:
    closed = [trade for trade in trades if trade["status"] == "CLOSED"]
    pnls = [trade["net_pnl"] for trade in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = sum(trade["gross_pnl"] for trade in closed)
    gross_loss = abs(sum(min(0.0, trade["gross_pnl"]) for trade in closed))
    net = sum(pnls)
    peak = initial
    max_dd = 0.0
    max_dd_pct = 0.0
    daily: dict[str, float] = {}
    for point in equity:
        value = point["equity"]
        peak = max(peak, value)
        dd = peak - value
        max_dd = max(max_dd, dd)
        if peak > 0:
            max_dd_pct = max(max_dd_pct, dd / peak * 100.0)
    for trade in closed:
        day = datetime.fromtimestamp(trade["exit_time"] / 1000, timezone.utc).date().isoformat()
        daily[day] = daily.get(day, 0.0) + trade["net_pnl"]
    daily_returns = [value / initial for _, value in sorted(daily.items())] if initial > 0 else []
    sharpe = None
    if len(daily_returns) >= 2:
        mean = sum(daily_returns) / len(daily_returns)
        variance = sum((x - mean) ** 2 for x in daily_returns) / len(daily_returns)
        std = sqrt(variance)
        sharpe = mean / std * sqrt(365.0) if std > 0 else None
    exposure = sum(trade["bars_held"] for trade in closed) / max(1, len(equity)) * 100.0
    benchmark = ((candles[-1]["close"] / candles[0]["close"]) - 1.0) * 100.0 if len(candles) >= 2 else None
    avg_win = sum(wins) / len(wins) if wins else None
    avg_loss = sum(losses) / len(losses) if losses else None
    return {
        "initial_capital": initial, "final_equity": equity[-1]["equity"] if equity else initial,
        "net_return_pct": net / initial * 100.0 if initial else None,
        "gross_return_pct": gross_profit / initial * 100.0 if initial else None,
        "gross_profit": gross_profit, "gross_loss": gross_loss,
        "max_drawdown": max_dd, "max_drawdown_pct": max_dd_pct,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else ("infinite" if wins else None),
        "win_rate_pct": len(wins) / len(closed) * 100.0 if closed else None,
        "average_winning_trade": avg_win, "average_losing_trade": avg_loss,
        "average_reward_risk": avg_win / abs(avg_loss) if avg_win is not None and avg_loss is not None and avg_loss else None,
        "sharpe_ratio": sharpe, "trade_count": len(closed),
        "exposure_pct": min(100.0, exposure), "benchmark_buy_hold_return_pct": benchmark,
        "costs": {"fees": sum(t["fees"] for t in closed), "slippage": sum(t["slippage"] for t in closed),
                   "spread": sum(t["spread"] for t in closed), "funding": sum(t["funding"] for t in closed)},
        "metric_notes": {
            "gross_return_pct": "Gross realized PnL before fees, slippage, spread and funding, divided by initial capital.",
            "sharpe_ratio": "Annualized daily realized net returns using sqrt(365); unavailable with fewer than two daily observations or zero variance.",
            "exposure_pct": "Total position bars divided by equity-curve bars; capped at 100% for the single-position simulation.",
            "benchmark": "Buy-and-hold return over the same selected candle interval; not cost-adjusted.",
            "funding": "Funding is applied only when a funding_rate is explicitly supplied; historical funding-rate replay is otherwise unavailable."
        }
    }


def run_strategy_lab(rows: list[dict], config: LabConfig, strategy_name: str) -> dict:
    if strategy_name not in STRATEGIES:
        raise ValueError(f"Unsupported strategy: {strategy_name}")
    if config.market not in {"SPOT", "FUTURES"}:
        raise ValueError("market must be SPOT or FUTURES")
    if config.sizing_mode not in {"risk_pct", "fixed_notional"}:
        raise ValueError("sizing_mode must be risk_pct or fixed_notional")
    initial = _number(config.initial_capital, "initial_capital", 0.01)
    risk_pct = _number(config.risk_per_trade_pct, "risk_per_trade_pct", 0.01)
    fixed_notional = _number(config.fixed_notional, "fixed_notional", 0.01)
    max_position_pct = _number(config.max_position_pct, "max_position_pct", 0.01)
    if max_position_pct > 100:
        raise ValueError("max_position_pct cannot exceed 100")
    candles = _validate_candles(rows, config)
    if len(candles) < 60:
        return {"status": "insufficient_data", "required_candles": 60, "available_candles": len(candles),
                "trades": [], "equity_curve": [], "metrics": None}
    strategy = STRATEGIES[strategy_name]()
    fee_rate, spread_bps, slip_bps = _costs(config, config.market)
    equity = initial
    curve: list[dict] = [{"time": candles[0]["open_time"], "equity": equity}]
    trades: list[dict] = []
    position: dict | None = None
    pending: dict | None = None
    bars_in_position = 0
    params = config.strategy_parameters or {}
    min_score = _number(params.get("min_score", 0), "strategy_parameters.min_score")
    for index in range(50, len(candles) - 1):
        bar = candles[index]
        next_bar = candles[index + 1]
        if position:
            bars_in_position += 1
            long_side = position["side"] == "LONG"
            stop_hit = bar["low"] <= position["stop_loss"] if long_side else bar["high"] >= position["stop_loss"]
            target_hit = bar["high"] >= position["take_profit"] if long_side else bar["low"] <= position["take_profit"]
            exit_reason = "STOP_LOSS" if stop_hit else "TAKE_PROFIT" if target_hit else None
            if exit_reason:
                raw_exit = position["stop_loss"] if stop_hit else position["take_profit"]
                direction = -1 if long_side else 1
                exit_fill = raw_exit * (1 + direction * (spread_bps / 2.0 + slip_bps) / 10000.0
                notional_exit = position["quantity"] * exit_fill
                exit_fee = notional_exit * fee_rate
                gross = (raw_exit - position["entry_price"]) * position["quantity"] * (1 if long_side else -1)
                funding = 0.0
                if config.market == "FUTURES" and config.funding_rate is not None:
                    hours = (bar["open_time"] - position["entry_time"]) / 3600000.0
                    funding = position["quantity"] * position["entry_fill"] * _number(config.funding_rate, "funding_rate") * int(hours // 8) * (1 if long_side else -1)
                exit_slippage = abs(exit_fill - raw_exit) * position["quantity"] * (slip_bps / (spread_bps / 2.0 + slip_bps) if spread_bps / 2.0 + slip_bps else 0.0)\n                exit_spread = raw_exit * spread_bps / 20000.0 * position["quantity"]\n                total_cost = position["entry_fee"] + exit_fee + position["entry_slippage"] + exit_slippage + position["entry_spread"] + exit_spread + funding
                net = gross - total_cost
                equity += net
                trades.append({
                    **position, "exit_time": bar["close_time"], "exit_price": raw_exit, "exit_fill": exit_fill,
                    "gross_pnl": gross, "net_pnl": net, "fees": position["entry_fee"] + exit_fee,
                    "slippage": position["entry_slippage"] + position["exit_slippage"],
                    "spread": position["entry_spread"] + position["exit_spread"], "funding": funding,
                    "close_reason": exit_reason, "bars_held": bars_in_position, "status": "CLOSED",
                })
                position = None
                bars_in_position = 0
        if position is None:
            strategy_tf = "1h" if strategy_name == "trend_following" else "15m"
            ohlc = {strategy_tf: _ohlc(candles[:index + 1])}
            try:
                signal = strategy.analyze(config.symbol, config.market, ohlc)
            except (ValueError, IndexError, KeyError, TypeError, FloatingPointError):
                signal = None
            if signal and float(signal.get("raw_score", 0) or 0) >= min_score:
                side = str(signal.get("direction", "")).upper()
                entry = _number(signal.get("entry"), "signal.entry", 0.00000001)
                stop = _number(signal.get("stop_loss"), "signal.stop_loss", 0.00000001)
                targets = signal.get("take_profit") or []
                target = _number(targets[0] if isinstance(targets, list) else targets, "signal.take_profit", 0.00000001)
                if side in {"LONG", "BUY"} and stop < entry < target or side in {"SHORT", "SELL"} and target < entry < stop:
                    risk_per_unit = abs(entry - stop)
                    risk_cash = equity * risk_pct / 100.0
                    quantity = risk_cash / risk_per_unit if config.sizing_mode == "risk_pct" else fixed_notional / entry
                    quantity = min(quantity, equity * max_position_pct / 100.0 / entry)
                    if quantity > 0 and isfinite(quantity):
                        pending = {"side": "LONG" if side in {"LONG", "BUY"} else "SHORT", "signal_index": index,
                                   "entry": entry, "stop_loss": stop, "take_profit": target,
                                   "strategy": strategy_name, "score": float(signal.get("raw_score", 0) or 0)}
        if pending and pending["signal_index"] == index:
            side = pending["side"]
            raw_entry = next_bar["open"]
            direction = 1 if side == "LONG" else -1
            entry_fill = raw_entry * (1 + direction * (spread_bps / 2.0 + slip_bps) / 10000.0
            quantity = min((equity * risk_pct / 100.0) / abs(entry_fill - pending["stop_loss"]) if config.sizing_mode == "risk_pct" else fixed_notional / entry_fill,
                          equity * max_position_pct / 100.0 / entry_fill)
            entry_fee = quantity * entry_fill * fee_rate
            position = {
                "trade_id": f"{strategy_name}-{config.symbol}-{config.timeframe}-{bar['open_time']}",
                "symbol": config.symbol, "market": config.market, "strategy": strategy_name,
                "side": side, "entry_time": next_bar["open_time"], "signal_time": bar["close_time"],
                "entry_price": raw_entry, "entry_fill": entry_fill, "quantity": quantity,
                "stop_loss": pending["stop_loss"], "take_profit": pending["take_profit"],
                "entry_fee": entry_fee, "entry_slippage": raw_entry * slip_bps / 10000.0 * quantity,
                "entry_spread": abs(raw_entry) * spread_bps / 20000.0 * quantity,
                "exit_time": None, "exit_price": None, "gross_pnl": 0.0, "net_pnl": 0.0,
                "fees": 0.0, "slippage": 0.0, "spread": 0.0, "funding": 0.0,
                "close_reason": "OPEN", "bars_held": 0, "status": "OPEN",
            }
            pending = None
        marked_equity = equity
        if position:
            direction_sign = 1 if position["side"] == "LONG" else -1
            unrealized = (bar["close"] - position["entry_price"]) * position["quantity"] * direction_sign
            estimated_exit_cost = position["quantity"] * bar["close"] * (fee_rate + spread_bps / 20000.0 + slip_bps / 10000.0)
            marked_equity += unrealized - position["entry_fee"] - estimated_exit_cost
        curve.append({"time": bar["close_time"], "equity": marked_equity})
    if position:
        last = candles[-1]
        exit_fill = last["close"] * (1 - (spread_bps / 2.0 + slip_bps) / 10000.0 * (1 if position["side"] == "LONG" else -1))
        gross = (last["close"] - position["entry_price"]) * position["quantity"] * (1 if position["side"] == "LONG" else -1)
        exit_fee = position["quantity"] * exit_fill * fee_rate
        exit_slippage = last["close"] * slip_bps / 10000.0 * position["quantity"]\n        exit_spread = last["close"] * spread_bps / 20000.0 * position["quantity"]\n        funding = 0.0
        if config.market == "FUTURES" and config.funding_rate is not None:
            hours = (last["open_time"] - position["entry_time"]) / 3600000.0
            funding = position["quantity"] * position["entry_fill"] * _number(config.funding_rate, "funding_rate") * int(hours // 8) * (1 if position["side"] == "LONG" else -1)
        costs = position["entry_fee"] + exit_fee + position["entry_slippage"] + position["entry_spread"] + exit_slippage + exit_spread + funding
        net = gross - costs
        equity += net
        trades.append({**position, "exit_time": last["close_time"], "exit_price": last["close"], "exit_fill": exit_fill,
                       "gross_pnl": gross, "net_pnl": net, "fees": position["entry_fee"] + exit_fee,
                       "slippage": position["entry_slippage"] + abs(exit_fill - last["close"]) * position["quantity"],
                       "spread": position["entry_spread"], "funding": 0.0, "close_reason": "END_OF_TEST",
                       "bars_held": bars_in_position, "status": "CLOSED"})
        curve.append({"time": last["close_time"], "equity": equity})
    metrics = _metrics(trades, curve, initial, candles)
    return {"status": "ok", "strategy": strategy_name, "symbol": config.symbol, "market": config.market,
            "timeframe": config.timeframe, "candle_count": len(candles), "start_time": candles[0]["open_time"],
            "end_time": candles[-1]["close_time"], "config": asdict(config), "trades": trades,
            "equity_curve": curve, "metrics": metrics,
            "execution_model": "completed-bar signal; next-bar open fill; conservative stop-first intrabar; taker fees plus configurable spread/slippage"}
