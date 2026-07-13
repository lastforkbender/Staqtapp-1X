# Staqtapp 1X 1.5.2 — Adaptive Write Batching

Version 1.5.2 adds opt-in, process-local write coalescing above the proven all-or-nothing transaction engine.

## Public API

- `configure(write_batching=True, batch_max_operations=100, batch_max_wait_ms=5, batch_max_bytes=8388608)`
- `flush_writes()`
- `pending_writes()`
- `write_batching_info()`
- `QueuedResult`
- `BatchFlushResult`

Immediate durability remains the default. A `QueuedResult` confirms acceptance into memory, not durable commit. `flush_writes()` is the explicit durability barrier.

## Guarantees

- batches never cross VFS boundaries;
- call order is preserved;
- explicit transactions flush prior queued work and are never merged;
- consistency reads flush the selected VFS first;
- maintenance and recovery flush first;
- threshold and timer flushes use one transaction, one revision, one integrity publication, and one sidecar invalidation cycle;
- failed batches commit nothing and return a contained failure;
- inherited queues are cleared in forked children;
- shutdown performs a best-effort flush.

## Scope

Batching is process-local. A queued acknowledgement is not a durability guarantee. Applications requiring immediate durability should leave batching disabled, call `flush_writes()`, or use explicit `run_transaction()`.
