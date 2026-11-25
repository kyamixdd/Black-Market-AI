# Community Strategy Library

## Available features
- Public strategy listing with text search, strategy-type, asset, timeframe and sort filters.
- Publishing and updating a built-in strategy description/ruleset.
- Immutable publication snapshots and version history.
- Read-only strategy details and a SHA-256 digest of the shared report summary.
- Favorites, and user content reports for misleading results, spam, abuse, copyright, or other concerns.
- Unpublishing hides a strategy from public search without deleting the owner's version history.

## Ownership and privacy
- The desktop client uses a random UUID stored in its local webview storage. It is not a user account and does not sync ownership between devices.
- Community records remain in the local desktop database. Cross-user public discovery and hosted sharing are not supported production features.
- Community records are stored in dedicated `public_strategies`, `public_strategy_versions`, `strategy_favorites`, and `strategy_report_flags` tables.
- The publisher submits only the explicit strategy fields and a small allowlisted report summary. No portfolio, balances, API credentials, personal settings, or private trade records are fetched or included automatically.
- Rule JSON is bounded and rejects common private-field names. Risk configuration accepts only a small allowlist of numeric risk fields.

## Report provenance
- Manually supplied metrics are labelled `USER_SUBMITTED`. A report ID from the internal Strategy Lab completion path can be linked and labelled `LOCAL_BACKTEST`; its summary is derived server-side from that saved report. The public API cannot convert an ordinary user-saved report into `LOCAL_BACKTEST`.
- A SHA-256 digest detects whether the stored summary differs from the published digest; it does **not** prove the backtest's performance is true. For a linked local run, the origin is recorded by the internal Strategy Lab completion path, not chosen by the publisher.
- `LOCAL_BACKTEST` identifies an application-generated local run only. It is not a reproducibility or independent verification claim. `REPRODUCIBLE_BACKTEST` and `VERIFIED_APPLICATION_RESULT` are not currently awarded; they require immutable input data, code/version metadata, deterministic replay, and a trusted verification flow.
- The interface explicitly states that user-submitted results are not independently verified and do not predict future profitability.

## Limitations
- Reports are queued in the database for review; this stage does not include a moderator/admin review console or automatic removal workflow.
- Shared library durability depends on the configured backend's persistent storage. Do not use ephemeral disk as the production community database.
- Search/filter and sorting operate on public metadata only; no profitability ranking is presented.
- Public sharing is for research only. All execution remains paper/simulator-only; no exchange order execution is added.
- The backend uses existing SQLite persistence and does not require a paid community service.
