# Staqtapp 1X 1.4.5 — Explicit Typed Values and Range Reads

Adds a deterministic, non-executable typed codec and public APIs `set_value`, `get_value`, `inspect_value`, `validate_value`, `read_range`, and `iter_value`.

Supported exact built-in types: `None`, `bool`, arbitrary precision `int`, IEEE-754 `float` including signed zero/NaN/infinities, `complex`, `str`, `bytes`, `list`, `tuple`, `dict` with hashable typed keys, `set`, and `frozenset`.

The `staqt-json-v1` codec uses canonical UTF-8 JSON with explicit tags. Dictionary entries and set members are sorted by canonical encoded bytes. It never executes payload content and does not use pickle for the new typed path. Cycles, unsupported classes, malformed tags, noncanonical payloads, excessive depth, excessive nodes, and excessive encoded size are rejected through the non-halting `CallFailure` contract.

`set_value` is transaction-capable and participates in one-lock, one-rewrite, one-revision all-or-nothing transactions. Immutable revisions preserve typed data byte-for-byte.

`read_range` and `iter_value` expose bounded slices/chunks of the canonical typed payload. Collection item indexing is intentionally deferred to a future indexed collection format.
