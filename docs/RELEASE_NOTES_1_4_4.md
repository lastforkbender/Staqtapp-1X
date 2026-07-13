# Staqtapp 1X 1.4.4 — Immutable Revisions and Rollback

## Summary

Staqtapp 1.4.4 adds content-addressed immutable revisions to the 1.4 transactional engine. Every committed VFS state is identified by its SHA-256 digest and preserved in a per-VFS object store. Rollback validates and restores an immutable object through an atomic replacement while retaining the pre-rollback head as history.

## Public API

- `list_revisions(limit=None)` — newest-first revision timeline.
- `rollback_revision(revision)` — validated, atomic rollback to a SHA-256 revision.
- `prune_revisions(keep=32)` — bounded retention of recent timeline entries and objects.

All three calls obey the 1.4.2 non-halting contract and return `CallFailure` on ordinary application errors.

## Durability model

- Revision IDs are lowercase SHA-256 content identifiers.
- Objects are installed by hard link where possible, with a bounded 1 MiB streaming-copy fallback.
- Object checksums are revalidated before rollback.
- Rollback writes a temporary destination, fsyncs it, atomically replaces the active VFS, and fsyncs the directory.
- Timeline publication uses an fsynced temporary JSON file and atomic replacement.
- The active VFS remains authoritative. A missing final timeline entry is reconciled from the current VFS on the next revision query.
- Existing SQTI sidecars are invalidated after rollback.

## Compatibility

Existing 1.4.3 calls and transaction semantics are unchanged. `listfiles()` now reports `revision_kind="sha256-content"`, while its previous filesystem generation identifier remains available as `filesystem_generation`.

## Validation

48 tests pass, including legacy regression, transaction sessions, non-halting failures, multiprocessing, streaming writer safety, content-addressed revision creation, exact rollback, corrupt object rejection, interrupted rollback, timeline reconciliation, pruning, and concurrent commit timeline integrity.
