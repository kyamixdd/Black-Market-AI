# Community Strategy Library

## Available features
- Public strategy listing with text search, strategy-type, asset, timeframe and sort filters.
- Publishing and updating a built-in strategy description/ruleset.
- Immutable publication snapshots and version history.
- Read-only strategy details and a SHA-256 digest of the shared report summary.
- Favorites, and user content reports for misleading results, spam, abuse, copyright, or other concerns.
- Unpublishing hides a strategy from public search without deleting the owner's version history.

## Ownership and privacy
- Hosted web users receive a signed, pseudonymous community-owner cookie after successful login. The same-origin backend proxy verifies it and forwards only the verified owner UUID.
- The desktop client uses a random UUID stored in its local webview storage. It is not a user account and does not sync ownership between devices.
- Desktop local mode stores community records in its own local backend database. Cross-user public discovery requires the hosted application to connect to one common backend/database; a local desktop listing is not automatically uploaded to the hosted community.
- Community records are stored in dedicated `public_strategies`, `public_strategy_versions`, `strategy_favorites`, and `strategy_report_flags` tables.
- The publisher submits only the explicit strategy fields and a small allowlisted report summary. No portfolio, balances, API credentials, personal settings, or private trade records are fetched or included automatically.
- Rule JSON is bounded and rejects common private-field names. Risk configuration accepts only a small allowlist of numeric risk fields.
- This project currently has shared-password hosted authentication, not individual user accounts. Community identity is pseudonymous per browser/device, not an authenticated real-world profile.

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


## Current repository status — 23 November 2026

Maintained against `black-market-ai-beta`; application-source baseline reviewed: `49e6841215303ed296ced4fc1ef3039b9959426d`. Later commits in this branch are documentation-only at the time of this update. Verify the branch head before relying on this snapshot as current runtime or CI evidence.

**Classification:** Windows desktop beta candidate; hosted website private preview. BlackMarket AI is local-first market research and paper-trading software. Paper trading is the only execution mode; real-money exchange order execution is not supported or verified. The assistant is deterministic and read-only by default; the optional OpenAI-compatible provider only interprets retrieved evidence. ML training or model registration does not establish profitability or promotion without validation evidence.

Audit corrections and outstanding work:
- Root `LICENSE` exists and identifies the project as proprietary. Statements that no root license exists are outdated.
- CI run #605 passed on an earlier commit, not the current source baseline. Fresh current-head CI and release-artifact verification remain required.
- The website is a shared-password private preview, not multi-user identity or tenant isolation. Hosted backend, durable storage, streaming and restore acceptance remain release gates.
- The repository contains 30 generated compressed shutdown database backups under `data/backups/` using `.db.gz`; the current ignore rules do not exclude this suffix. Contents were not inspected. Review safely and remove generated database artifacts from version control.
- SQLite databases, model artifacts and backup archives are not application-encrypted. SHA-256 manifests provide integrity, not confidentiality.

This is source/documentation evidence only; it does not claim live deployment verification, fresh training/backtest, current-head CI, security certification or profitable performance.
