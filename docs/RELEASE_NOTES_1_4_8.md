# Staqtapp 1X 1.4.8 — Surgical Recovery

Adds trustworthy, localized repair using the 1.4.7 region integrity map and immutable revision objects.

## Public API

- `repair_vfs(strategy="surgical", source="latest-valid-revision")`

Repairs only failed variable record/payload regions whose exact expected SHA-256 bytes can be recovered from a valid immutable revision. Aggregate TQPT checksum failures are tolerated only when fully explained by localized record failures. Structural corruption, missing or forged maps, corrupt revision objects, unavailable provenance, conflicts, and interrupted replacement are refused and returned through the non-halting `CallFailure` contract.

Revision objects are now copied onto independent inodes rather than hard-linked to the active VFS, preventing external in-place corruption of the active file from mutating preserved history. Repairs use one lock, one span-patch plan, one streamed rewrite, one backup, one `fsync`, and one atomic replacement, followed by parse validation and deep integrity verification.
