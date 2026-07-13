## 1.5.3

- Documentation-only release with updated README, benchmark overview image, and Core API Quick Reference PDF.
- Engine behavior remains unchanged from 1.5.2.

# Changelog

## 1.5.2
- Added opt-in process-local adaptive write batching.
- Added queued and flush result types plus operational inspection APIs.
- Added timer, operation-count, and byte thresholds.
- Added read/maintenance consistency barriers and fork-child queue reset.
- Coalesced revision, integrity-map, and `.sqti` invalidation work through one transaction commit.

# 1.4.8

- Added checksum-proven surgical recovery for localized variable corruption.
- Added `repair_vfs()` with non-halting structured failure behavior.
- Made immutable revision objects inode-independent from the active VFS.
- Added atomic multi-region restoration and post-repair deep verification.
- Expanded validation to 95 tests.

# Changelog

## 1.4.4

- Added SHA-256 content-addressed immutable VFS revisions.
- Added atomic validated rollback and bounded revision pruning.
- Added revision timeline reconciliation and filesystem-generation compatibility metadata.
- Added exceptional tests for corruption, interruption, concurrency, pruning, and non-halting continuation.

## 1.4.2 — 2026-07-13

- Added universal non-halting containment for callable public APIs.
- Added immutable, false-valued `CallFailure` results carrying API, error type, message, and bounded argument context.
- Preserved all successful legacy return values.
- Changed direct call failures, unsupported calls, validation failures, and transaction failures from escaping exceptions to contained results.
- Changed mapped execution to return one result per input and continue after individual failures.
- Added process-pool failure fallback to contained in-process execution.
- Added diagnostic `api_failure_contained` events and counts.
- Added continuation, mixed batch, malformed-call, invalid-configuration, and diagnostic tests.

## 1.4.1 — 2026-07-13

- Added immutable `MutationPlan`, `SourceSpan`, and `ReplacementBytes` operation types.
- Replaced complete destination `bytes` assembly for supported mutations with a streamed temporary-destination writer.
- Calculates the destination SHA-256 during the same streaming pass.
- Preserved hard-link backups with a bounded-buffer durable copy fallback.
- Preserved per-VFS locking, revision conflict checks, fsync, atomic replace, recovery, and disposable `.sqti` invalidation.
- Added bounded 1 MiB reusable source-copy buffering and write metrics for bytes copied, bytes written, write amplification, lock duration, and fsync duration.
- Routed `addvar`, `appvar`, `changevar`, `renamevar_stx`, `removevar`, and `joinvars` through the streaming writer.
- Added interruption-before-replace, backup recovery, mutation compatibility, and span-plan tests.

## 1.4.0 — 2026-07-13

- Replaced routine full-file object parsing with read-only mmap snapshots and compact byte-span indexes.
- Added a disposable, checksummed `.sqti` sidecar index.
- Added adaptive 32-bit and 64-bit sidecar offsets for compact small/medium indexes and large-file compatibility.
- Added a mapped CRC32 lookup table with byte-level collision verification.
- Added a compressed physical-order name table for fast complete listings.
- Made variable payload materialization lazy; only requested payloads are copied.
- Made lock and stalk-history parsing lazy.
- Replaced record-count cache limits with byte-weighted and entry-count bounds.
- Removed full-file SHA-256 work from ordinary `listfiles()` metadata calls.
- Added hard-link transaction backups where supported, with durable copy fallback.
- Reduced serialization from repeated whole-file splicing to one destination assembly.
- Reduced repeated full-file conflict hashing by reading one consistent transaction revision.
- Added mapped-engine, sidecar invalidation, encoded-search, and backup tests.

## 1.3.0 — 2026-07-13

- Introduced second-generation package engine while retaining Staqtapp 1.x.x.
- Added typed errors and machine-readable version metadata.
- Added mmap-backed structural reads and compact in-memory record maps.
- Added per-VFS transactional writes, backups, conflict checks, fsync, and atomic replace.
- Prevented destructive `makevfs` overwrite.
- Enforced operation locks.
- Removed false-success behavior from missing remove/join operations.
- Added plain-text normalization and safe arbitrary-text value extension.
- Added verification, migration, recovery, CLI, diagnostics, and spawn dispatch tests.
- Disabled generated-code and unrecovered experimental features explicitly.

## 1.4.3

- Added non-halting all-or-nothing multi-operation transactions.
- Added `run_transaction`, `run_vfs_transaction`, and immutable `TransactionResult`.
- Added read-your-own-writes across pending mutations.
- Collapsed successful transaction batches into one locked snapshot, one mutation plan, one backup, and one atomic replacement.
- Added complete rollback on duplicate, lock, validation, malformed-call, and unsupported-operation failures.
- Added transaction-session regression coverage; full suite is 34 tests.

## 1.4.5
- Added deterministic explicit typed values, complex numbers, nested collections, exact type validation, raw range/chunk reads, transaction integration, and non-halting malformed-value containment.

## 1.4.6

- Added optional verified `orjson` acceleration via the `fastjson` extra.
- Added canonical JSON backend routing with stdlib reference fallback.
- Added `json_backend_info()` and `configure(json_backend=...)`.
- Added byte-equivalence, fallback, revision identity, transaction, Unicode, and failure-containment tests.

## 1.4.7
- Added versioned region integrity maps and deep checksum verification.
- Added atomic integrity-map publication and rebuild APIs.
- Added localized record/payload corruption reports.
- Preserved disposable SQTI invalidation and non-halting error containment.

## 1.4.9
- Added reproducible Gorilla benchmark and hostile-scale validation harness.
- Added machine-readable JSON/CSV plus Markdown reports.
- Added transaction, variable-count, typed-value, corruption/recovery, and non-halting benchmark suites.
- Added benchmark-harness regression coverage and packaged quick/standard baselines.
