# Staqtapp 1X 1.5.1 — Optimize and Compact

## New public APIs

- `optimize_vfs()` canonicalizes the selected VFS when needed, verifies logical equivalence, republishes the integrity map, and rebuilds the validated `.sqti` read index.
- `compact_vfs(keep_revisions=32)` performs optimization, atomically reduces the revision timeline, deletes only now-unreferenced immutable revision objects, and removes recognized disposable temporary artifacts.

## Safety rules

- Logical records, typed values, locks, histories, and opaque records are preserved.
- Byte-identical optimization is detected before commit, so the current `.bak` recovery image is not refreshed by a no-op.
- Compaction publishes the reduced timeline before deleting objects. Interruption may leave reclaimable extras, but never a timeline referring to deleted history.
- Revision pruning is serialized against VFS writers.
- `.bak`, active VFS, revision timeline, revision objects still referenced by the retained timeline, integrity maps, and unrelated files are never treated as disposable.
- All public failures return `CallFailure` and do not halt later execution.

## Validation

111 automated tests pass, including complete 1.5.0 regression coverage and maintenance-specific interruption, corruption-boundary, exact-value, backup, retention, and continuation tests.
