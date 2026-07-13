from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from . import integrity
from .errors import RecoveryError
from .revisions import revision_object, trusted_revision_candidates
from .snapshot import MappedVFS
from .transaction import plan_from_replacements, repair_mutate


def _sha(data) -> str:
    return hashlib.sha256(data).hexdigest()


def _raw_failures(path: Path, document: dict[str, Any]) -> tuple[bytes, list[dict[str, Any]]]:
    raw = path.read_bytes()
    failures: list[dict[str, Any]] = []
    for region in document.get("regions", []):
        try:
            start = int(region["start"]); end = int(region["end"])
            actual = _sha(raw[start:end]) if 0 <= start <= end <= len(raw) else None
            if actual != region.get("sha256"):
                failures.append({**region, "actual": actual})
        except Exception as exc:
            raise RecoveryError("integrity map contains an invalid region entry") from exc
    return raw, failures


def _repair_regions(failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not failures:
        return []
    allowed = {"record", "payload"}
    leaf_failures = [item for item in failures if item.get("kind") in allowed]
    structural = [item for item in failures if item.get("kind") not in allowed]
    # tqpt-body is an aggregate checksum covering all variable records. It is
    # expected to fail whenever a contained record/payload fails and does not
    # itself imply independent structural damage.
    structural = [item for item in structural if not (
        item.get("kind") == "container" and item.get("name") == "tqpt-body" and leaf_failures
    )]
    if structural:
        kinds = sorted({str(item.get("kind")) for item in structural})
        raise RecoveryError(f"surgical repair refuses structural corruption: {', '.join(kinds)}")
    # Record regions contain their payload regions. Repairing the exact record
    # is sufficient and avoids overlapping replacements.
    records = [item for item in failures if item.get("kind") == "record"]
    covered = {(item.get("name"), int(item["start"]), int(item["end"])) for item in records}
    selected = list(records)
    for payload in failures:
        if payload.get("kind") != "payload":
            continue
        ps, pe = int(payload["start"]), int(payload["end"])
        if not any(name == payload.get("name") and rs <= ps <= pe <= re for name, rs, re in covered):
            selected.append(payload)
    selected.sort(key=lambda item: int(item["start"]))
    cursor = -1
    for item in selected:
        start, end = int(item["start"]), int(item["end"])
        if start < cursor:
            raise RecoveryError("surgical repair regions overlap")
        cursor = end
    return selected


def _candidate_bytes(candidate: Path, directory: str, folder: str,
                     region: dict[str, Any]) -> bytes | None:
    try:
        with MappedVFS(candidate, directory, folder) as snapshot:
            name = str(region.get("name")); kind = region.get("kind")
            span = snapshot.span(name)
            start, end = ((span.record_start, span.record_end) if kind == "record"
                          else (span.payload_start, span.payload_end))
            data = bytes(snapshot._mapped[start:end])
            if len(data) != int(region["length"]) or _sha(data) != region.get("sha256"):
                return None
            return data
    except Exception:
        return None


def repair_vfs(path: Path, directory: str, folder: str, *, strategy: str = "surgical",
               source: str = "latest-valid-revision") -> dict[str, Any]:
    if strategy != "surgical":
        raise ValueError("strategy must be 'surgical'")
    if source != "latest-valid-revision":
        raise ValueError("source must be 'latest-valid-revision'")
    document = integrity.load_map(path)
    raw, failures = _raw_failures(path, document)
    selected = _repair_regions(failures)
    if not selected:
        return {"ok": True, "repaired": False, "reason": "no-corruption-detected", "regions_restored": []}

    replacements: list[tuple[int, int, bytes]] = []
    sources: dict[str, str] = {}
    entries = trusted_revision_candidates(path)
    if not entries:
        raise RecoveryError("no immutable revisions are available for surgical repair")
    for region in selected:
        trusted = None; trusted_revision = None
        for entry in entries:
            try:
                candidate = revision_object(path, entry.revision)
            except Exception:
                continue
            trusted = _candidate_bytes(candidate, directory, folder, region)
            if trusted is not None:
                trusted_revision = entry.revision
                break
        if trusted is None or trusted_revision is None:
            raise RecoveryError(f"no trustworthy revision contains region {region.get('kind')}:{region.get('name')}")
        start, end = int(region["start"]), int(region["end"])
        replacements.append((start, end, trusted))
        sources[f"{region.get('kind')}:{region.get('name')}"] = trusted_revision

    observed = _sha(raw)
    def operation(mapped):
        if _sha(mapped) != observed:
            raise RecoveryError("VFS changed after recovery analysis")
        return plan_from_replacements(len(mapped), replacements)

    stats = repair_mutate(path, operation, event="surgical_repair")
    # A repaired image must be structurally valid before a new map is trusted.
    with MappedVFS(path, directory, folder) as snapshot:
        variables = snapshot.variable_count
    integrity.publish_map(path, directory, folder)
    verification = integrity.verify_map(path, directory, folder, deep=True)
    if not verification.get("ok"):
        raise RecoveryError("post-repair deep verification failed")
    return {
        "ok": True,
        "repaired": True,
        "strategy": strategy,
        "regions_restored": [f"{r.get('kind')}:{r.get('name')}" for r in selected],
        "source_revisions": sources,
        "new_revision": stats.destination_sha256,
        "variables": variables,
        "bytes_written": stats.bytes_written,
        "bytes_copied": stats.bytes_copied,
    }
