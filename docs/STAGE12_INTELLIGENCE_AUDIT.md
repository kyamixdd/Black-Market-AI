# Stage 12 — Full Intelligence Audit

## Audit scope and evidence

> Historical Stage 12 technical findings are preserved. Comprehensive product documentation baseline reviewed 23 November 2026: `49e6841215303ed296ced4fc1ef3039b9959426d`. This document’s stage-specific findings and verification status are tied to its original audit evidence unless explicitly updated.

- **Target branch:** `black-market-ai-beta`
- **Audited base commit:** `45d1becc5406b888cddbb09a81ec9fe78bba5b94`
- **Stage 10 review:** PR #82, head `c151587fb107dbd4e465ed347730a2149d0abee7` (open; not part of the audited base)
- **Audit type:** source review, API/workflow trace, test/CI evidence review. No source behavior, configuration, dependency, database, deployment, or GitHub setting was changed.
- **Runtime scope:** no production or hosted deployment was exercised. CI evidence is not a substitute for end-to-end acceptance against a deployed backend.

The report distinguishes code inspection from CI validation and from live runtime verification.

## Executive status

The intelligence foundation through Stage 9 is present on the beta branch. It provides deterministic natural-language parsing, bounded read-only evidence tools, persistent owner-scoped memory, explicit feedback/preference handling, task planning/cancellation, event-driven monitoring, a compact outcome benchmark, validated intelligence modes, and a shared desktop/hosted frontend.

The implementation is **bounded and useful, but not yet a fully autonomous or broadly validated intelligence system**. It does not establish general language understanding, calibrated confidence, model factuality, or trading profitability. The benchmark baseline records 10/14 exact intent matches (71.43%), below the configured 90% threshold.

Stage 10 controlled evolution is implemented in PR #82 but is not merged into `black-market-ai-beta`. Its proposal workflow is review-only in design, but audit findings below show that benchmark provenance and stale-proposal checks need hardening before it should be accepted as a reliable promotion gate.

A dedicated Stage 11 local-model-provider abstraction was not found in the inspected beta branch or the recent Stage 1–10 PR history. The current optional provider is an OpenAI-compatible HTTP endpoint; it is not evidence of a completed local LLM integration.

## Workflow verification matrix

| Workflow | Code evidence | Verification status |
|---|---|---|
| Deterministic assistant query | `assistant/query`, runtime, NLU, evidence tools | Source and regression tests reviewed; broad real-world language coverage not established |
| Async assistant task, status, cancel | `assistant/tasks`, task manager | Bounded in-process task state; restart persistence not provided |
| Memory create/list/retrieve/delete | Assistant memory API and repository | Owner-scoped database tests, expiry and secret-pattern checks present |
| Explicit remember/recall | Assistant query route | Implemented as explicit command handling; not a general conversation-memory engine |
| Feedback and preference correction | Feedback and preference endpoints/repository | Thresholded adaptation exists; repeated feedback is not deduplicated by request ID |
| Realtime monitoring | Monitoring endpoints and event worker | Bounded in-memory task queue; task definitions do not survive process restart |
| Intelligence mode selection | Settings API, config loader, desktop Settings panel | Desktop selector and API are present; hosted uses shared UI/proxy |
| Outcome benchmark | Versioned dataset/evaluator/workflow | Deterministic CI measurement; small dataset, not a general assistant-quality test |
| Controlled proposal/approval/rollback | Stage 10 PR #82 | PR-only; no production/runtime acceptance; findings below must be resolved |
| Hosted assistant/config access | Shared React app and authenticated backend proxy | Source path supports generic proxying; deployed hosted backend/E2E behavior not verified |

## Security and permission review

### Confirmed protections

- Desktop API defaults to loopback binding; remote API mode is disabled unless explicitly enabled.
- Remote mode requires a configured bearer token with a minimum length and host validation.
- HTTP API authentication uses constant-time bearer comparison in the global middleware.
- WebSocket authentication requires a bearer token after connection and restricts the socket to loopback clients.
- Assistant tool registry is explicit and allow-listed. Registered assistant tools are read-only and marked as not changing application state.
- Tool inputs are restricted to symbol, market, and timeframe; unknown fields and unsupported values are rejected.
- Tool calls have timeouts and bounded retry behavior; retry is limited to transient read-only failures.
- Memory records use an owner namespace derived from the authenticated bearer credential, and CRUD operations enforce that namespace.
- Hosted proxy requires a valid signed session, checks same-origin mutations, applies process-local rate limits, limits request/response body sizes, and keeps backend credentials server-side.
- No assistant tool grants real-money order execution. Trading remains in the paper/simulation application boundary.

### Permission limitations

