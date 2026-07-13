from __future__ import annotations

import hashlib
import json
import multiprocessing
from pathlib import Path

import staqtapp


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_initial_revision_is_content_addressed_and_immutable(home):
    staqtapp.makevfs("rev", "Main", "Data")
    info = staqtapp.listfiles()
    path = Path(info["vfs_file"])
    assert info["revision_kind"] == "sha256-content"
    assert info["revision"] == _sha(path)
    history = staqtapp.list_revisions()
    assert len(history) == 1
    assert history[0]["revision"] == info["revision"]
    obj = path.with_name(f".{path.name}.revisions") / "objects" / f"{info['revision']}.sqtpp"
    assert obj.read_bytes() == path.read_bytes()


def test_each_commit_creates_a_revision_and_objects_are_deduplicated(home):
    staqtapp.makevfs("rev", "Main", "Data")
    initial = staqtapp.listfiles()["revision"]
    staqtapp.addvar("a", "1")
    first = staqtapp.listfiles()["revision"]
    staqtapp.changevar("a", "2")
    second = staqtapp.listfiles()["revision"]
    assert len({initial, first, second}) == 3
    history = staqtapp.list_revisions()
    assert [item["revision"] for item in history[:3]] == [second, first, initial]
    path = Path(staqtapp.listfiles()["vfs_file"])
    objects = list((path.with_name(f".{path.name}.revisions") / "objects").glob("*.sqtpp"))
    assert len(objects) == 3


def test_rollback_restores_exact_bytes_and_creates_timeline_event(home):
    staqtapp.makevfs("rev", "Main", "Data")
    staqtapp.addvar("a", "1")
    target = staqtapp.listfiles()["revision"]
    target_bytes = Path(staqtapp.listfiles()["vfs_file"]).read_bytes()
    staqtapp.changevar("a", "2")
    previous_head = staqtapp.listfiles()["revision"]
    result = staqtapp.rollback_revision(target)
    assert result and result["from_revision"] == previous_head
    path = Path(staqtapp.listfiles()["vfs_file"])
    assert path.read_bytes() == target_bytes
    assert staqtapp.loadvar(False, "a", "s") == [1]
    history = staqtapp.list_revisions()
    assert history[0]["event"] == "rollback"
    assert history[0]["revision"] == target
    assert history[0]["parent"] == previous_head


def test_invalid_and_missing_revision_never_halts_or_changes_head(home):
    staqtapp.makevfs("rev", "Main", "Data")
    path = Path(staqtapp.listfiles()["vfs_file"])
    before = path.read_bytes()
    malformed = staqtapp.rollback_revision("bad")
    missing = staqtapp.rollback_revision("0" * 64)
    assert not malformed and malformed.error_type == "ValueError"
    assert not missing and missing.error_type == "RecoveryError"
    assert path.read_bytes() == before
    assert staqtapp.addvar("continues", "yes") is None


def test_corrupt_revision_object_is_rejected_without_touching_current(home):
    staqtapp.makevfs("rev", "Main", "Data")
    staqtapp.addvar("a", "1")
    target = staqtapp.listfiles()["revision"]
    staqtapp.changevar("a", "2")
    path = Path(staqtapp.listfiles()["vfs_file"])
    before = path.read_bytes()
    obj = path.with_name(f".{path.name}.revisions") / "objects" / f"{target}.sqtpp"
    obj.write_bytes(b"corrupt")
    result = staqtapp.rollback_revision(target)
    assert not result and result.error_type == "RecoveryError"
    assert path.read_bytes() == before


def test_transaction_creates_only_one_new_revision(home):
    staqtapp.makevfs("rev", "Main", "Data")
    before = len(staqtapp.list_revisions())
    result = staqtapp.run_transaction([
        ("addvar", ("a", "1")),
        ("addvar", ("b", "2")),
        ("joinvars", ("ab", ["a", "b"])),
    ])
    assert result
    after = staqtapp.list_revisions()
    assert len(after) == before + 1
    assert after[0]["event"] == "transaction_committed"


