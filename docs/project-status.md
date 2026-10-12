# SensorWatch delivery record — 2026-10-12

Authorized destination: https://github.com/oshada28nilendra-debug/sensorwatch
Feature branch: feat/sensorwatch-mvp. No merge or deployment performed.

## Implemented

Single-sensor timestamp/value CSV validation, separate earlier reference period, exact-grid missing-slot expansion, robust median/MAD spike rule, overlapping range-bounded stuck-run detection, seeded Isolation Forest feature model, shared-eligibility numeric evaluation, independent missing-slot confusion metrics, CLI, localhost browser signal/evidence explorer and complete JSON export.

## Actual verification

- Exact dependencies installed in a fresh Python 3.12 virtual environment; package installation succeeded.
- 33 Python tests passed in the clean environment, covering core logic, failure cases, labelled evaluation, deterministic real Isolation Forest, web and CLI.
- Real Chromium 133 checks passed: synthetic demo, signal plot, missing-only filter, exported JSON contents, real CSV upload, no-label state, malformed-upload reset, mobile overflow and no JavaScript errors.
- Desktop/mobile screenshots inspected. Browser testing caught table overflow at 390px; fixed with constrained grid child widths and rerun successfully.
- Read-only code review found an overlapping flat-run edge case and a missing-label evaluation restriction. Both fixed, regression-tested and re-reviewed with no remaining material issues.
- The measured report is reports/synthetic-evaluation.json. Seed 20261012, 300 reference readings, 400 analysis slots, 379 numeric-eligible rows. Rules TP/FP/FN = 36/0/0; Isolation Forest = 30/58/6; missing reconstruction = 9/0/0. Model fit 72.84 ms and score 4.88 ms in this single clean-environment run, not throughput guarantees.

Synthetic fixture results are not production evidence. No real users, adoption or deployment claimed. Model false positives and all scope limits are disclosed in README. The GitHub Actions workflow runs Python, CLI evaluation and browser verification; remote status must be checked on the PR, not inferred from local tests.