- The local desktop API uses a shared application bearer token, not individual user identities or granular user roles. The registry's permission labels are internal read scopes; the API does not currently issue per-user scoped grants.
- The hosted preview uses a single shared-password session. Hosted paper-trading data and settings are shared by the backend instance; account-level isolation is not implemented.
- Hosted session revocation and rate-limit counters are process-local. They are not shared across multiple instances or durable after restart.
- Remote backend deployment security depends on TLS, restrictive ingress, high-entropy secrets, and durable protected storage being configured correctly. This audit did not inspect live hosting configuration or secrets.
- Stage 10 approval uses an explicit confirmation boolean under the same authenticated API credential. It is not a separate role, signed approval, or multi-factor authorization.

## Desktop and hosted compatibility

- The desktop uses a loopback Python backend and the typed API client.
- The hosted application imports the same canonical React dashboard and sends API requests through the Next.js authenticated proxy.
- The Stage 9 intelligence-mode selector exists in the shared Settings screen and calls the intelligence settings endpoint.
- The hosted proxy forwards general backend route paths, so the Stage 10 API route is structurally proxy-compatible once the PR is merged; no Stage 10 proposal/version UI was found in the shared dashboard.
- CI has checks for desktop TypeScript/lint/market-data tests, shared website build, responsive browser smoke, Python regression, Rust/Tauri compilation, dependency audit, and Windows installer smoke.

### Compatibility verification limitations

