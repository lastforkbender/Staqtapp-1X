from __future__ import annotations

import atexit
import os
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from . import diagnostics
from .config import selected


@dataclass(slots=True, frozen=True)
class QueuedResult:
    ok: bool
    queued: bool
    durable: bool
    batch_id: str
    operation_index: int
    api: str
    accepted_ns: int

    def __bool__(self) -> bool:
        return self.ok

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "queued": self.queued,
            "durable": self.durable,
            "batch_id": self.batch_id,
            "operation_index": self.operation_index,
            "api": self.api,
            "accepted_ns": self.accepted_ns,
        }


@dataclass(slots=True, frozen=True)
class BatchFlushResult:
    ok: bool
    batches: int
    operations: int
    results: tuple[Any, ...] = ()
    failures: tuple[Any, ...] = ()

    def __bool__(self) -> bool:
        return self.ok

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "batches": self.batches,
            "operations": self.operations,
            "results": self.results,
            "failures": self.failures,
        }


@dataclass(slots=True)
class _PendingBatch:
    batch_id: str
    vfs_key: tuple[str, str, str]
    calls: list[tuple[str, tuple, dict]]
    bytes_estimate: int
    created_ns: int
    timer: threading.Timer | None = None


_lock = threading.RLock()
_enabled = False
_max_operations = 100
_max_wait_ms = 5.0
_max_bytes = 8 * 1024 * 1024
_pending: dict[tuple[str, str, str], _PendingBatch] = {}
_inflight: dict[str, _PendingBatch] = {}
_condition = threading.Condition(_lock)
_stats = {
    "batches_committed": 0,
    "batches_failed": 0,
    "operations_queued": 0,
    "operations_committed": 0,
    "operations_coalesced": 0,
    "physical_commits_avoided": 0,
    "flushes": 0,
}
_transaction_runner: Callable[[list[tuple[str, tuple, dict]]], Any] | None = None
_pid = os.getpid()


def install_runner(runner: Callable[[list[tuple[str, tuple, dict]]], Any]) -> None:
    global _transaction_runner
    _transaction_runner = runner


def configure(*, enabled: bool | None = None, max_operations: int | None = None,
              max_wait_ms: float | int | None = None, max_bytes: int | None = None) -> dict[str, Any]:
    global _enabled, _max_operations, _max_wait_ms, _max_bytes
    if enabled is not None and not isinstance(enabled, bool):
        raise TypeError("write_batching must be a boolean")
    if max_operations is not None:
        if not isinstance(max_operations, int) or isinstance(max_operations, bool) or max_operations < 1:
            raise ValueError("batch_max_operations must be a positive integer")
    if max_wait_ms is not None:
        if isinstance(max_wait_ms, bool) or not isinstance(max_wait_ms, (int, float)) or max_wait_ms < 0:
            raise ValueError("batch_max_wait_ms must be a non-negative number")
    if max_bytes is not None:
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
            raise ValueError("batch_max_bytes must be a positive integer")
    if enabled is False:
        flush_all(reason="disable")
    with _lock:
        if enabled is not None:
            _enabled = enabled
        if max_operations is not None:
            _max_operations = max_operations
        if max_wait_ms is not None:
            _max_wait_ms = float(max_wait_ms)
        if max_bytes is not None:
            _max_bytes = max_bytes
    return info()


def enabled() -> bool:
    with _lock:
        return _enabled


def _estimate_call(name: str, args: tuple, kwargs: dict) -> int:
    return len(name.encode("utf-8")) + len(repr(args).encode("utf-8")) + len(repr(kwargs).encode("utf-8"))


def _new_batch(key: tuple[str, str, str]) -> _PendingBatch:
    return _PendingBatch(uuid.uuid4().hex, key, [], 0, time.time_ns())


