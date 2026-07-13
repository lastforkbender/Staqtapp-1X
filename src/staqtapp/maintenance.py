from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any

from . import integrity
from .diagnostics import emit
from .parser import parse_vfs, parse_vfs_source, serialize_mutation_plan, serialize_vfs
from .revisions import prune_revisions, storage_report
from .snapshot import MappedVFS, sidecar_path
from .transaction import mutate, vfs_write_lock


def _logical_fingerprint(image) -> str:
    """Hash logical records/locks/history independently of source layout."""
    digest = hashlib.sha256()
    for record in image.records:
        name = getattr(record, "name", None)
        if name is None:
            digest.update(b"O\0")
            digest.update(record.raw)
        else:
            digest.update(b"V\0")
            digest.update(name.encode("ascii"))
            digest.update(b"\0")
            digest.update(record.payload)
        digest.update(b"\xff")
    for name, values in image.locks.items():
        digest.update(b"L\0" + name.encode("utf-8") + b"\0")
        for value in values:
            digest.update(value.encode("utf-8") + b"\0")
    for name, values in image.histories.items():
        digest.update(b"H\0" + name.encode("utf-8") + b"\0")
        for value in values:
            digest.update(value.encode("utf-8") + b"\0")
    return digest.hexdigest()


def optimize_vfs(path: Path, directory: str, folder: str) -> dict[str, Any]:
    """Canonicalize physical layout and rebuild advisory acceleration metadata."""
    started = time.perf_counter_ns()
    before_size = path.stat().st_size
    before_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    before = parse_vfs(path, directory, folder)
    logical_before = _logical_fingerprint(before)

    canonical = serialize_vfs(before)
    changed_layout = canonical != before.source
    if changed_layout:
        def operation(source):
            image = parse_vfs_source(path, source, directory, folder)
            return serialize_mutation_plan(image)
        mutate(path, operation, event="vfs_optimized")
    else:
        emit("vfs_optimized", path=str(path), no_op=True, bytes_before=before_size, bytes_after=before_size)
    after = parse_vfs(path, directory, folder)
    logical_after = _logical_fingerprint(after)
    if logical_before != logical_after:
        raise RuntimeError("optimization changed logical VFS content")

    integrity_info = integrity.publish_map(path, directory, folder)
    try:
        sidecar_path(path).unlink(missing_ok=True)
    except OSError:
        pass
    with MappedVFS(path, directory, folder) as snapshot:
        index_info = snapshot.index_info()

    after_size = path.stat().st_size
    after_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = {
        "ok": True,
        "changed": before_digest != after_digest,
        "bytes_before": before_size,
        "bytes_after": after_size,
        "bytes_reclaimed": max(0, before_size - after_size),
        "sha256_before": before_digest,
        "sha256_after": after_digest,
        "variables": len(after.variable_map()),
        "integrity_map": integrity_info,
        "read_index": index_info,
        "elapsed_ns": time.perf_counter_ns() - started,
    }
    emit("vfs_optimize_completed", path=str(path), changed=result["changed"],
         bytes_before=before_size, bytes_after=after_size,
         bytes_reclaimed=result["bytes_reclaimed"])
    return result


def _cleanup_disposable(path: Path) -> tuple[int, int]:
    """Remove only known temporary artifacts; never backups or authoritative files."""
    patterns = (
        f".{path.name}.*.tmp",
        f".{path.name}.*.bak.tmp",
        f".{path.name}.*.restore.tmp",
        ".timeline.*.tmp",
        ".integrity.*.tmp",
    )
    removed = 0
    reclaimed = 0
    roots = {path.parent, path.with_name(f".{path.name}.revisions")}
    for root in roots:
        if not root.is_dir():
            continue
        for pattern in patterns:
            for candidate in root.glob(pattern):
                if not candidate.is_file():
                    continue
                try:
                    size = candidate.stat().st_size
                    candidate.unlink()
                    removed += 1
                    reclaimed += size
                except OSError:
                    continue
    return removed, reclaimed


def compact_vfs(path: Path, directory: str, folder: str, *, keep_revisions: int = 32) -> dict[str, Any]:
    if type(keep_revisions) is not int or keep_revisions < 1:
        raise ValueError("keep_revisions must be a positive integer")
    started = time.perf_counter_ns()
    optimize = optimize_vfs(path, directory, folder)
    # Serialize revision/timeline reclamation against writers. Optimization has
    # its own transaction lock; this second short lock protects maintenance of
    # the revision graph and disposable artifacts.
    with vfs_write_lock(path):
        before = storage_report(path)
        removed_objects = prune_revisions(path, keep_revisions)
        temp_removed, temp_bytes = _cleanup_disposable(path)
        after = storage_report(path)
    revision_bytes = max(0, before["total_bytes"] - after["total_bytes"])
    result = {
        "ok": True,
        "optimize": optimize,
        "keep_revisions": keep_revisions,
        "revision_objects_removed": removed_objects,
        "temporary_files_removed": temp_removed,
        "revision_bytes_reclaimed": revision_bytes,
        "temporary_bytes_reclaimed": temp_bytes,
        "total_bytes_reclaimed": revision_bytes + temp_bytes + optimize["bytes_reclaimed"],
        "revision_storage_before": before,
        "revision_storage_after": after,
        "elapsed_ns": time.perf_counter_ns() - started,
    }
    emit("vfs_compact_completed", path=str(path), keep_revisions=keep_revisions,
         objects_removed=removed_objects, bytes_reclaimed=result["total_bytes_reclaimed"])
    return result
