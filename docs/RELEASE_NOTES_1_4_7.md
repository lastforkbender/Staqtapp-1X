# Staqtapp 1X 1.4.7 — Region Integrity Maps and Deep Verification

Adds an advisory, versioned, checksummed integrity sidecar for every selected VFS.

## Public API

- `rebuild_integrity_map()`
- `verify_integrity(deep=True)`
- `integrity_report(rebuild_if_missing=False, deep=True)`

The map records the committed VFS identity plus SHA-256 checksums for structural containers, history blocks, variable records, and individual payloads. It is atomically published, never authoritative, and may always be rebuilt from the VFS.

Deep verification localizes damaged regions. Missing, malformed, forged, stale, truncated, and corrupted states are contained by the public non-halting API contract.
