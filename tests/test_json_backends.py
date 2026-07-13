from __future__ import annotations

import math
from pathlib import Path

import staqtapp
from staqtapp import json_backend, typed_values


def _sample():
    return {
        ("complex", 1): 3.5 - 2j,
        "unicode": "Zażółć β 漢字",
        "bytes": b"\x00\xff",
        "set": {3, 2, 1},
        "floats": (float("inf"), float("-inf"), -0.0),
        "huge": 10**200,
    }


def test_backend_info_is_public_and_verified():
    info = staqtapp.json_backend_info()
    assert info["format"] == "staqt-json-v1"
    assert info["fallback"] == "stdlib"
    assert info["active"] in {"stdlib", "orjson"}
    if info["orjson_installed"]:
        assert info["canonical_equivalence_verified"] is True


def test_forced_backends_emit_identical_bytes():
    json_backend.set_backend("stdlib")
    reference = typed_values.encode_typed(_sample())
    if json_backend.backend_info()["orjson_installed"]:
        json_backend.set_backend("orjson")
        assert typed_values.encode_typed(_sample()) == reference
    json_backend.set_backend("auto")


def test_auto_falls_back_when_native_dump_fails(monkeypatch):
    json_backend.set_backend("auto")
    monkeypatch.setattr(json_backend, "_ORJSON_VERIFIED", True)
    monkeypatch.setattr(json_backend, "_orjson_dumps", lambda value: (_ for _ in ()).throw(RuntimeError("native fail")))
    assert json_backend.dumps_canonical({"b": 2, "a": 1}) == b'{"a":1,"b":2}'


def test_forced_orjson_failure_is_contained(monkeypatch):
    if not json_backend.backend_info()["orjson_installed"]:
        return
    json_backend.set_backend("orjson")
    monkeypatch.setattr(json_backend, "_orjson_dumps", lambda value: (_ for _ in ()).throw(RuntimeError("native fail")))
    result = staqtapp.set_value("will_fail", {"x": 1})
    assert not result
    assert result.error_type == "RuntimeError"
    json_backend.set_backend("auto")


def test_invalid_backend_configuration_is_non_halting():
    result = staqtapp.configure(json_backend="unknown")
    assert not result
    assert result.error_type == "InvalidValueError"
    assert staqtapp.json_backend_info()["active"] in {"stdlib", "orjson"}


def test_cross_backend_storage_and_read(tmp_path):
    staqtapp.configure(storage_dir=tmp_path, json_backend="stdlib")
    staqtapp.makevfs("cross", "db", "main")
    assert not isinstance(staqtapp.set_value("value", _sample()), staqtapp.CallFailure)
    raw_stdlib = typed_values.encode_typed(_sample())
    if json_backend.backend_info()["orjson_installed"]:
        staqtapp.configure(json_backend="orjson")
    restored = staqtapp.get_value("value")
    assert restored[("complex", 1)] == 3.5 - 2j
    assert typed_values.encode_typed(restored) == raw_stdlib


def test_revision_id_is_backend_independent(tmp_path):
    staqtapp.configure(storage_dir=tmp_path, json_backend="stdlib")
    staqtapp.makevfs("rev", "db", "main")
    assert not isinstance(staqtapp.set_value("value", _sample()), staqtapp.CallFailure)
    first = staqtapp.list_revisions()[0]["revision"]
    if json_backend.backend_info()["orjson_installed"]:
        staqtapp.configure(json_backend="orjson")
    # Re-encoding the same value must not alter persistent bytes.
    assert staqtapp.get_value("value")[("complex", 1)] == 3.5 - 2j
    assert staqtapp.list_revisions()[0]["revision"] == first


def test_transaction_round_trip_under_each_backend(tmp_path):
    staqtapp.configure(storage_dir=tmp_path)
    staqtapp.makevfs("txjson", "db", "main")
    backends = ["stdlib"]
    if json_backend.backend_info()["orjson_installed"]:
        backends.append("orjson")
    for index, backend in enumerate(backends):
        staqtapp.configure(json_backend=backend)
        result = staqtapp.run_transaction([
            ("set_value", (f"v{index}", _sample())),
            ("set_value", (f"n{index}", index)),
        ])
        assert result
        assert staqtapp.get_value(f"v{index}")[("complex", 1)] == 3.5 - 2j


def test_noncanonical_json_rejected_with_accelerated_decoder():
    json_backend.set_backend("auto")
    raw = b'{"value":{"t":"int","v":"1"}, "codec":"staqt-json-v1"}'
    try:
        typed_values.decode_typed(raw)
    except Exception as exc:
        assert type(exc).__name__ == "InvalidValueError"
    else:
        raise AssertionError("noncanonical payload accepted")


def test_negative_zero_survives_backend_switch():
    json_backend.set_backend("stdlib")
    raw = typed_values.encode_typed(-0.0)
    if json_backend.backend_info()["orjson_installed"]:
        json_backend.set_backend("orjson")
    value = typed_values.decode_typed(raw)
    assert value == 0.0 and math.copysign(1.0, value) < 0
    json_backend.set_backend("auto")