def _schedule(batch: _PendingBatch) -> None:
    if _max_wait_ms <= 0:
        return
    timer = threading.Timer(_max_wait_ms / 1000.0, _timer_flush, args=(batch.vfs_key, batch.batch_id))
    timer.daemon = True
    batch.timer = timer
    timer.start()


def _timer_flush(key: tuple[str, str, str], batch_id: str) -> None:
    try:
        flush_key(key, expected_batch_id=batch_id, reason="timer")
    except Exception as exc:
        try:
            diagnostics.emit("write_batch_timer_failure_contained", error_type=type(exc).__name__, message=str(exc)[:512])
        except Exception:
            pass


def enqueue(name: str, args: tuple = (), kwargs: dict | None = None) -> QueuedResult:
    if not enabled():
        raise RuntimeError("write batching is not enabled")
    kwargs = {} if kwargs is None else dict(kwargs)
    key = selected()
    call_size = _estimate_call(name, args, kwargs)
    flush_before = False
    with _lock:
        batch = _pending.get(key)
        if batch is not None and batch.calls and (
            len(batch.calls) >= _max_operations or batch.bytes_estimate + call_size > _max_bytes
        ):
            flush_before = True
    if flush_before:
        flush_key(key, reason="threshold-preflush")
    with _lock:
        batch = _pending.get(key)
        if batch is None:
            batch = _new_batch(key)
            _pending[key] = batch
            _schedule(batch)
        index = len(batch.calls)
        batch.calls.append((name, tuple(args), kwargs))
        batch.bytes_estimate += call_size
        _stats["operations_queued"] += 1
        receipt = QueuedResult(True, True, False, batch.batch_id, index, name, time.time_ns())
        threshold = len(batch.calls) >= _max_operations or batch.bytes_estimate >= _max_bytes or _max_wait_ms == 0
    if threshold:
        flush_key(key, expected_batch_id=batch.batch_id, reason="threshold")
    return receipt


def _take_batch(key: tuple[str, str, str], expected_batch_id: str | None = None) -> _PendingBatch | None:
    with _lock:
        batch = _pending.get(key)
        if batch is None or (expected_batch_id is not None and batch.batch_id != expected_batch_id):
            return None
        _pending.pop(key, None)
        _inflight[batch.batch_id] = batch
        if batch.timer is not None:
            batch.timer.cancel()
            batch.timer = None
        return batch


@dataclass(slots=True, frozen=True)
class _BatchEngineResult:
    ok: bool
    results: tuple[Any, ...] = ()
    def __bool__(self) -> bool:
        return self.ok

def _run_batch(batch: _PendingBatch, reason: str) -> Any:
    if _transaction_runner is None:
        raise RuntimeError("batch transaction runner is not installed")
    # Run directly against the captured VFS identity. The batch key is the
    # authoritative target; timer threads must not depend on thread-local
    # selection state.
    from . import engine
    normalized = list(batch.calls)
    with engine.open_vfs(*batch.vfs_key):
        raw_results = engine.run_transaction_calls(normalized)
        # Publish acceleration metadata exactly once for the completed batch.
        # The VFS is already durable; metadata remains advisory and rebuildable.
        engine.rebuild_integrity_map()
        engine.rebuild_read_index()
    result = _BatchEngineResult(True, tuple(raw_results))
    with _lock:
        _stats["flushes"] += 1
        if bool(result):
            _stats["batches_committed"] += 1
            _stats["operations_committed"] += len(batch.calls)
            coalesced = max(0, len(batch.calls) - 1)
            _stats["operations_coalesced"] += coalesced
            _stats["physical_commits_avoided"] += coalesced
        else:
            _stats["batches_failed"] += 1
    try:
        diagnostics.emit(
            "write_batch_flushed",
            batch_id=batch.batch_id,
            operations=len(batch.calls),
            bytes_estimate=batch.bytes_estimate,
            reason=reason,
            ok=bool(result),
        )
    except Exception:
        pass
    finally:
        with _condition:
            _inflight.pop(batch.batch_id, None)
            _condition.notify_all()
    return result


