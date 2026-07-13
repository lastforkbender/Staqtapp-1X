# Staqtapp 1X 1.5.0 — Performance Corrections and Scale Hardening

## Added

- Validated `.sqti` index inspection and forced rebuild APIs.
- True mmap-bounded raw payload range reads.
- Base64-aligned partial decoding for finite typed-value range reads.
- Fine-grained mutation timing: lock wait, lock hold, preparation, commit, revision publication, and fsync.
- Transaction overlay supersession diagnostics.
- Revision-store capacity and reclaimable-byte reporting.

## Public APIs

- `read_payload_range(name, start=0, length=None)`
- `read_index_info()`
- `rebuild_read_index()`
- `revision_storage_report()`

## Compatibility

All pre-1.5.0 APIs and the universal non-halting contract remain intact. The `.sqti` index and integrity maps remain advisory, rebuildable sidecars and never become authoritative storage.

## Scope honesty

This release improves bounded reads and observability but does not claim a fully record-native mutation parser. The transaction overlay still parses the logical VFS image once per commit; it avoids repeated physical rewrites and collapses final state before the one durable commit.
