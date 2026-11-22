# Stage 1 — Paper-Trading Stabilization

## Scope
This stage is limited to existing paper-trading order management and simulator correctness. Execution remains simulated; no exchange order-placement APIs were added.

## Changes
- Added order-ID idempotency in `Simulator._execute_signal_locked`. Repeated execution of an order with an existing open position returns that position; an order already represented in closed trade history is rejected.
- Added regression coverage for cancellation, duplicate cancellation, preventing cancelled limit orders from filling, cancellation event emission, and duplicate execution before and after position closure.

## Existing behavior reviewed
- The manual cancellation API rejects unknown orders and orders in `FILLING`, `RECOVERY_REVIEW`, or any non-`OPEN` state.
- Simulator cancellation transitions the order to `CANCELLED`, persists it before removing it from the in-memory open-order map, and emits `TRADE_CANCELLED`.
- Limit fill processing claims `FILLING` before awaiting execution and reconciles order ownership to prevent a retry from duplicating a position.
- Manual market and limit order request schemas reject invalid/non-finite quantity, price, stop-loss, take-profit, and leverage values. The manual route rejects unsupported Spot shorts and validates market snapshot freshness.
- Existing position close logic claims `CLOSING` before awaiting, commits trade history through the repository callback, and rolls back in-memory accounting when persistence fails.

## Verification status
Regression tests were added but have not been executed in a local project checkout or CI in this stage. Therefore Stage 1 is **not marked complete** until the targeted paper-trading and persistence suites, full backend test suite, lint/type checks, and build checks run successfully.

## Remaining validation
- Execute `tests/test_manual_paper_trading.py`, `tests/test_paper_trading_phase5.py`, and `tests/test_paper_trading_persistence.py`.
- Run the complete backend test suite and applicable lint/type/build checks.
- Verify frontend order and position views against live API responses in a running app. The API returns current simulator order/position state; an end-to-end UI check remains outstanding.
