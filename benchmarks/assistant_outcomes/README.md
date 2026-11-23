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
