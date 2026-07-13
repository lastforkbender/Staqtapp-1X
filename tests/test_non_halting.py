from __future__ import annotations

import staqtapp
from staqtapp import CallFailure


def test_direct_failure_does_not_halt_following_calls(selected):
    staqtapp.addvar("alpha", "one")
    failure = staqtapp.addvar("alpha", "duplicate")
    after = staqtapp.addvar("beta", "two")
    assert isinstance(failure, CallFailure)
    assert failure.error_type == "DuplicateVariableError"
    assert after is None
    assert staqtapp.listvars() == ["alpha", "beta"]


def test_map_returns_one_result_per_call_and_continues(selected):
    results = staqtapp.map_api_calls([
        ("addvar", ("one", "1")),
        ("addvar", ("one", "duplicate")),
        ("addvar", ("two", "2")),
        ("unknown", ()),
        {"broken": True},
    ], processes=1)
    assert len(results) == 5
    assert results[0] is None
    assert isinstance(results[1], CallFailure)
    assert results[2] is None
    assert isinstance(results[3], CallFailure)
    assert isinstance(results[4], CallFailure)
    assert staqtapp.listvars() == ["one", "two"]


def test_invalid_batch_configuration_is_contained_per_call(selected):
    results = staqtapp.map_api_calls([("listvars", ()), ("listvars", ())], chunksize=0)
    assert len(results) == 2
    assert all(isinstance(item, CallFailure) for item in results)
    assert all(item.error_type == "ValueError" for item in results)


def test_failure_is_diagnostic(selected):
    staqtapp.removevar("absent")
    counts = staqtapp.diagnostic_counts()
    assert counts.get("api_failure_contained", 0) >= 1
