from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest
import staqtapp

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_backup_created_and_recovery(selected):
    staqtapp.addvar("alpha", "one")
    info = staqtapp.listfiles(); path = Path(info["vfs_file"])
    staqtapp.changevar("alpha", "two")
    backup = path.with_suffix(".sqtpp.bak")
    assert backup.is_file()
    assert staqtapp.loadvar(False, "alpha", "s") == ["two"]
    staqtapp.recover_vfs()
    assert staqtapp.loadvar(False, "alpha", "s") == ["one"]


def test_verify_and_migrate_legacy_fixture(home):
    source = FIXTURES / "stalk_history.sqtpp"
    report = staqtapp.verify_vfs(source, "AuditDir", "AuditFolder")
    assert report["ok"] is True
    assert report["variables"] >= 8
    destination = home / "migrated.sqtpp"
    migration = staqtapp.migrate_vfs(source, destination, "AuditDir", "AuditFolder")
    assert migration["ok"] is True
    assert source.read_bytes() == (FIXTURES / "stalk_history.sqtpp").read_bytes()
    assert staqtapp.verify_vfs(destination, "AuditDir", "AuditFolder")["ok"] is True


def test_legacy_file_mutates_without_losing_history_or_locks(home):
    target = home / "legacy.sqtpp"
    shutil.copy2(FIXTURES / "stalk_history.sqtpp", target)
    staqtapp.setpath("legacy", "AuditDir", "AuditFolder")
    before = staqtapp.verify_vfs()["history_roots"]
    staqtapp.addvar("newvar", "new")
    after = staqtapp.verify_vfs()
    assert after["history_roots"] == before
    assert after["lock_records"] >= 1
    assert staqtapp.findvar("newvar") is True


def test_diagnostics_are_bounded(selected):
    staqtapp.addvar("alpha", "one")
    assert staqtapp.diagnostic_counts()["variable_added"] >= 1
    assert len(staqtapp.recent_events(10)) <= 10
