from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import staqtapp
from staqtapp import CallFailure
from staqtapp import transaction
from staqtapp.errors import TransactionError


def test_plan_is_ordered_and_sized():
    plan = transaction.plan_from_replacements(10, [(2, 4, b"XYZ"), (7, 8, b"")])
    assert plan.destination_size == 10
    assert plan.bytes_copied == 7
    assert plan.operations == (
        transaction.SourceSpan(0, 2),
        transaction.ReplacementBytes(b"XYZ"),
        transaction.SourceSpan(4, 7),
        transaction.SourceSpan(8, 10),
    )


def test_required_mutations_use_streaming_writer(selected):
    staqtapp.addvar("a", "one")
    staqtapp.appvar(["b", "c"], ["two", "three"], None)
    staqtapp.changevar("a", "ONE")
    staqtapp.renamevar_stx("b", "renamed")
    staqtapp.joinvars("joined", ["a", "renamed"])
    staqtapp.removevar("c")
    assert staqtapp.listvars() == ["a", "renamed", "joined"]
    assert staqtapp.verify_vfs()["ok"] is True


def test_interruption_before_atomic_replace_preserves_commit(selected, monkeypatch):
    staqtapp.addvar("stable", "before")
    path = Path(selected) / "testvfs.sqtpp"
    before = path.read_bytes()
    before_hash = hashlib.sha256(before).hexdigest()
    real_replace = transaction.os.replace

    def fail_destination_replace(source, destination):
        if Path(destination) == path and str(source).endswith(".tmp"):
            raise OSError("simulated interruption")
        return real_replace(source, destination)

    monkeypatch.setattr(transaction.os, "replace", fail_destination_replace)
    failure = staqtapp.changevar("stable", "after")
    assert isinstance(failure, CallFailure)
    assert failure.error_type == "TransactionError"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before_hash
    assert staqtapp.loadvar(False, "stable", "s") == ["before"]


def test_backup_recovers_previous_revision(selected):
    staqtapp.addvar("a", "one")
    staqtapp.changevar("a", "two")
    staqtapp.recover_vfs()
    assert staqtapp.loadvar(False, "a", "s") == ["one"]
