from __future__ import annotations

from collections import deque
from pathlib import Path

import pytest
import staqtapp
from staqtapp import CallFailure
from staqtapp.errors import (
    DuplicateVariableError, UnsafePatternError, UnsupportedLegacyFeatureError,
    VariableLockedError, VariableNotFoundError, VFSAlreadyExistsError,
)


def test_lifecycle_and_plain_text_normalization(selected):
    staqtapp.addvar("alpha", "one")
    staqtapp.addvar("beta", "@qp(2):")
    assert staqtapp.listvars() == ["alpha", "beta"]
    assert staqtapp.findvar("alpha") is True
    assert staqtapp.findvar("missing") is False
    assert staqtapp.loadvar(False, "alpha", "s") == ["one"]
    assert staqtapp.loadvar(True, "beta", "d") == deque([2])
    assert staqtapp.changevar("alpha", "changed") == 8
    assert staqtapp.renamevar_stx("alpha", "gamma") == 1
    staqtapp.joinvars("joined", ["gamma", "beta"])
    assert staqtapp.loadvar(False, "joined", "s") == ["changed", 2]
    staqtapp.removevar("beta")
    assert staqtapp.listvars() == ["gamma", "joined"]


def test_overwrite_and_false_success_are_removed(selected):
    failures = [
        staqtapp.makevfs("testvfs", "OtherDir", "OtherFolder"),
        staqtapp.removevar("missing"),
        staqtapp.joinvars("joined", ["missing"]),
    ]
    assert [failure.error_type for failure in failures] == [
        "VFSAlreadyExistsError", "VariableNotFoundError", "VariableNotFoundError"
    ]
    assert all(isinstance(failure, CallFailure) and not failure for failure in failures)
    assert staqtapp.listvars() == []


def test_batch_is_atomic(selected):
    staqtapp.addvar("exists", "x")
    failure = staqtapp.appvar(["new", "exists"], ["a", "b"], None)
    assert isinstance(failure, CallFailure)
    assert failure.error_type == "DuplicateVariableError"
    assert staqtapp.findvar("new") is False


def test_locks_are_enforced(selected):
    staqtapp.addvar("alpha", "one")
    staqtapp.lockvar("alpha", "changevar")
    assert staqtapp.keyvar("alpha", "changevar") is True
    assert staqtapp.locklist("alpha") == ["changevar"]
    failure = staqtapp.changevar("alpha", "two")
    assert isinstance(failure, CallFailure)
    assert failure.error_type == "VariableLockedError"
    assert staqtapp.loadvar(False, "alpha", "s") == ["one"]
    staqtapp.lockdel(False, "alpha", "changevar")
    staqtapp.changevar("alpha", "two")
    assert staqtapp.loadvar(False, "alpha", "s") == ["two"]


def test_stalk_history_and_findvar_stx(selected):
    staqtapp.addvar("gamma", "base")
    staqtapp.stalkvar("gamma", "history-1")
    staqtapp.stalkvar("gamma", "history-2")
    assert "gamma_1" in staqtapp.listvars()
    assert staqtapp.findvar_stx(["gamma"], "gamma") == ["gamma_1=-1"]
    assert staqtapp.findvar_stx(["gamma", "missing"], None) == [True, False]


def test_corevar_roundtrip(selected):
    source = [True, False, True, True, True, False]
    assert staqtapp.corevar(1, "bits", source) is None
    assert staqtapp.corevar(2, "bits", []) == source
    runs = staqtapp.corevar(3, "bits", [])
    assert isinstance(runs, list) and all(isinstance(item, tuple) for item in runs)


def test_arbitrary_text_uses_safe_extension(selected):
    text = "line one\nline two):still data"
    staqtapp.addvar("text", text)
    assert staqtapp.loadvar(False, "text", "s") == [text]


def test_regex_policy(selected):
    staqtapp.addvar("alpha", "hello")
    assert staqtapp.vardata_stx(True, ["alpha"], r"hel+o") == ["alpha"]
    failure = staqtapp.vardata_stx(True, ["alpha"], r"(a+)+$")
    assert isinstance(failure, CallFailure)
    assert failure.error_type == "UnsafePatternError"


def test_unsafe_legacy_features_are_explicitly_disabled(selected):
    first = staqtapp.registry(True, "key", None, "schema")
    second = staqtapp.lambdavar("f", [])
    assert first.error_type == "UnsupportedLegacyFeatureError"
    assert second.error_type == "UnsupportedLegacyFeatureError"
