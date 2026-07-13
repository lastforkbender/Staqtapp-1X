from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .errors import RecoveryError

_COPY_BUFFER = 1024 * 1024


@dataclass(frozen=True, slots=True)
class RevisionInfo:
    revision: str
    parent: str | None
    size: int
    created_ns: int
    event: str
    sequence: int

    def as_dict(self) -> dict:
        return asdict(self)


def revision_root(path: Path) -> Path:
    return path.with_name(f".{path.name}.revisions")


def _objects(path: Path) -> Path:
    return revision_root(path) / "objects"


def _timeline(path: Path) -> Path:
    return revision_root(path) / "timeline.json"


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as stream:
        while True:
            chunk = stream.read(_COPY_BUFFER)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> list[RevisionInfo]:
    index = _timeline(path)
    if not index.is_file():
        return []
    try:
        raw = json.loads(index.read_text(encoding="utf-8"))
        entries = [RevisionInfo(**item) for item in raw]
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise RecoveryError(f"invalid revision timeline: {index}") from exc
    for expected, entry in enumerate(entries, 1):
        if entry.sequence != expected:
            raise RecoveryError("revision timeline sequence is not contiguous")
    return entries


def _write_timeline(path: Path, entries: Iterable[RevisionInfo]) -> None:
    root = revision_root(path)
    root.mkdir(parents=True, exist_ok=True)
    payload = json.dumps([entry.as_dict() for entry in entries], indent=2, sort_keys=True).encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=".timeline.", suffix=".tmp", dir=root)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, _timeline(path))
        temporary = ""
        _fsync_directory(root)
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _store_object(path: Path, revision: str) -> Path:
    """Preserve an immutable object on an inode independent of the active VFS."""
    objects = _objects(path)
    objects.mkdir(parents=True, exist_ok=True)
    destination = objects / f"{revision}.sqtpp"
    if destination.is_file():
        if digest_file(destination) != revision:
            raise RecoveryError(f"revision object checksum mismatch: {revision}")
        return destination
    temporary = objects / f".{revision}.{os.getpid()}.{time.time_ns()}.tmp"
    try:
        with path.open("rb", buffering=0) as source, temporary.open("xb", buffering=0) as target:
            while True:
                chunk = source.read(_COPY_BUFFER)
                if not chunk:
                    break
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        if digest_file(temporary) != revision:
            raise RecoveryError("source changed while preserving immutable revision")
        try:
            os.link(temporary, destination)
        except FileExistsError:
            pass
        _fsync_directory(objects)
        return destination
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def record_current(path: Path, *, event: str, known_digest: str | None = None) -> RevisionInfo:
    revision = known_digest or digest_file(path)
    size = path.stat().st_size
    _store_object(path, revision)
    entries = _load(path)
    parent = entries[-1].revision if entries else None
    # Avoid duplicate bookkeeping for initialization or a repeated observation,
    # but preserve deliberate rollback events even when content is identical.
    if entries and entries[-1].revision == revision and event in {"observed", "initial"}:
        return entries[-1]
    info = RevisionInfo(revision, parent, size, time.time_ns(), event, len(entries) + 1)
    entries.append(info)
    _write_timeline(path, entries)
    return info


def ensure_current_recorded(path: Path) -> RevisionInfo:
    digest = digest_file(path)
    entries = _load(path)
    if entries and entries[-1].revision == digest:
        return entries[-1]
    return record_current(path, event="observed", known_digest=digest)


def list_revisions(path: Path, limit: int | None = None) -> tuple[RevisionInfo, ...]:
    ensure_current_recorded(path)
    entries = _load(path)
    if limit is not None:
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer or None")
        entries = entries[-limit:]
    return tuple(reversed(entries))


def revision_object(path: Path, revision: str) -> Path:
    if not isinstance(revision, str) or len(revision) != 64 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("revision must be a lowercase SHA-256 identifier")
    candidate = _objects(path) / f"{revision}.sqtpp"
    if not candidate.is_file():
        raise RecoveryError(f"revision does not exist: {revision}")
    if digest_file(candidate) != revision:
        raise RecoveryError(f"revision object is corrupt: {revision}")
    return candidate


def prune_revisions(path: Path, keep: int) -> int:
    if not isinstance(keep, int) or keep < 1:
        raise ValueError("keep must be a positive integer")
    ensure_current_recorded(path)
    entries = _load(path)
    retained = entries[-keep:]
    retained_ids = {entry.revision for entry in retained}
    # Publish the reduced authoritative timeline first. If interruption occurs
    # afterward, extra unreferenced objects are harmless and reclaimable. The
    # reverse order could leave a timeline referring to deleted history.
    rewritten = [RevisionInfo(e.revision, retained[i-1].revision if i else None, e.size, e.created_ns, e.event, i + 1) for i, e in enumerate(retained)]
    _write_timeline(path, rewritten)
    removed = 0
    for candidate in _objects(path).glob("*.sqtpp"):
        if candidate.stem not in retained_ids:
            candidate.unlink()
            removed += 1
    return removed


def trusted_revision_candidates(path: Path) -> tuple[RevisionInfo, ...]:
    """Return newest-first timeline entries without observing/recording current bytes."""
    return tuple(reversed(_load(path)))


def storage_report(path: Path) -> dict:
    """Return bounded revision-store accounting without modifying history."""
    entries = _load(path)
    referenced = {entry.revision for entry in entries}
    objects = list(_objects(path).glob("*.sqtpp")) if _objects(path).is_dir() else []
    object_sizes = {obj.stem: obj.stat().st_size for obj in objects}
    total = sum(object_sizes.values())
    referenced_bytes = sum(size for revision, size in object_sizes.items() if revision in referenced)
    return {
        "timeline_entries": len(entries),
        "object_count": len(objects),
        "referenced_objects": sum(1 for revision in object_sizes if revision in referenced),
        "total_bytes": total,
        "referenced_bytes": referenced_bytes,
        "reclaimable_bytes": total - referenced_bytes,
        "oldest_revision": entries[0].revision if entries else None,
        "newest_revision": entries[-1].revision if entries else None,
        "root": str(revision_root(path)),
    }