def test_failed_transaction_creates_no_revision(home):
    staqtapp.makevfs("rev", "Main", "Data")
    before = staqtapp.list_revisions()
    result = staqtapp.run_transaction([
        ("addvar", ("a", "1")),
        ("addvar", ("a", "duplicate")),
    ])
    assert not result
    assert staqtapp.list_revisions() == before


def test_timeline_reconciles_current_if_last_entry_is_missing(home):
    staqtapp.makevfs("rev", "Main", "Data")
    staqtapp.addvar("a", "1")
    path = Path(staqtapp.listfiles()["vfs_file"])
    timeline = path.with_name(f".{path.name}.revisions") / "timeline.json"
    entries = json.loads(timeline.read_text())
    timeline.write_text(json.dumps(entries[:-1]))
    repaired = staqtapp.list_revisions()
    assert repaired[0]["revision"] == _sha(path)
    assert repaired[0]["event"] == "observed"


def test_prune_retains_recent_timeline_and_current_object(home):
    staqtapp.makevfs("rev", "Main", "Data")
    for index in range(6):
        if index == 0:
            staqtapp.addvar("a", str(index))
        else:
            staqtapp.changevar("a", str(index))
    current = staqtapp.listfiles()["revision"]
    result = staqtapp.prune_revisions(3)
    assert result and result["kept"] == 3
    history = staqtapp.list_revisions()
    assert len(history) == 3 and history[0]["revision"] == current


def test_revision_limit_validation_is_contained(home):
    staqtapp.makevfs("rev", "Main", "Data")
    result = staqtapp.list_revisions(0)
    assert not result and result.error_type == "ValueError"
    assert staqtapp.listvars() == []


def test_interrupted_rollback_preserves_current_and_continues(home, monkeypatch):
    import staqtapp.transaction as transaction

    staqtapp.makevfs("rev", "Main", "Data")
    staqtapp.addvar("a", "1")
    target = staqtapp.listfiles()["revision"]
    staqtapp.changevar("a", "2")
    path = Path(staqtapp.listfiles()["vfs_file"])
    before = path.read_bytes()
    real_replace = transaction.os.replace

    def interrupted(source, destination):
        if Path(destination) == path and str(source).endswith(".rollback.tmp"):
            raise OSError("simulated rollback interruption")
        return real_replace(source, destination)

    monkeypatch.setattr(transaction.os, "replace", interrupted)
    result = staqtapp.rollback_revision(target)
    assert not result and result.error_type == "OSError"
    assert path.read_bytes() == before
    assert staqtapp.loadvar(False, "a", "s") == [2]


def test_corrupt_timeline_is_contained_without_blocking_reads(home):
    staqtapp.makevfs("rev", "Main", "Data")
    staqtapp.addvar("a", "1")
    path = Path(staqtapp.listfiles()["vfs_file"])
    timeline = path.with_name(f".{path.name}.revisions") / "timeline.json"
    timeline.write_text("{not-json", encoding="utf-8")
    result = staqtapp.list_revisions()
    assert not result and result.error_type == "RecoveryError"
    assert staqtapp.loadvar(False, "a", "s") == [1]


def test_concurrent_commits_keep_contiguous_revision_timeline(home):
    from concurrent.futures import ThreadPoolExecutor

    staqtapp.makevfs("rev", "Main", "Data")
    staqtapp.addvar("counter", "0")

    def write(index):
        return staqtapp.changevar("counter", str(index))

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(write, range(1, 25)))
    assert all(bool(result) for result in results)
    history = list(reversed(staqtapp.list_revisions()))
    assert [entry["sequence"] for entry in history] == list(range(1, len(history) + 1))
    assert len(history) == 26  # initial + add + 24 changes
    assert staqtapp.listfiles()["revision"] == history[-1]["revision"]


def test_pruned_revision_cannot_be_rolled_back_but_execution_continues(home):
    staqtapp.makevfs("rev", "Main", "Data")
    initial = staqtapp.listfiles()["revision"]
    staqtapp.addvar("a", "1")
    staqtapp.changevar("a", "2")
    assert staqtapp.prune_revisions(2)
    result = staqtapp.rollback_revision(initial)
    assert not result and result.error_type == "RecoveryError"
    assert staqtapp.addvar("after", "ok") is None
