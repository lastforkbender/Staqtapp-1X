# Staqtapp 1X 1.4.6 — Accelerated Codec Backends

Staqtapp 1X 1.4.6 introduces a verified JSON backend abstraction for the `staqt-json-v1` typed-value codec.

- `orjson` is optional through the `fastjson` extra.
- standard-library `json` remains the reference implementation and guaranteed fallback.
- `auto` selects `orjson` only after canonical byte and decode equivalence checks pass.
- forced `orjson` failures are contained by the public non-halting API contract.
- canonical bytes, checksums, immutable revision IDs, transactions, and rollback remain backend-independent.
- `json_backend_info()` exposes the selected backend and verification state.
- `configure(json_backend="auto" | "orjson" | "stdlib")` controls routing.

Install acceleration with:

    pip install "staqtapp[fastjson]"
