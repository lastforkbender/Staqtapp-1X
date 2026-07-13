from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import staqtapp

if __name__ == "__main__":
    staqtapp.configure(storage_dir=os.environ["STAQTAPP_TEST_HOME"])
    staqtapp.makevfs("spawnvfs", "SpawnDir", "SpawnFolder")
    staqtapp.appvar(["a", "b"], ["1", "2"], None)
    result = staqtapp.map_api_calls(
        [("findvar", ("a",)), ("loadvar", (True, "b", "s")), ("listvars", ())],
        processes=2,
        start_method="spawn",
    )
    assert result == [True, [2], ["a", "b"]], result
    staqtapp.makevfs("other", "OtherDir", "OtherFolder")
    results = staqtapp.map_vfs_api_calls([
        {"vfs": "spawnvfs", "directory": "SpawnDir", "folder": "SpawnFolder", "name": "addvar", "args": ("left", "11")},
        {"vfs": "other", "directory": "OtherDir", "folder": "OtherFolder", "name": "addvar", "args": ("right", "22")},
    ], processes=2, start_method="spawn")
    assert results == [None, None], results
    with staqtapp.open_vfs("spawnvfs", "SpawnDir", "SpawnFolder"):
        assert staqtapp.findvar("left") is True
    with staqtapp.open_vfs("other", "OtherDir", "OtherFolder"):
        assert staqtapp.findvar("right") is True
    failure = staqtapp.invoke_api("__dict__")
    assert isinstance(failure, staqtapp.CallFailure)
    assert failure.error_type == "ValueError"
    assert staqtapp.listvars() == ["right"]
