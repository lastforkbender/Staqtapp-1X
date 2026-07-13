from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import FormatError
from .snapshot import MappedVFS

_FORMAT = "staqt-integrity-v1"


def integrity_path(path: str | Path) -> Path:
    return Path(path).with_suffix(Path(path).suffix + ".integrity.json")


def _digest(data) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(document: dict[str, Any]) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _region(kind: str, name: str, start: int, end: int, mapped) -> dict[str, Any]:
    if not (0 <= start <= end <= len(mapped)):
        raise FormatError(f"invalid integrity region span: {kind}:{name}")
    return {"kind": kind, "name": name, "start": start, "end": end, "length": end-start,
            "sha256": _digest(mapped[start:end])}


def build_map(path: str | Path, directory: str, folder: str) -> dict[str, Any]:
    path = Path(path)
    with MappedVFS(path, directory, folder) as snapshot:
        mapped = snapshot._mapped
        regions = [
            _region("structure", "prefix", 0, snapshot.tqpt_body_start, mapped),
            _region("container", "tqpt-body", snapshot.tqpt_body_start, snapshot.tqpt_body_end, mapped),
            _region("container", "tpqt-body", snapshot.tpqt_body_start, snapshot.tpqt_body_end, mapped),
        ]
        if snapshot.history_span:
            regions.append(_region("history", "stalk-history", snapshot.history_span[0], snapshot.history_span[1], mapped))
        for name in snapshot.iter_names():
            span = snapshot.span(name)
            regions.append(_region("record", name, span.record_start, span.record_end, mapped))
            regions.append(_region("payload", name, span.payload_start, span.payload_end, mapped))
        document = {
            "format": _FORMAT,
            "vfs": {"size": snapshot.size, "sha256": snapshot.sha256(), "directory": directory, "folder": folder},
            "regions": regions,
        }
    document["map_sha256"] = _digest(_canonical(document))
    return document


def publish_map(path: str | Path, directory: str, folder: str) -> dict[str, Any]:
    path = Path(path); target = integrity_path(path); document = build_map(path, directory, folder)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(_canonical(document)); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, target); temp = ""
        try:
            dfd = os.open(target.parent, os.O_RDONLY)
            try: os.fsync(dfd)
            finally: os.close(dfd)
        except OSError: pass
    finally:
        if temp:
            try: os.unlink(temp)
            except FileNotFoundError: pass
    return {"ok": True, "path": str(target), "vfs_sha256": document["vfs"]["sha256"], "regions": len(document["regions"]), "format": _FORMAT}


def load_map(path: str | Path) -> dict[str, Any]:
    target = integrity_path(path)
    try:
        raw = target.read_bytes(); document = json.loads(raw.decode("utf-8"))
    except FileNotFoundError: raise FormatError(f"integrity map does not exist: {target}")
    except Exception as exc: raise FormatError("integrity map is malformed") from exc
    if not isinstance(document, dict) or document.get("format") != _FORMAT:
        raise FormatError("unsupported integrity-map format")
    claimed = document.pop("map_sha256", None)
    actual = _digest(_canonical(document))
    document["map_sha256"] = claimed
    if claimed != actual: raise FormatError("integrity-map checksum mismatch")
    return document


def verify_map(path: str | Path, directory: str, folder: str, *, deep: bool = True) -> dict[str, Any]:
    path = Path(path); document = load_map(path)
    with MappedVFS(path, directory, folder) as snapshot:
        current_sha = snapshot.sha256()
        stale = document.get("vfs", {}).get("size") != snapshot.size or document.get("vfs", {}).get("sha256") != current_sha
        failures: list[dict[str, Any]] = []
        checked = 0
        if deep:
            mapped = snapshot._mapped
            for region in document.get("regions", []):
                try:
                    start = int(region["start"]); end = int(region["end"])
                    actual = _digest(mapped[start:end]) if 0 <= start <= end <= snapshot.size else None
                    checked += 1
                    if actual != region.get("sha256"):
                        failures.append({"kind": region.get("kind"), "name": region.get("name"), "start": start, "end": end,
                                         "expected": region.get("sha256"), "actual": actual})
                except Exception:
                    failures.append({"kind": region.get("kind"), "name": region.get("name"), "error": "invalid-region-entry"})
        return {"ok": not stale and not failures, "path": str(path), "map_path": str(integrity_path(path)),
                "format": _FORMAT, "stale": stale, "deep": deep, "regions_checked": checked,
                "failures": failures, "vfs_sha256": current_sha, "mapped_vfs_sha256": document.get("vfs", {}).get("sha256")}