- A successful website build does not verify a deployed hosted backend, session cookie behavior across instances, remote API ingress, database persistence, SSE reconnection, or complete hosted paper-trading workflows.
- The latest Stage 10 CI run (#741 / run ID `45152741527`) reported Python regression, desktop TypeScript/lint/market-data, website build, responsive smoke, and dependency audit as passed. Rust/Tauri and Windows installer jobs were still in progress when this audit snapshot was taken.
- The CI suite is not a full cross-platform runtime matrix. macOS/Linux packaged desktop installation and long-duration runtime behavior were not verified here.

## Performance and failure recovery

### Existing bounds and recovery behavior

- Assistant evidence tools have a 15-second execution timeout and at most one retry for transient read-only failures.
- Runtime tool count is constrained by the intelligence profile; the current plan executor also validates bounded plans.
- Async assistant tasks are limited to 16 active tasks and 128 retained in-process records.
- Realtime monitoring uses a bounded event queue and tracks dropped/duplicate events; monitoring task records are held in memory.
- Runtime settings and Stage 10 proposal state use atomic file replacement with restrictive permissions where supported.
- Backend startup checks SQLite integrity and shutdown stops the realtime service, orchestrator, event bus, WebSocket manager, and database.
- Optional provider interpretation is non-essential; unavailable/unsupported provider configuration returns to deterministic evidence output.

### Failure-recovery limitations

- Async task records, cancellation registrations, and realtime monitoring task definitions are process-local. Restart loses task status/history and active monitoring definitions.
- Cancellation is cooperative and can stop in-flight async tool work, but it is not a durable job queue.
- In-memory rate limiting and hosted session revocation reset on process restart.
- Atomic settings writes prevent torn files but do not provide a cross-process transaction or prevent concurrent lost updates.
- Stage 10 config application and evolution-history persistence are separate writes. A failure between them could apply a config without successfully recording its version; rollback/history should be made transactionally recoverable before relying on it.
- No measured latency, sustained-load, memory-growth, queue saturation, or multi-instance recovery benchmark was run as part of this audit.

## Confirmed findings and recommended priority

### P1 — Stage 10 promotion evidence is not authenticated

**Evidence:** `core/controlled_evolution.py` in PR #82 accepts caller-supplied candidate and baseline report dictionaries. It checks required metrics, numeric ranges, report version, and configuration snapshots, but does not verify benchmark artifact provenance, source commit, dataset version, workflow run, or a signature. A client with the API token can submit fabricated metrics and matching configuration snapshots.

**Impact:** The benchmark promotion gate can be bypassed by forged reports; measured quality is not guaranteed by the current API contract.

**Required before Stage 10 merge:** Generate reports server-side or verify a trusted signed/immutable report artifact. Validate benchmark ID, dataset version, source commit, sample counts, and required detail structure.

### P1 — Stage 10 approval does not re-check the active baseline configuration

**Evidence:** `approve_proposal()` checks the proposal's stored eligible gate and validates the stored config, but does not confirm that the active configuration is still the one used by the proposal's baseline when approval occurs.

**Impact:** A proposal can become stale after creation, yet remain eligible for application against a different active configuration.

**Required before Stage 10 merge:** Store the baseline configuration/version or hash in the proposal and compare it with the active config at approval time; invalidate or re-evaluate stale proposals.

### P2 — Intelligence mode environment override can retain settings from another profile

**Evidence:** `core/intelligence_config.py::load_intelligence_config` selects the mode from explicit override/environment/persisted mode, then merges the persisted `intelligence_config` over that mode's preset. The Stage 9 tests verify environment mode override only when no persisted profile values exist.

**Impact:** For example, a persisted research profile with custom values can be loaded as mode `fast` under `BLACKMARKET_INTELLIGENCE_MODE=fast` while retaining research/custom values such as a larger tool budget. The displayed mode and effective behavior can disagree.

**Recommended fix:** Define whether environment mode selects the complete preset or only the mode label. If it selects the preset, apply profile defaults after discarding persisted profile-specific values, or explicitly document/test an override policy.

### P2 — Stage 9 response-detail setting is validated but not applied by the assistant

**Evidence:** `response_detail` is part of `IntelligenceConfig`, presets, API, and UI. The inspected assistant runtime reads tool budget and provider enablement; the assistant response path applies stored feedback preferences, but does not apply the configured profile's `response_detail`.

**Impact:** Mode selection can report `brief` or `detailed` without consistently changing assistant response formatting.

**Recommended fix:** Apply the configured response-detail value in the response assembly path, with precedence documented against user-corrected preferences, and add end-to-end tests.

### P2 — Committed Stage 8 baseline is not compatible with Stage 10 config-bound baseline validation

**Evidence:** `benchmarks/assistant_outcomes/reports/baseline-v1.0.0.json` records metrics and source metadata but has no `intelligence_config` snapshot. Stage 10 proposal creation requires the baseline report's `intelligence_config` to equal the active config.

**Impact:** The committed baseline summary cannot be passed directly to the Stage 10 proposal path; a compatible full report must be generated and reviewed.

**Recommended fix:** Preserve a complete baseline report with the config snapshot and validated provenance. Do not silently relabel the existing summary as a complete candidate artifact.

### P2 — Stage 10 version/history updates are not a single transaction

**Evidence:** `approve_proposal()` and `rollback_version()` persist runtime configuration before saving the evolution history file.

**Impact:** If the second write fails, runtime config may change without a corresponding durable version/approval record.

**Recommended fix:** Use a recoverable transaction protocol (pending record, config write, committed record) or restore the previous config on history-write failure; add injected-failure tests.

### P2 — Stage 10 proposal/version history is unbounded

**Evidence:** The proposal and version lists append indefinitely; list endpoints return the full history without pagination or retention limits.

**Impact:** Repeated authenticated requests can grow local state and response size over time.

**Recommended fix:** Add bounded pagination and an explicit retention/archival policy while preserving rollback-critical versions.

### P2 — Assistant task and monitoring definitions are not restart-persistent

**Evidence:** Assistant task records and realtime monitoring task records are stored in in-process dictionaries.

**Impact:** A backend restart loses active task state, cancellation state, and monitoring definitions. The UI must treat these workflows as session-local.

**Recommended fix:** Either persist task/monitor definitions with recovery semantics or explicitly expose restart-loss behavior and require re-creation.

### P3 — Benchmark scope is too small for broad intelligence claims

**Evidence:** Baseline dataset contains 14 intent cases, 11 tool safety checks, 3 memory fixtures, and 3 deterministic completion cases. Baseline intent exact match is 71.43%; the report records four known mismatches.

**Impact:** The benchmark is a useful regression suite but cannot establish broad natural-language accuracy, calibrated confidence, production memory relevance, provider factuality, or market/trading performance.

**Recommended fix:** Expand reviewed cases and adversarial/ambiguous prompts; keep dataset versions immutable and use separate holdout evaluation.

### P3 — Stage 10 has no review/rollback interface in the shared dashboard

**Evidence:** The shared Settings UI exposes Stage 9 modes. No proposal review, approval, version history, or rollback screen was found in the inspected frontend.

**Impact:** Stage 10 is currently API-oriented and requires a trusted client or manual API workflow; users cannot review evidence and approve/rollback through the normal dashboard.

**Recommended fix:** Add a read-only proposal/version view and explicit confirmation UI only after provenance and stale-proposal safeguards are fixed.

### P3 — Stage 11 local provider abstraction remains unverified

**Evidence:** The inspected assistant provider uses an optional OpenAI-compatible HTTP endpoint. No dedicated local model adapter or Stage 11 PR was identified in the inspected branch/PR history.

**Impact:** Local inference availability, model lifecycle, resource budgeting, and offline provider behavior are not established.

**Required follow-up:** Verify Stage 11 implementation status before treating the full staged intelligence roadmap as complete.

## Audit conclusion

The merged intelligence implementation is suitable for **bounded, authenticated, read-only local evidence retrieval and measured assistant workflows**, subject to the limitations documented above. It is not verified as a general-purpose autonomous intelligence system.

Stage 9 is integrated on the beta branch. Stage 10 remains under review and should not be merged until benchmark provenance, stale approval validation, and version-write recovery are addressed. Stage 11 local provider status requires confirmation.

No production deployment, live exchange execution, or trading profitability claim was verified or made.


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
