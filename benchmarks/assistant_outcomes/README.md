# Assistant outcome benchmark

Dataset: `dataset-v1.json` (benchmark schema version 1.0.0).

## Dimensions

- Intent exact match: parsed registered tool set equals the expected tool set.
- Tool registry safety: every tool referenced by the benchmark is registered, available, read-only, and does not change application state.
- Memory top-1 relevance: the expected relevant memory is ranked first by the existing bounded retrieval scorer.
- Completion accuracy: deterministic end-to-end requests reach the expected task state and status using a fixed local test bridge.

The benchmark is intentionally deterministic and uses no market network requests, paid model provider, or user data. Completion cases use fixed sample values and verify task lifecycle, not market forecast accuracy.

## Run

From the repository root:

```bash
python -m benchmarks.assistant_outcomes.evaluate --report benchmarks/assistant_outcomes/reports/v1.0.0.json
```

The report records the dataset version, UTC generation time, sample counts, aggregate metrics, and per-case results. A report is a measurement, not evidence of improvement by itself.

## Baseline and promotion

Run the benchmark on the approved baseline commit and preserve its generated report as a versioned baseline artifact. Then run the candidate with:

```bash
python -m benchmarks.assistant_outcomes.evaluate \
  --report candidate-report.json \
  --baseline approved-baseline.json \
  --enforce-promotion
```

The promotion gate requires each metric to meet the dataset policy and, by default, not regress against the baseline. Missing baseline prevents promotion. The GitHub Actions workflow supports manual baseline comparison and scheduled measurement; each run uploads a SHA-versioned report artifact.

Do not update an approved baseline merely to make a candidate pass. Review the per-case differences, confirm the benchmark dataset version, and approve baseline changes deliberately.

## Limitations

This is a compact regression benchmark, not a comprehensive measure of assistant quality. It does not establish calibrated confidence, production memory relevance, real-time monitoring uptime, model factuality across arbitrary prompts, or trading profitability. Expand the dataset with reviewed cases before using it as a broader quality claim.


## Measured baseline v1.0.0

The initial benchmark was executed in GitHub Actions on 2026-11-23 against source commit `7c975d69b17aa7d13d9f0ea3f04786073c38ef8a` (workflow run 45147538731). The full per-case report is retained as the workflow artifact; the versioned baseline summary is committed at `reports/baseline-v1.0.0.json`.

Measured metrics:

| Metric | Baseline |
|---|---:|
| Intent exact match | 0.7143 (10/14) |
| Tool registry safety | 1.0000 (11/11) |
| Memory top-1 relevance | 1.0000 (3/3) |
| Completion accuracy | 1.0000 (3/3) |

The baseline did not meet the 0.90 intent threshold and is not promotion-eligible. Four intent cases exposed deterministic classification issues: scanner request also matched market snapshot; trade history also matched historical candles; portfolio risk also matched paper account; and an unresolved pronoun request did not trigger clarification. These are recorded as baseline findings, not silently corrected in the evaluation data.

To evaluate a future candidate against this baseline, use the manual workflow's `baseline_report` input with `benchmarks/assistant_outcomes/reports/baseline-v1.0.0.json`. A candidate that still fails policy thresholds will be rejected by the promotion gate. Keep the original baseline immutable; approve a new baseline version only after reviewing dataset changes and measured results.


## Current repository status — 23 November 2026

This document is maintained against the `black-market-ai-beta` branch. The latest application-source baseline reviewed for the comprehensive product audit is `49e6841215303ed296ced4fc1ef3039b9959426d`. Subsequent commits in this branch update documentation only; verify the branch head before treating this snapshot as current runtime or CI evidence.

Current product classification: **Windows desktop beta candidate; hosted website private preview**. The application is local-first market research and paper-trading software. Paper trading is the only execution mode; no real-money exchange order execution is supported or verified. The deterministic assistant is read-only by default; an optional OpenAI-compatible endpoint may provide interpretation. ML training and model registration do not establish profitability or promotion without the configured validation evidence.

Current audit corrections and outstanding items:
- A root `LICENSE` file exists and identifies the project as proprietary. Older statements that the root license is absent are stale.
- Existing CI run #605 passed for an earlier source commit, not the current source baseline. Fresh current-head CI and release-artifact verification remain required.
- The website is a private preview with a shared-password session gate, not a multi-user SaaS identity and isolation system. Hosted backend, durable storage, streaming and restore acceptance remain release gates.
- The repository tree contains 30 generated compressed shutdown database backups under `data/backups/` with the `.db.gz` suffix. The current ignore rules do not exclude that suffix. Their contents were not inspected in this audit; review them safely and remove generated database artifacts from version control after confirming data-handling requirements.
- The application does not encrypt SQLite databases, model artifacts or backup archives. SHA-256 manifests provide integrity checking, not confidentiality.

This status block records source/documentation evidence only. It does not claim a live deployment test, fresh training run, new backtest, current-head CI pass, security certification or trading performance result.
