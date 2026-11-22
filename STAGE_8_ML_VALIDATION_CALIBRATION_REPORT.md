# Stage 8 — ML Validation, Calibration, and Model Lifecycle

## Scope
Initial hardening of existing ML lifecycle components. This stage does not replace the RandomForest, XGBoost, or River architecture and does not claim that model predictions are profitable.

## Implemented
- Added `learning/model_lifecycle.py` with explicit RNG seeding, SHA-256 artifact digest calculation and verification, held-out classification metrics (accuracy, macro precision/recall/F1, multiclass Brier score and expected calibration error), and realized-return/cost-adjusted trading metrics.
- Model registration records the artifact SHA-256 digest in the existing registry metrics JSON.
- Promotion verifies the registered artifact digest before changing champion state.
- Rollback resolves and verifies a compatible target before demoting the current champion. Missing, mismatched, or tampered targets fail closed; rollback to the current champion is rejected.
- Added deterministic utility tests in `tests/test_stage8_ml_lifecycle.py`.

## Existing infrastructure retained
- Existing timestamp-ordered walk-forward validation and purge support.
- Existing prediction/outcome records and champion/challenger registry.
- Existing promotion gate and drift monitor.
- Existing RF/XGBoost and optional River components.

## Verification status
- PR #42 created as draft.
- Automated workflow results and local test execution have not yet been verified for this branch. Do not treat this stage as CI-green or merge-ready until checks complete.

## Acceptance gaps requiring further work
- End-to-end reproducible training and persisted training/evaluation provenance.
- Explicit untouched out-of-sample evaluation separated from model selection and calibration.
- Verify calibration metrics and promotion thresholds are consistently applied to the actual model family; current manager maps a single model into shared RF/XGB gate slots.
- Verify multiple regime evaluation uses genuinely held-out predictions, not in-regime fitting.
- Integrate verified metrics into promotion evidence and remove/deprecate legacy F1-derived economic approximations from any promotion path.
- Validate River-specific lifecycle and artifact handling.
- Add manager-level tests for failed promotion, missing evaluation evidence, artifact tampering, promotion, and rollback preserving the current champion on failure.
- Drift coverage should include prediction-distribution changes and feature/performance baselines with documented sampling requirements.
- Model registry needs durable artifact lineage/hash and evaluation provenance beyond metrics JSON, with migration compatibility review.

## Decision
Stage 8 remains incomplete and PR #42 remains draft. No model is declared production-ready based on successful training alone; actual effectiveness must be reported from recorded out-of-sample predictions and aligned realized returns after costs.
