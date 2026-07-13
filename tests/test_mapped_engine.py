from __future__ import annotations

from pathlib import Path

import staqtapp
from staqtapp.snapshot import MappedVFS, VariableSpan


def test_mapped_snapshot_uses_spans_and_lazy_feature_indexes(selected):
    staqtapp.appvar(["alpha", "beta"], ["one", "two"], None)
    info = staqtapp.listfiles()
    path = Path(info["vfs_file"])
    with MappedVFS(path, info["directory"], info["folder"]) as snapshot:
        assert not hasattr(snapshot, "source")
        assert snapshot.variable_order == ["alpha", "beta"]
        assert snapshot.variable_count == 2
        assert isinstance(snapshot.span("alpha"), VariableSpan)
        assert snapshot._locks is None
        assert snapshot._histories is None
        assert snapshot.payload_bytes("beta").startswith(b"@qp(")
        assert snapshot._locks is None
        assert snapshot._histories is None


def test_verify_reports_mapped_read_engine(selected):
    staqtapp.addvar("alpha", "one")
    report = staqtapp.verify_vfs()
    assert report["ok"] is True
    assert report["read_engine"] == "mmap-span-index"
    assert report["index_bytes_estimate"] > 0


def test_literal_search_preserves_encoded_text_semantics(selected):
    staqtapp.addvar("encoded", "line one\nline two):still data")
    assert staqtapp.vardata_stx(False, ["encoded"], "line two") == ["encoded"]
    assert staqtapp.vardata_stx(False, ["encoded"], "absent") == []


def test_backup_is_previous_committed_revision(selected):
    staqtapp.addvar("alpha", "one")
    path = Path(staqtapp.listfiles()["vfs_file"])
    before = path.read_bytes()
    staqtapp.changevar("alpha", "two")
    backup = path.with_suffix(path.suffix + ".bak")
    assert backup.read_bytes() == before
    assert path.read_bytes() != before


def test_disposable_sidecar_is_used_and_invalidated(selected):
    staqtapp.appvar(["alpha", "beta"], ["one", "two"], None)
    info = staqtapp.listfiles()
    path = Path(info["vfs_file"])
    index = path.with_suffix(".sqti")
    assert index.is_file()
    with MappedVFS(path, info["directory"], info["folder"]) as snapshot:
        assert snapshot.index_source == "sidecar"
        assert snapshot.payload_bytes("alpha").startswith(b"@qp(")
    staqtapp.changevar("alpha", "changed")
    assert not index.exists()
    with MappedVFS(path, info["directory"], info["folder"]) as rebuilt:
        assert rebuilt.index_source == "scan"
        assert rebuilt.payload_bytes("alpha") == b"@qp(changed):"
    assert index.is_file()


def test_corrupt_sidecar_falls_back_to_authoritative_vfs(selected):
    staqtapp.appvar(["alpha", "beta"], ["one", "two"], None)
    info = staqtapp.listfiles()
    path = Path(info["vfs_file"])
    index = path.with_suffix(".sqti")
    damaged = bytearray(index.read_bytes())
    damaged[-1] ^= 0xFF
    index.write_bytes(damaged)
    with MappedVFS(path, info["directory"], info["folder"]) as snapshot:
        assert snapshot.index_source == "scan"
        assert snapshot.payload_bytes("beta") == b"@qp(two):"
    with MappedVFS(path, info["directory"], info["folder"]) as repaired:
        assert repaired.index_source == "sidecar"
        assert repaired.list_names() == ["alpha", "beta"]
