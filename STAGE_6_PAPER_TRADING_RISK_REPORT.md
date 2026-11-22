# Stage 6 — Paper-Trading Risk and Execution Integrity

## Scope
This stage hardens the local paper-trading simulator only. Real exchange order placement remains disabled and was not added.

## Implemented
- Serialized market-order execution and limit-order placement under the account allocation lock.
- Pending open limit orders reserve market position slots, symbol exposure, and aggregate stop risk until cancelled or filled.
- Backend validation of supported market/direction, finite positive entry and stop prices, stop/target direction, daily equity drawdown, position count, duplicate symbol, leverage, available margin, and total open stop risk.
- Configurable maximum position notional and aggregate base-asset exposure across Spot and Futures. Defaults: 50% of total account equity per position and 30% per asset. Runtime settings are validated, atomically persisted, restored, and applied to the live risk manager.
- Fill-time checks for per-trade risk, aggregate open risk, notional cap, and asset exposure. Auto-sized market orders are reduced when spread/slippage changes the stop distance.
- Limit orders execute at their limit price; simulated fills cannot be worse than the specified limit.
- Invalid market-price updates are ignored. Funding rates and liquidation calculations reject invalid numeric inputs.
- Funding settlement timestamps remain persisted and idempotent at UTC 8-hour boundaries.
- Futures liquidation losses are bounded by reserved isolated margin so a simulated gap cannot create a negative Futures available balance.
- Risk API and Risk Analytics panel report the new exposure limits and include open pending-order stop risk.

## Tests added or expanded
- Concurrent position openings against position caps.
- Pending limit-order slot/risk reservation.
- Cross-market asset exposure.
- Oversized manual quantity and invalid leverage rejection.
- Extreme fill-gap sizing.
- Daily drawdown recovery after restart.
- Futures liquidation collateral boundary.
- Runtime exposure settings validation, persistence, and live application.
- Non-finite risk input rejection.

## Important model assumptions and limitations
- Risk per trade is stop-distance based; trades without a valid stop are rejected.
- Asset exposure groups symbols by base asset inferred from common quote suffixes. This is not a full exchange instrument/contract mapping.
- Futures liquidation uses the existing simplified fixed maintenance-margin model; exchange tier-specific maintenance margin, liquidation fees, insurance fund and auto-deleveraging are not modeled.
- Funding uses the supplied current funding rate at a newly observed eligible settlement boundary. Historical settlement-rate replay is not available.
- Partial fills remain limited to the simulator's existing supported order lifecycle; no new exchange execution was introduced.
- This stage does not establish profitability or guarantee that simulated fills match exchange execution.

## Verification status
CI must pass before merge. No deployment was performed.
