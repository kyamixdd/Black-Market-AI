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
