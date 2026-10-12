# SensorWatch MVP contract

Single numeric sensor, timezone-aware timestamp/value CSVs. Separate reference and analysis files; no fitting on evaluation labels. Expected cadence is explicit. Require exact cadence-grid alignment, ordered unique timestamps. Empty values and absent interior slots are missing; never interpolate. No leading/trailing outage inference without external bounds. Cap inputs at 5 MiB each, 10,000 rows and 20,000 expanded slots.

Rules: reference median/MAD robust score (3.5 threshold); std/floor fallback disclosed for zero MAD. Stuck runs of at least five consecutive readings within configurable absolute epsilon flag the whole run retrospectively. Gaps break runs. Model: 100-tree seeded Isolation Forest on value, absolute previous delta, trailing five-point population standard deviation; fixed 0.05 contamination, fitted only on finite contiguous reference windows. Four-point warmup after gaps, shared eligibility for numeric comparison. No per-event point adjustment. Missing-slot detection evaluated separately from numeric models.

CLI plus stateless localhost Flask browser UI, SVG signal plot, filterable flags and downloadable JSON. All imported strings rendered as text. Bundled deterministic synthetic training/test/labels, no claim of production accuracy. Thresholds are illustrative defaults, not tuned on test labels.
