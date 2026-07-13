import math
import os
from pathlib import Path

import pytest
import staqtapp
from staqtapp import typed_values


def test_roundtrip_all_explicit_types(selected):
    value = {
        "none": None, "bool": True, "int": 10**100, "float": -0.0,
        "complex": 3.5-2j, "str": "λ\ntext", "bytes": b"\x00\xff",
        "list": [1, "x"], "tuple": (2, False), "set": {3, 1, 2},
        "frozen": frozenset({"b", "a"}), ("tuple", 1): {1: "one"},
    }
    assert staqtapp.set_value("typed", value) is None
    got = staqtapp.get_value("typed")
    assert got == value
    assert math.copysign(1.0, got["float"]) == -1.0


def test_float_specials_and_complex(selected):
    staqtapp.set_value("special", [float("nan"), float("inf"), float("-inf"), complex(-0.0, float("inf"))])
    got = staqtapp.get_value("special")
    assert math.isnan(got[0]) and got[1] == float("inf") and got[2] == float("-inf")
    assert math.copysign(1.0, got[3].real) == -1.0 and got[3].imag == float("inf")


def test_encoding_is_deterministic_for_dict_and_sets():
    a = {"set": {3,1,2}, 4: "x", (2,1): frozenset({"z","a"})}
    b = {(2,1): frozenset({"a","z"}), 4: "x", "set": {2,3,1}}
    assert typed_values.encode_typed(a) == typed_values.encode_typed(b)


def test_cycle_is_contained_and_execution_continues(selected):
    value=[]; value.append(value)
    failure=staqtapp.set_value("cycle", value)
    assert not failure and failure.error_type == "InvalidValueError"
    assert staqtapp.set_value("after", 7) is None
    assert staqtapp.get_value("after") == 7


def test_custom_class_rejected(selected):
    class Unsafe: pass
    result=staqtapp.set_value("unsafe", Unsafe())
    assert not result and "unsupported typed value" in result.message


def test_expected_type_exact_check(selected):
    staqtapp.set_value("number", True)
    assert staqtapp.get_value("number", bool) is True
    result=staqtapp.get_value("number", int)
    assert not result and result.error_type == "InvalidValueError"


def test_inspect_and_validate(selected):
    staqtapp.set_value("items", (1,2,3))
    info=staqtapp.inspect_value("items")
    assert info["name"] == "items" and info["type"] == "tuple" and info["logical_length"] == 3
    assert info["codec"] == "staqt-json-v1" and info["encoded_size"] > 0
    assert staqtapp.validate_value("items") is True


def test_ranges_exact_boundaries(selected):
    staqtapp.set_value("rangev", {"text":"abcdef"})
    raw=typed_values.encode_typed({"text":"abcdef"})
    assert staqtapp.read_range("rangev",0,0) == b""
    assert staqtapp.read_range("rangev",0,len(raw)) == raw
    assert staqtapp.read_range("rangev",len(raw),None) == b""
    assert staqtapp.read_range("rangev",3,7) == raw[3:10]
    assert b"".join(staqtapp.iter_value("rangev",7)) == raw


def test_invalid_ranges_are_non_halting(selected):
    staqtapp.set_value("rangev", 1)
    for args in [(-1,None),(0,-1),(10_000,None)]:
        result=staqtapp.read_range("rangev",*args)
        assert not result
    assert not staqtapp.iter_value("rangev",0)
    assert staqtapp.get_value("rangev") == 1


def test_legacy_string_is_not_misdecoded(selected):
    staqtapp.addvar("legacy","hello")
    result=staqtapp.get_value("legacy")
    assert not result and result.error_type == "InvalidValueError"
    assert staqtapp.loadvar(False,"legacy","s") == ["hello"]


def test_set_value_upserts_and_revisions(selected):
    before=len(staqtapp.list_revisions())
    assert staqtapp.set_value("x",1) is None
    assert staqtapp.set_value("x",2) == 8
    assert staqtapp.get_value("x") == 2
    assert len(staqtapp.list_revisions()) == before+2


def test_typed_transaction_read_final_and_single_revision(selected):
    before=len(staqtapp.list_revisions())
    result=staqtapp.run_transaction([
        ("set_value",("a", {"n":1})),
        ("set_value",("a", {"n":2})),
        ("set_value",("b", 3+4j)),
    ])
    assert result and result.operations == 3
    assert staqtapp.get_value("a") == {"n":2} and staqtapp.get_value("b") == 3+4j
    assert len(staqtapp.list_revisions()) == before+1


def test_invalid_typed_transaction_rolls_back(selected):
    bad=[]; bad.append(bad)
    before=Path(staqtapp.listfiles()["vfs_file"]).read_bytes()
    result=staqtapp.run_transaction([
        ("set_value",("first",1)), ("set_value",("bad",bad)), ("set_value",("last",3))
    ])
    assert not result
    assert Path(staqtapp.listfiles()["vfs_file"]).read_bytes() == before
    assert not staqtapp.findvar("first") and not staqtapp.findvar("last")
    assert staqtapp.set_value("after",4) is None


def test_typed_value_rollback_exact(selected):
    staqtapp.set_value("state", {"v":1,"z":2j})
    target=staqtapp.list_revisions()[0]["revision"]
    staqtapp.set_value("state", {"v":2})
    assert staqtapp.rollback_revision(target)
    assert staqtapp.get_value("state") == {"v":1,"z":2j}


def test_malformed_canonical_payload_rejected(selected):
    import base64
    malformed=b'{"value":{"t":"int","v":"1"},"codec":"staqt-json-v1"}' # valid JSON, noncanonical key order
    staqtapp.addvar("badtyped", typed_values.MAGIC + base64.urlsafe_b64encode(malformed).decode("ascii"))
    result=staqtapp.get_value("badtyped")
    assert not result and "canonically" in result.message
    assert staqtapp.set_value("good",5) is None


def test_depth_limit_contained(selected):
    value=0
    for _ in range(typed_values.MAX_DEPTH+2): value=[value]
    result=staqtapp.set_value("deep",value)
    assert not result
    assert staqtapp.set_value("shallow",[1]) is None
