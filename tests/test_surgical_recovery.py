from __future__ import annotations

import json
import os
from pathlib import Path

import staqtapp
from staqtapp import integrity
from staqtapp.revisions import revision_root


def _path() -> Path:
    return Path(staqtapp.listfiles()["vfs_file"])


def _corrupt_payload(path: Path, old: bytes, replacement: bytes = b"x") -> bytes:
    before = path.read_bytes()
    pos = before.index(old)
    with path.open("r+b") as stream:
        stream.seek(pos)
        stream.write(replacement)
        stream.flush()
        os.fsync(stream.fileno())
    return before


def test_surgical_repair_restores_one_payload_exactly(selected):
    staqtapp.addvar("alpha", "one")
    path = _path(); expected = path.read_bytes()
    _corrupt_payload(path, b"one")
    result = staqtapp.repair_vfs()
    assert result["ok"] and result["repaired"]
    assert "record:alpha" in result["regions_restored"]
    assert path.read_bytes() == expected
    assert staqtapp.loadvar(False, "alpha", "s") == ["one"]
    assert staqtapp.verify_integrity()["ok"]


def test_repair_uses_newest_revision_with_exact_region(selected):
    staqtapp.addvar("alpha", "one")
    staqtapp.changevar("alpha", "two")
    path = _path(); expected = path.read_bytes()
    _corrupt_payload(path, b"two")
    result = staqtapp.repair_vfs()
    assert result["repaired"] and path.read_bytes() == expected
    assert staqtapp.loadvar(False, "alpha", "s") == ["two"]


def test_healthy_vfs_is_noop(selected):
    result = staqtapp.repair_vfs()
    assert result["ok"] and result["repaired"] is False
    assert result["reason"] == "no-corruption-detected"


def test_structural_corruption_is_refused_and_execution_continues(selected):
    path = _path(); before = path.read_bytes()
    with path.open("r+b") as stream:
        stream.seek(0); stream.write(b"X")
    corrupted = path.read_bytes()
    result = staqtapp.repair_vfs()
    assert not result and result.error_type == "RecoveryError"
    assert "structural corruption" in result.message
    assert path.read_bytes() == corrupted and path.read_bytes() != before
    assert isinstance(staqtapp.diagnostic_counts(), dict)


def test_missing_integrity_map_is_refused(selected):
    path = _path(); integrity.integrity_path(path).unlink()
    result = staqtapp.repair_vfs()
    assert not result and result.error_type == "FormatError"
    assert isinstance(staqtapp.listvars(), list)


def test_forged_integrity_map_is_refused(selected):
    path = _path(); mp = integrity.integrity_path(path)
    doc = json.loads(mp.read_text()); doc["regions"][0]["sha256"] = "0" * 64
    mp.write_text(json.dumps(doc))
    result = staqtapp.repair_vfs()
    assert not result and result.error_type == "FormatError"


def test_no_trustworthy_revision_refuses_without_modification(selected):
    staqtapp.addvar("alpha", "one")
    path = _path()
    revisions = staqtapp.list_revisions()
    head = revisions[0]["revision"]
    _corrupt_payload(path, b"one"); corrupted = path.read_bytes()
    # Corrupt the only immutable object containing alpha. The initial object
    # remains valid but cannot satisfy alpha's expected region checksum.
    obj = revision_root(path) / "objects" / f"{head}.sqtpp"
    with obj.open("r+b") as stream:
        stream.seek(0); stream.write(b"X")
    result = staqtapp.repair_vfs()
    assert not result and result.error_type == "RecoveryError"
    assert path.read_bytes() == corrupted


def test_interruption_before_replace_preserves_corrupt_source(selected, monkeypatch):
    staqtapp.addvar("alpha", "one")
    path = _path(); _corrupt_payload(path, b"one"); corrupted = path.read_bytes()
    real_replace = os.replace
    def fail(source, destination):
        if Path(destination) == path:
            raise OSError("simulated repair interruption")
        return real_replace(source, destination)
    monkeypatch.setattr(os, "replace", fail)
    result = staqtapp.repair_vfs()
    assert not result and result.error_type == "TransactionError"
    assert path.read_bytes() == corrupted


def test_repair_creates_revision_event_and_fresh_map(selected):
    staqtapp.addvar("alpha", "one")
    path = _path(); _corrupt_payload(path, b"one")
    result = staqtapp.repair_vfs()
    history = staqtapp.list_revisions()
    assert history[0]["event"] == "surgical_repair"
    assert history[0]["revision"] == result["new_revision"]
    report = staqtapp.integrity_report()
    assert report["ok"] and report["mapped_vfs_sha256"] == result["new_revision"]


def _flip_region_byte(path: Path, name: str) -> None:
    doc = integrity.load_map(path)
    region = next(r for r in doc["regions"] if r["kind"] == "payload" and r["name"] == name)
    position = int(region["start"])
    with path.open("r+b") as stream:
        stream.seek(position)
        original = stream.read(1)
        stream.seek(position)
        stream.write(bytes([original[0] ^ 1]))
        stream.flush(); os.fsync(stream.fileno())


def test_multiple_record_corruptions_repair_in_one_atomic_commit(selected):
    staqtapp.addvar("alpha", "one"); staqtapp.addvar("beta", "two")
    path = _path(); expected = path.read_bytes()
    _flip_region_byte(path, "alpha"); _flip_region_byte(path, "beta")
    result = staqtapp.repair_vfs()
    assert result["repaired"]
    assert result["regions_restored"] == ["record:alpha", "record:beta"]
    assert path.read_bytes() == expected and staqtapp.verify_integrity()["ok"]


def test_typed_value_is_restored_and_decodes_exactly(selected):
    value = {("key", 1): 3.5-2j, "payload": b"\x00\xff"}
    staqtapp.set_value("typed", value)
    path = _path(); expected = path.read_bytes(); _flip_region_byte(path, "typed")
    result = staqtapp.repair_vfs()
    assert result["repaired"] and path.read_bytes() == expected
    assert staqtapp.get_value("typed") == value


def test_revision_object_is_inode_independent_from_active_vfs(selected):
    staqtapp.addvar("alpha", "one")
    path = _path(); revision = staqtapp.list_revisions()[0]["revision"]
    obj = revision_root(path) / "objects" / f"{revision}.sqtpp"
    assert path.stat().st_ino != obj.stat().st_ino or path.stat().st_dev != obj.stat().st_dev
    original = obj.read_bytes(); _corrupt_payload(path, b"one")
    assert obj.read_bytes() == original
