# Staqtapp 1X 1.4.9 — Gorilla Benchmark & Endurance Validation

Staqtapp 1.4.9 adds a reproducible hostile-scale benchmark harness and publishes honest quick and standard baseline results. It does not change the SQTPP storage format or public operational API.

## Added

- `tools/gorilla_benchmark.py`
- quick and standard workload profiles
- JSON, CSV, and Markdown benchmark outputs
- write-size, transaction-scaling, variable-count, typed-value, corruption/recovery, and non-halting suites
- deterministic random corruption using a recorded seed
- environment, backend, peak-RSS, and report SHA-256 metadata
- executable regression tests for the benchmark harness itself

## Baseline result

The included standard run completed 37/37 cases successfully. No VFS corruption, failed repair, or escaped ordinary API failure was observed.

These figures are environment-specific and are not universal performance claims. See `docs/GORILLA_BENCHMARK_REPORT_1_4_9.md` and the machine-readable result files.
