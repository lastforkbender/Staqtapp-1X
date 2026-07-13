# Maintenance Guide

Use `optimize_vfs()` to verify and canonicalize the selected VFS and rebuild advisory acceleration metadata. It is safe to run repeatedly; a canonical VFS produces a no-op physical commit.

Use `compact_vfs(keep_revisions=N)` only when the desired immutable-history retention window is known. The newest `N` timeline entries are retained. Older unreferenced revision objects are removed after the new timeline is durably published.

Neither API removes the `.bak` recovery file. Both APIs preserve the universal non-halting public contract.
