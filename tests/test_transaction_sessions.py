from pathlib import Path
import staqtapp


def test_transaction_read_own_writes_and_commit_once(home):
    staqtapp.makevfs("tx", "Main", "Data")
    result = staqtapp.run_transaction([
        ("addvar", ("alpha", "1")),
        ("changevar", ("alpha", "2")),
        ("joinvars", ("joined", ["alpha"])),
    ])
    assert result
    assert result.operations == 3
    assert staqtapp.loadvar(False, "alpha", "s") == [2]
    assert staqtapp.loadvar(False, "joined", "s") == [2]


def test_transaction_failure_rolls_back_and_execution_continues(home):
    staqtapp.makevfs("tx", "Main", "Data")
    path = Path(staqtapp.listfiles()["vfs_file"])
    before = path.read_bytes()
    result = staqtapp.run_transaction([
        ("addvar", ("alpha", "1")),
        ("addvar", ("alpha", "duplicate")),
        ("addvar", ("beta", "2")),
    ])
    assert not result
    assert result.failure.error_type == "DuplicateVariableError"
    assert path.read_bytes() == before
    assert staqtapp.addvar("after_failure", "ok") is None
    assert staqtapp.findvar("after_failure") is True


def test_transaction_rejects_non_mutation_without_halting(home):
    staqtapp.makevfs("tx", "Main", "Data")
    result = staqtapp.run_transaction([("listvars", ())])
    assert not result
    assert "not transaction-capable" in result.failure.message
    assert staqtapp.listvars() == []


def test_explicit_vfs_transaction(home):
    staqtapp.makevfs("one", "Main", "Data")
    staqtapp.makevfs("two", "Main", "Data")
    result = staqtapp.run_vfs_transaction("one", "Main", "Data", [
        ("addvar", ("only_one", "yes")),
    ])
    assert result
    staqtapp.setpath("one", "Main", "Data")
    assert staqtapp.findvar("only_one") is True
    staqtapp.setpath("two", "Main", "Data")
    assert staqtapp.findvar("only_one") is False
