# Stage 10 — Controlled evolution

Controlled evolution is a review workflow for improving the assistant's validated intelligence configuration. It is deliberately not self-modifying.

## Safety boundaries

- The proposal allow-list contains only Stage 9 configuration fields: mode, tool-call budget, memory, feedback, provider interpretation, and response detail.
- No arbitrary code/file patches, shell commands, dependency changes, exchange permission changes, trading actions, or deployments are accepted.
- Proposal creation only records a pending candidate. It does not change runtime settings.
- Candidate and baseline benchmark metrics must be finite values in the 0–1 range and include all required metrics and a report version.
- A proposal cannot be approved without a baseline, all benchmark thresholds, and no regression against the baseline.
- Approval and rollback require explicit confirmation from an authenticated API client.
- Approved configurations are versioned with the previous configuration for rollback.

## API

All endpoints are under `/api/evolution` and use the existing local bearer-token authentication middleware.

- `POST /weaknesses`: submit a benchmark report and receive threshold/failed-case weaknesses.
- `POST /proposals`: submit a bounded config patch, candidate report, optional baseline, and rationale.
- `GET /proposals`: list pending and historical proposals.
- `POST /proposals/{proposal_id}/approve`: body `{"explicit_approval": true}`; applies only a gate-eligible proposal.
- `GET /versions`: list configuration versions.
- `POST /versions/{version_id}/rollback`: body `{"explicit_approval": true}`; restore the saved previous configuration and record the rollback as a new version.

A missing baseline results in a pending proposal that is ineligible for approval. It is not treated as evidence of improvement. Candidate reports must include the exact proposed configuration; baseline reports must include the active configuration. Reports are rejected if these snapshots do not match.

To measure a candidate configuration, save its validated JSON object and run the Stage 8 benchmark with `--intelligence-config candidate.json`. The resulting report records the configuration used. A baseline should be generated under the currently active configuration.

## Persistence

Proposal and version history is stored in the local private data directory as `controlled_evolution.json`, using atomic replacement and restrictive file permissions where supported. Runtime settings continue to use the existing settings store.

## Scope

This stage does not run proposals automatically or edit application source code. The user reviews benchmark evidence and explicitly approves or rejects configuration changes.


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
