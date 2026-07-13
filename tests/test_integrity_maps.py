import json
from pathlib import Path
import staqtapp
from staqtapp import integrity


def test_map_created_and_deep_verifies(selected):
    result = staqtapp.verify_integrity()
    assert result["ok"] is True
    assert result["regions_checked"] >= 3


def test_mutation_republishes_map(selected):
    before = staqtapp.integrity_report()["mapped_vfs_sha256"]
    staqtapp.addvar("alpha", "one")
    report = staqtapp.verify_integrity()
    assert report["ok"] and report["mapped_vfs_sha256"] != before


def test_missing_map_is_contained_and_rebuildable(selected):
    path = Path(staqtapp.listfiles()["vfs_file"])
    integrity.integrity_path(path).unlink()
    failure = staqtapp.verify_integrity()
    assert not failure and failure.error_type == "FormatError"
    assert staqtapp.rebuild_integrity_map()["ok"]
    assert staqtapp.verify_integrity()["ok"]


def test_forged_map_checksum_is_rejected(selected):
    path = Path(staqtapp.listfiles()["vfs_file"]); mp = integrity.integrity_path(path)
    doc = json.loads(mp.read_text()); doc["regions"][0]["sha256"] = "0"*64
    mp.write_text(json.dumps(doc))
    failure = staqtapp.verify_integrity()
    assert not failure and failure.error_type == "FormatError"


def test_stale_map_detected_without_trusting_it(selected):
    path = Path(staqtapp.listfiles()["vfs_file"]); mp = integrity.integrity_path(path)
    saved = mp.read_bytes(); staqtapp.addvar("alpha", "one"); mp.write_bytes(saved)
    report = staqtapp.verify_integrity()
    assert report["ok"] is False and report["stale"] is True


def test_payload_corruption_localizes_variable(selected):
    staqtapp.addvar("alpha", "one")
    path = Path(staqtapp.listfiles()["vfs_file"])
    with path.open("r+b") as f:
        data=f.read(); pos=data.index(b"one"); f.seek(pos); f.write(b"x")
    report = staqtapp.verify_integrity()
    assert report["ok"] is False
    assert any(x.get("kind") == "payload" and x.get("name") == "alpha" for x in report["failures"])


def test_truncation_is_contained_and_execution_continues(selected):
    path = Path(staqtapp.listfiles()["vfs_file"])
    data = path.read_bytes(); path.write_bytes(data[:-8])
    failure = staqtapp.verify_integrity()
    assert failure["ok"] is False and failure["stale"] is True
    # public controller remains alive
    assert isinstance(staqtapp.diagnostic_counts(), dict)


def test_shallow_verification_checks_identity_only(selected):
    result = staqtapp.verify_integrity(deep=False)
    assert result["ok"] and result["regions_checked"] == 0


def test_rebuild_is_atomic_under_simulated_replace_failure(selected, monkeypatch):
    path = Path(staqtapp.listfiles()["vfs_file"]); mp = integrity.integrity_path(path); before=mp.read_bytes()
    import os
    real=os.replace
    def fail(src,dst):
        if Path(dst)==mp: raise OSError("simulated")
        return real(src,dst)
    monkeypatch.setattr(os,"replace",fail)
    result=staqtapp.rebuild_integrity_map()
    assert not result and mp.read_bytes()==before
