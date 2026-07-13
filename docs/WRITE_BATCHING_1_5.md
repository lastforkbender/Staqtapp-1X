# Write batching operations guide

Enable batching only when delayed durability is acceptable:

```python
staqtapp.configure(
    write_batching=True,
    batch_max_operations=100,
    batch_max_wait_ms=5,
    batch_max_bytes=8 * 1024 * 1024,
)
```

Direct mutation calls return `QueuedResult`. The receipt is truthy and records the batch ID and operation index, but `durable` remains false. Use `flush_writes()` as a durability barrier.

Reads including `findvar`, `loadvar`, `get_value`, and bounded range reads flush pending writes before observing state. Explicit transactions and maintenance operations also flush first.

A batch is all-or-nothing. One invalid operation rejects the entire physical transaction. This is intentionally stronger than independent direct-call semantics and is why batching is opt-in.

Do not rely on queued writes surviving abrupt process termination. For strict durability, disable batching or flush before acknowledging work externally.
