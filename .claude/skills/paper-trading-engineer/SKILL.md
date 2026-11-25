---
name: paper-trading-engineer
description: Virtual Spot and Futures trading simulation, order lifecycle, fills, positions, and PnL.
---

# Paper Trading Engineer

Implement a completely local trading simulator.

## Virtual accounts
- Spot: 500 USDT.
- USDⓈ-M Futures: 500 USDT.
- Keep balances, positions, and accounting independent.

## Required functionality
- Simulated market orders.
- Simulated limit orders.
- Partial fills.
- Spread and slippage.
- Trading fees.
- Stop-loss and take-profit.
- Futures leverage simulation.
- Funding payments.
- Liquidation simulation.
- Position sizing.
- Realized and unrealized PnL.

## Trade lifecycle
PROPOSED -> VALIDATED -> OPEN -> PARTIALLY FILLED -> CLOSED

Other valid states: REJECTED, EXPIRED, CANCELLED.

Persist every state transition. Support restart recovery without duplicating orders or positions.

Use realistic market data and deterministic tests for accounting. Never invent fills or historical performance.

The simulator must be isolated from any future live-execution system. Never add real Binance order placement.

## Recovery and persistence boundary
- The production orchestrator persists opened positions and limit-order placement/fill events, then recovery restores open positions and open/partial orders using their persisted IDs. Recovery must be idempotent.
- Completed trade history and position closure are committed together; do not delete the closed position record.
- Do not claim native forced-crash/restart behavior is verified: the 1.0.0 x64 NSIS package's ordinary startup, duplicate-launch guard, and graceful close were exercised, but an unexpected desktop/backend process crash was not. Keep paper trading local; never add real exchange execution.
