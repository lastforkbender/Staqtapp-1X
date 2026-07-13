from __future__ import annotations

import hashlib
import mmap
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from .diagnostics import emit
from .errors import ConflictError, TransactionError
from .model import FileIdentity
from .revisions import ensure_current_recorded, record_current, revision_object

_LOCKS: dict[Path, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()
_COPY_BUFFER_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class SourceSpan:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError("invalid source span")

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class ReplacementBytes:
    data: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.data, bytes):
            raise TypeError("replacement data must be bytes")


SpanOperation = SourceSpan | ReplacementBytes


@dataclass(frozen=True, slots=True)
class MutationPlan:
    source_size: int
    operations: tuple[SpanOperation, ...]

    def __post_init__(self) -> None:
        if self.source_size < 0:
            raise ValueError("source_size must be non-negative")
        cursor = 0
        for operation in self.operations:
            if isinstance(operation, SourceSpan):
                if operation.end > self.source_size:
                    raise ValueError("source span exceeds source size")
                if operation.start < cursor:
                    raise ValueError("source spans are out of order or overlap")
                cursor = operation.end

    @property
    def destination_size(self) -> int:
        return sum(op.length if isinstance(op, SourceSpan) else len(op.data) for op in self.operations)

    @property
    def bytes_copied(self) -> int:
        return sum(op.length for op in self.operations if isinstance(op, SourceSpan))

    @property
    def bytes_written(self) -> int:
        return self.destination_size


@dataclass(frozen=True, slots=True)
class CommitStats:
    backup_mode: str
    destination_sha256: str
    bytes_copied: int
    bytes_written: int
    fsync_ns: int
    lock_ns: int


def plan_from_replacements(source_size: int, replacements: list[tuple[int, int, bytes]]) -> MutationPlan:
    ordered = sorted(replacements, key=lambda item: item[0])
    operations: list[SpanOperation] = []
    cursor = 0
    for start, end, data in ordered:
        if start < cursor or end < start or end > source_size:
            raise ValueError("overlapping or invalid mutation replacements")
        if cursor < start:
            operations.append(SourceSpan(cursor, start))
        if data:
            operations.append(ReplacementBytes(data))
        cursor = end
    if cursor < source_size:
        operations.append(SourceSpan(cursor, source_size))
    return MutationPlan(source_size, tuple(operations))


def _metadata(stat_result: os.stat_result) -> tuple[int, int, int, int]:
    return (stat_result.st_dev, stat_result.st_ino, stat_result.st_size, stat_result.st_mtime_ns)


def identity(path: Path, source: bytes | None = None) -> FileIdentity:
    stat = path.stat()
    if source is None:
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
    else:
        digest = hashlib.sha256(source).hexdigest()
    return FileIdentity(stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, digest)


@contextmanager
def _mapped_consistent_revision(path: Path) -> Iterator[tuple[object, FileIdentity]]:
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as source:
            after = os.fstat(stream.fileno())
            if _metadata(before) != _metadata(after):
                raise ConflictError("VFS changed while the transaction snapshot was being mapped")
            current = path.stat()
            if _metadata(current) != _metadata(after):
                raise ConflictError("VFS path changed while the transaction snapshot was being mapped")
            digest = hashlib.sha256(source).hexdigest()
            expected = FileIdentity(after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, digest)
            yield source, expected


def _metadata_matches(path: Path, expected: FileIdentity) -> bool:
    try:
        current = path.stat()
    except FileNotFoundError:
        return False
    return _metadata(current) == (expected.device, expected.inode, expected.size, expected.mtime_ns)


class InterProcessFileLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0, os.SEEK_END)
        if self.handle.tell() == 0:
            self.handle.write(b"\0"); self.handle.flush()
        self.handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()


def _thread_lock(path: Path) -> threading.RLock:
    key = path.resolve()
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


