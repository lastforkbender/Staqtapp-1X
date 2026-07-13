from pathlib import Path
import hashlib
import staqtapp


def _setup(tmp_path: Path):
    staqtapp.configure(storage_dir=tmp_path)
    assert staqtapp.makevfs("maint", "dir", "folder") is None


def test_optimize_preserves_legacy_and_typed_values(tmp_path):
    _setup(tmp_path)
    staqtapp.addvar("legacy", "alpha,beta")
    typed = {("key", 1): 3.5-2j, "blob": b"\x00\xff", "set": {3, 1, 2}}
    staqtapp.set_value("typed", typed)
    before = Path(tmp_path, "maint.sqtpp").read_bytes()
    result = staqtapp.optimize_vfs()
    assert result and result["ok"]
    assert staqtapp.loadvar(False, "legacy", "s") == ["alpha", "beta"]
    assert staqtapp.get_value("typed") == typed
    assert staqtapp.verify_integrity()["ok"] is True
    assert staqtapp.read_index_info()["variables"] == 2
    assert Path(tmp_path, "maint.sqtpp").read_bytes() == before


def test_compact_prunes_unreachable_revision_objects(tmp_path):
    _setup(tmp_path)
    for i in range(8):
        staqtapp.set_value("counter", i)
    before = staqtapp.revision_storage_report()
    result = staqtapp.compact_vfs(keep_revisions=3)
    assert result and result["ok"]
    after = staqtapp.revision_storage_report()
    assert after["timeline_entries"] == 3
    assert after["object_count"] <= before["object_count"]
    assert staqtapp.get_value("counter") == 7
    assert staqtapp.verify_integrity()["ok"] is True


def test_compact_never_removes_backup(tmp_path):
    _setup(tmp_path)
    staqtapp.addvar("alpha", "one")
    staqtapp.changevar("alpha", "two")
    backup = Path(tmp_path, "maint.sqtpp.bak")
    assert backup.is_file()
    digest = hashlib.sha256(backup.read_bytes()).hexdigest()
    assert staqtapp.compact_vfs(keep_revisions=2)
    assert backup.is_file()
    assert hashlib.sha256(backup.read_bytes()).hexdigest() == digest


def test_invalid_compact_is_contained_and_execution_continues(tmp_path):
    _setup(tmp_path)
    result = staqtapp.compact_vfs(keep_revisions=0)
    assert not result
    assert result.error_type == "ValueError"
    assert staqtapp.addvar("after_failure", "yes") is None
    assert staqtapp.findvar("after_failure") is True


def test_optimize_publication_failure_does_not_corrupt_vfs(tmp_path, monkeypatch):
    _setup(tmp_path)
    staqtapp.set_value("safe", {"x": 1})
    path = Path(tmp_path, "maint.sqtpp")
    before = path.read_bytes()
    from staqtapp import maintenance
    def fail(*args, **kwargs):
        raise OSError("simulated integrity publication failure")
    monkeypatch.setattr(maintenance.integrity, "publish_map", fail)
    result = staqtapp.optimize_vfs()
    assert not result
    assert path.read_bytes() == before
    assert staqtapp.get_value("safe") == {"x": 1}


def test_compact_removes_only_recognized_temp_files(tmp_path):
    _setup(tmp_path)
    staqtapp.addvar("alpha", "one")
    disposable = Path(tmp_path, ".maint.sqtpp.orphan.tmp")
    protected = Path(tmp_path, "keep-me.tmp")
    disposable.write_bytes(b"x" * 17)
    protected.write_bytes(b"important")
    result = staqtapp.compact_vfs(keep_revisions=2)
    assert result["temporary_files_removed"] >= 1
    assert not disposable.exists()
    assert protected.exists()


def test_prune_timeline_failure_never_deletes_revision_objects(tmp_path, monkeypatch):
    _setup(tmp_path)
    for i in range(5):
        staqtapp.set_value("counter", i)
    from staqtapp import revisions
    path = Path(tmp_path, "maint.sqtpp")
    objects_before = sorted(p.name for p in revisions._objects(path).glob("*.sqtpp"))
    def fail(*args, **kwargs):
        raise OSError("simulated timeline publication failure")
    monkeypatch.setattr(revisions, "_write_timeline", fail)
    result = staqtapp.compact_vfs(keep_revisions=2)
    assert not result
    objects_after = sorted(p.name for p in revisions._objects(path).glob("*.sqtpp"))
    assert objects_after == objects_before
    assert staqtapp.get_value("counter") == 4