def flush_key(key: tuple[str, str, str], *, expected_batch_id: str | None = None, reason: str = "explicit") -> BatchFlushResult:
    batch = _take_batch(key, expected_batch_id)
    if batch is None:
        return BatchFlushResult(True, 0, 0, (), ())
    try:
        result = _run_batch(batch, reason)
        if bool(result):
            return BatchFlushResult(True, 1, len(batch.calls), (result,), ())
        return BatchFlushResult(False, 1, len(batch.calls), (), (result,))
    except Exception as exc:
        with _condition:
            _stats["flushes"] += 1
            _stats["batches_failed"] += 1
            _inflight.pop(batch.batch_id, None)
            _condition.notify_all()
        return BatchFlushResult(False, 1, len(batch.calls), (), (exc,))


def flush_current(reason: str = "explicit") -> BatchFlushResult:
    try:
        key = selected()
    except Exception:
        return BatchFlushResult(True, 0, 0, (), ())
    return flush_key(key, reason=reason)


def flush_all(reason: str = "explicit") -> BatchFlushResult:
    with _lock:
        keys = list(_pending)
        failures_before = _stats["batches_failed"]
    results: list[Any] = []
    failures: list[Any] = []
    operations = 0
    batches = 0
    for key in keys:
        item = flush_key(key, reason=reason)
        batches += item.batches
        operations += item.operations
        results.extend(item.results)
        failures.extend(item.failures)
    # A timer may already have claimed a batch. Wait for that durable commit
    # boundary rather than reporting a false empty flush.
    with _condition:
        while _inflight:
            _condition.wait(timeout=0.1)
        timer_failed = _stats["batches_failed"] > failures_before
    if timer_failed and not failures:
        failures.append(RuntimeError("one or more in-flight batches failed"))
    return BatchFlushResult(not failures, batches, operations, tuple(results), tuple(failures))


def pending_count() -> int:
    with _lock:
        return sum(len(batch.calls) for batch in _pending.values()) + sum(len(batch.calls) for batch in _inflight.values())


def pending_writes() -> tuple[dict[str, Any], ...]:
    now = time.time_ns()
    with _lock:
        items = [(batch, "queued") for batch in _pending.values()] + [(batch, "committing") for batch in _inflight.values()]
        return tuple({
            "batch_id": batch.batch_id,
            "vfs": batch.vfs_key[0],
            "directory": batch.vfs_key[1],
            "folder": batch.vfs_key[2],
            "operations": len(batch.calls),
            "bytes_estimate": batch.bytes_estimate,
            "state": state,
            "oldest_pending_ms": (now - batch.created_ns) / 1_000_000.0,
        } for batch, state in items)


def info() -> dict[str, Any]:
    pending = pending_writes()
    with _lock:
        return {
            "enabled": _enabled,
            "batch_max_operations": _max_operations,
            "batch_max_wait_ms": _max_wait_ms,
            "batch_max_bytes": _max_bytes,
            "pending_batches": len(pending),
            "pending_operations": sum(item["operations"] for item in pending),
            "pending_bytes": sum(item["bytes_estimate"] for item in pending),
            "oldest_pending_ms": max((item["oldest_pending_ms"] for item in pending), default=0.0),
            "process_id": os.getpid(),
            **_stats,
        }


def _after_fork_child() -> None:
    global _pid
    with _lock:
        for batch in _pending.values():
            if batch.timer is not None:
                batch.timer.cancel()
        _pending.clear()
        _inflight.clear()
        _pid = os.getpid()
    try:
        diagnostics.emit("write_batch_fork_child_reset", process_id=_pid)
    except Exception:
        pass


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork_child)


def _shutdown_flush() -> None:
    try:
        flush_all(reason="shutdown")
    except Exception:
        pass


atexit.register(_shutdown_flush)