@contextmanager
def vfs_write_lock(path: Path):
    with _thread_lock(path):
        with InterProcessFileLock(path.with_name(f".{path.name}.lock")):
            yield


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _copy_range(source_fd: int, destination, start: int, length: int, digest) -> int:
    os.lseek(source_fd, start, os.SEEK_SET)
    remaining = length
    buffer = bytearray(min(_COPY_BUFFER_SIZE, max(1, remaining)))
    view = memoryview(buffer)
    copied = 0
    while remaining:
        count = min(len(buffer), remaining)
        read = os.readv(source_fd, [view[:count]]) if hasattr(os, "readv") else 0
        if not hasattr(os, "readv"):
            chunk = os.read(source_fd, count)
            read = len(chunk)
            if read:
                view[:read] = chunk
        if read <= 0:
            raise TransactionError("unexpected end of VFS while streaming a source span")
        block = view[:read]
        destination.write(block)
        digest.update(block)
        copied += read
        remaining -= read
    return copied


def _stream_file_copy(source: Path, destination_stream) -> None:
    with source.open("rb", buffering=0) as input_stream:
        digest = hashlib.sha256()
        _copy_range(input_stream.fileno(), destination_stream, 0, source.stat().st_size, digest)


def _install_backup(path: Path, backup: Path) -> str:
    directory = path.parent
    link_name = None
    try:
        fd, link_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".bak.link", dir=directory)
        os.close(fd); os.unlink(link_name)
        os.link(path, link_name)
        os.replace(link_name, backup)
        return "hardlink"
    except (AttributeError, OSError):
        if link_name:
            try: os.unlink(link_name)
            except FileNotFoundError: pass
        fd, copied = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".bak.tmp", dir=directory)
        try:
            with os.fdopen(fd, "wb", buffering=0) as stream:
                _stream_file_copy(path, stream)
                os.fsync(stream.fileno())
            os.replace(copied, backup)
            return "copy"
        finally:
            try: os.unlink(copied)
            except FileNotFoundError: pass


def atomic_replace_plan(path: Path, plan: MutationPlan, expected: FileIdentity) -> CommitStats:
    directory = path.parent
    backup = path.with_suffix(path.suffix + ".bak")
    tmp_new = None
    backup_mode = "none"
    fsync_ns = 0
    try:
        if plan.source_size != expected.size or not _metadata_matches(path, expected):
            raise ConflictError("VFS changed before the transaction could be committed")
        backup_mode = _install_backup(path, backup)
        fd_n, tmp_new = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=directory)
        digest = hashlib.sha256()
        with path.open("rb", buffering=0) as source, os.fdopen(fd_n, "wb", buffering=0) as destination:
            for operation in plan.operations:
                if isinstance(operation, SourceSpan):
                    _copy_range(source.fileno(), destination, operation.start, operation.length, digest)
                else:
                    destination.write(operation.data)
                    digest.update(operation.data)
            destination.flush()
            started = time.perf_counter_ns(); os.fsync(destination.fileno()); fsync_ns = time.perf_counter_ns() - started
        if not _metadata_matches(path, expected):
            raise ConflictError("VFS changed while the transaction was being prepared")
        os.replace(tmp_new, path); tmp_new = None
        _fsync_directory(directory)
        return CommitStats(backup_mode, digest.hexdigest(), plan.bytes_copied, plan.bytes_written, fsync_ns, 0)
    except Exception as exc:
        if isinstance(exc, ConflictError):
            raise
        raise TransactionError(f"failed to commit VFS transaction: {path}") from exc
    finally:
        if tmp_new:
            try: os.unlink(tmp_new)
            except FileNotFoundError: pass


