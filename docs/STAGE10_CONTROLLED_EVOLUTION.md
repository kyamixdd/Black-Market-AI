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

A missing baseline results in a pending proposal that is ineligible for approval. It is not treated as evidence of improvement.

## Persistence

Proposal and version history is stored in the local private data directory as `controlled_evolution.json`, using atomic replacement and restrictive file permissions where supported. Runtime settings continue to use the existing settings store.

## Scope

This stage does not run proposals automatically or edit application source code. The user reviews benchmark evidence and explicitly approves or rejects configuration changes.
