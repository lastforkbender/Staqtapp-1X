from __future__ import annotations

import base64
from pathlib import Path

import staqtapp


def _setup(tmp_path: Path):
    staqtapp.configure(storage_dir=tmp_path)
    assert staqtapp.makevfs("scale", "dir", "folder") is None


def test_validated_index_info_and_rebuild(tmp_path):
    _setup(tmp_path)
    assert staqtapp.addvar("alpha", "one") is None
    info = staqtapp.rebuild_read_index()
    assert info["source"] in {"scan", "sidecar"}
    assert info["variables"] == 1
    assert info["exists"] is True
    current = staqtapp.read_index_info()
    assert current["variables"] == 1
    assert current["format_version"] >= 3


def test_raw_payload_range_is_exact(tmp_path):
    _setup(tmp_path)
    staqtapp.addvar("alpha", "abcdefghij")
    whole = staqtapp.read_payload_range("alpha")
    assert staqtapp.read_payload_range("alpha", 2, 5) == whole[2:7]
    assert staqtapp.read_payload_range("alpha", len(whole), 1) == b""


def test_typed_range_matches_full_canonical_bytes(tmp_path):
    _setup(tmp_path)
    value = {"blob": b"x" * 50000, "complex": 3.5-2j, "text": "Żółw" * 100}
    assert staqtapp.set_value("typed", value) is None
    full = staqtapp.read_range("typed")
    for start, length in [(0, 1), (1, 2), (2, 7), (11, 4096), (len(full)-3, 3), (len(full), 10)]:
        assert staqtapp.read_range("typed", start, length) == full[start:start+length]


def test_typed_finite_range_does_not_use_full_payload_bytes(tmp_path, monkeypatch):
    _setup(tmp_path)
    staqtapp.set_value("typed", b"z" * 100000)
    from staqtapp import snapshot
    original = snapshot.MappedVFS.payload_bytes
    def forbidden(self, name):
        raise AssertionError("full payload materialization used")
    monkeypatch.setattr(snapshot.MappedVFS, "payload_bytes", forbidden)
    try:
        assert len(staqtapp.read_range("typed", 123, 77)) == 77
    finally:
        monkeypatch.setattr(snapshot.MappedVFS, "payload_bytes", original)


def test_diagnostics_split_lock_wait_and_hold(tmp_path):
    _setup(tmp_path)
    staqtapp.addvar("alpha", "one")
    events = staqtapp.recent_events(20)
    mutation = next(event for event in reversed(events) if event.name == "variable_added")
    fields = dict(mutation.fields)
    assert fields["lock_wait_ns"] >= 0
    assert fields["lock_hold_ns"] > 0
    assert fields["preparation_ns"] >= 0
    assert fields["commit_ns"] > 0

def test_transaction_overlay_reports_superseded_targets(tmp_path):
    _setup(tmp_path)
    result = staqtapp.run_transaction([
        ("set_value", ("count", 1)),
        ("set_value", ("count", 2)),
        ("set_value", ("count", 3)),
    ])
    assert result
    assert staqtapp.get_value("count") == 3
    event = next(e for e in reversed(staqtapp.recent_events(20)) if e.name == "transaction_operations_applied")
    fields = dict(event.fields)
    assert fields["physical_commits"] == 1
    assert fields["unique_targets"] == 1
    assert fields["superseded_operations"] == 2


def test_revision_storage_report(tmp_path):
    _setup(tmp_path)
    staqtapp.addvar("alpha", "one")
    report = staqtapp.revision_storage_report()
    assert report["timeline_entries"] >= 2
    assert report["object_count"] >= 2
    assert report["reclaimable_bytes"] >= 0