def mutate(path: Path, operation: Callable[[object], MutationPlan], *, event: str) -> None:
    wait_started = time.perf_counter_ns()
    with vfs_write_lock(path):
        acquired_ns = time.perf_counter_ns()
        lock_wait_ns = acquired_ns - wait_started
        with _mapped_consistent_revision(path) as (source, expected):
            ensure_current_recorded(path)
            preparation_started = time.perf_counter_ns()
            plan = operation(source)
            preparation_ns = time.perf_counter_ns() - preparation_started
            if not isinstance(plan, MutationPlan):
                raise TypeError("transaction operation must return MutationPlan")
            if plan.destination_size == plan.source_size and len(plan.operations) == 1 and isinstance(plan.operations[0], SourceSpan):
                emit(event, path=str(path), no_op=True, lock_wait_ns=lock_wait_ns,
                     lock_hold_ns=time.perf_counter_ns()-acquired_ns, preparation_ns=preparation_ns)
                return
            commit_started = time.perf_counter_ns()
            stats = atomic_replace_plan(path, plan, expected)
            commit_ns = time.perf_counter_ns() - commit_started
            revision_started = time.perf_counter_ns()
            try:
                record_current(path, event=event, known_digest=stats.destination_sha256)
            except Exception as exc:
                emit("revision_record_deferred", path=str(path), error_type=type(exc).__name__)
            revision_ns = time.perf_counter_ns() - revision_started
        lock_hold_ns = time.perf_counter_ns() - acquired_ns
    emit(event, path=str(path), bytes_before=expected.size, bytes_after=plan.destination_size,
         bytes_copied=stats.bytes_copied, bytes_written=stats.bytes_written,
         write_amplification=(stats.bytes_written / max(1, expected.size)),
         backup_mode=stats.backup_mode, destination_sha256=stats.destination_sha256,
         fsync_ns=stats.fsync_ns, lock_ns=lock_wait_ns + lock_hold_ns,
         lock_wait_ns=lock_wait_ns, lock_hold_ns=lock_hold_ns,
         preparation_ns=preparation_ns, commit_ns=commit_ns, revision_ns=revision_ns)


def restore_backup(path: Path) -> None:
    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.is_file():
        raise TransactionError(f"backup does not exist: {backup}")
    with vfs_write_lock(path):
        fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".restore.tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb", buffering=0) as stream:
                _stream_file_copy(backup, stream); os.fsync(stream.fileno())
            os.replace(tmp, path); tmp = None
            _fsync_directory(path.parent)
        finally:
            if tmp:
                try: os.unlink(tmp)
                except FileNotFoundError: pass
    emit("backup_restored", path=str(path))


def restore_revision(path: Path, revision: str) -> str:
    """Atomically restore an immutable revision and retain the pre-rollback head."""
    source = revision_object(path, revision)
    with vfs_write_lock(path):
        ensure_current_recorded(path)
        # Revalidate after obtaining the lock; immutable objects are checksummed.
        source = revision_object(path, revision)
        fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".rollback.tmp", dir=path.parent)
        digest = hashlib.sha256()
        try:
            with source.open("rb", buffering=0) as input_stream, os.fdopen(fd, "wb", buffering=0) as output:
                while True:
                    chunk = input_stream.read(_COPY_BUFFER_SIZE)
                    if not chunk:
                        break
                    output.write(chunk); digest.update(chunk)
                output.flush(); os.fsync(output.fileno())
            if digest.hexdigest() != revision:
                raise TransactionError(f"revision object changed during rollback: {revision}")
            os.replace(tmp, path); tmp = None
            _fsync_directory(path.parent)
            record_current(path, event="rollback", known_digest=revision)
        finally:
            if tmp:
                try: os.unlink(tmp)
                except FileNotFoundError: pass
    emit("revision_rolled_back", path=str(path), revision=revision)
    return revision


def repair_mutate(path: Path, operation: Callable[[object], MutationPlan], *, event: str) -> CommitStats:
    """Commit a recovery plan without preserving the known-corrupt source as a revision."""
    lock_started = time.perf_counter_ns()
    with vfs_write_lock(path):
        with _mapped_consistent_revision(path) as (source, expected):
            plan = operation(source)
            if not isinstance(plan, MutationPlan):
                raise TypeError("repair operation must return MutationPlan")
            stats = atomic_replace_plan(path, plan, expected)
            try:
                record_current(path, event=event, known_digest=stats.destination_sha256)
            except Exception as exc:
                emit("revision_record_deferred", path=str(path), error_type=type(exc).__name__)
    lock_ns = time.perf_counter_ns() - lock_started
    emit(event, path=str(path), bytes_before=expected.size, bytes_after=plan.destination_size,
         bytes_copied=stats.bytes_copied, bytes_written=stats.bytes_written,
         write_amplification=(stats.bytes_written / max(1, expected.size)),
         backup_mode=stats.backup_mode, destination_sha256=stats.destination_sha256,
         fsync_ns=stats.fsync_ns, lock_ns=lock_ns)
    return CommitStats(stats.backup_mode, stats.destination_sha256, stats.bytes_copied,
                       stats.bytes_written, stats.fsync_ns, lock_ns)
