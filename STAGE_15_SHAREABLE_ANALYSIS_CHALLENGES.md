# Stage 15 — Shareable Analysis and Paper-Trading Challenges

## Implemented in this branch

- `POST /api/community/share/analysis` creates an immutable publication snapshot.
- `GET /api/community/share/analysis/{share_id}` returns the public snapshot read-only.
- Public report schema is allowlisted: asset, market, timeframe, timezone-aware analysis timestamp, data source/freshness, indicators, market condition, evidence, risk factors, optional strategy configuration, and research disclaimer.
- Snapshot payloads are finite JSON, size bounded, canonicalized, and stored with a SHA-256 content digest.
- `GET /api/community/challenges` and `GET /api/community/challenges/{challenge_id}` expose five challenge definitions with starting capital, duration, assets, simulation rules, costs, risk limits, and ranking approach.
- API tests cover persistence, immutable readback, input validation, privacy fields, unknown IDs, and challenge specification integrity.

## Safety / honest limitations

Challenge participation and public rankings are intentionally **disabled**. The current hosted architecture uses shared API authentication and does not provide reliable individual participant identity or isolated server-owned challenge accounts. Accepting client-submitted PnL/trade histories would allow manipulated rankings. No leaderboard, participation endpoint, completion claim, or client-score submission is enabled in this stage.

Before enabling participation, implement and test:
1. Individual hosted identity and authorization.
2. Separate challenge account/ledger tables and challenge-specific order/position/trade records.
3. Server-side market execution with deterministic fee/slippage application and immutable event ledger.
4. Server-computed metrics and ranking, with minimum sample rules, idempotent execution, anti-replay and integrity checks.
5. Start/finish lifecycle and completion snapshot; privacy/deletion and abuse reporting controls.

## Challenge baseline

All definitions use simulated starting capital of 10,000 units, spot-only, no leverage, BTCUSDT/ETHUSDT, 0.10% fee per side, 0.05% slippage per side, and 14- or 30-day durations. Individual challenge risk caps and ranking intent are returned in the API. Rankings must be computed from the server-owned ledger; net profit alone is not a ranking metric.

These are research simulations, not investment advice. No guaranteed returns or encouragement of leverage is provided.

## Validation

The new tests are in `tests/test_stage15_share_challenges.py`. Run with the repository's normal test environment:

```bash
pytest -q tests/test_stage15_share_challenges.py
```

Full integration testing and hosted deployment are not performed from this branch.
