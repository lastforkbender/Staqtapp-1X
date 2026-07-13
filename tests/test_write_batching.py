from __future__ import annotations

import os
import time

import staqtapp


def _setup(tmp_path):
    staqtapp.configure(storage_dir=tmp_path, write_batching=False)
    result = staqtapp.makevfs("batched", "data", "main")
    assert not isinstance(result, staqtapp.CallFailure)


def test_batching_disabled_by_default(tmp_path):
    _setup(tmp_path)
    result = staqtapp.addvar("a", "1")
    assert not isinstance(result, staqtapp.QueuedResult)
    assert staqtapp.findvar("a") is True


def test_explicit_queue_and_flush(tmp_path):
    _setup(tmp_path)
    info = staqtapp.configure(write_batching=True, batch_max_wait_ms=1000)
    assert info["write_batching"]["enabled"] is True
    r1 = staqtapp.addvar("a", "1")
    r2 = staqtapp.set_value("b", {"x": 2})
    assert isinstance(r1, staqtapp.QueuedResult) and r1.queued and not r1.durable
    assert r1.batch_id == r2.batch_id
    pending = staqtapp.pending_writes()
    assert len(pending) == 1 and pending[0]["operations"] == 2
    flushed = staqtapp.flush_writes()
    assert flushed and flushed.operations == 2 and flushed.batches == 1
    assert staqtapp.findvar("a") is True
    assert staqtapp.get_value("b") == {"x": 2}
    info = staqtapp.write_batching_info()
    assert info["physical_commits_avoided"] >= 1


def test_read_flushes_pending_writes(tmp_path):
    _setup(tmp_path)
    staqtapp.configure(write_batching=True, batch_max_wait_ms=1000)
    staqtapp.addvar("a", "1")
    assert staqtapp.write_batching_info()["pending_operations"] == 1
    assert staqtapp.findvar("a") is True
    assert staqtapp.write_batching_info()["pending_operations"] == 0


def test_batch_failure_is_contained_and_no_partial_commit(tmp_path):
    _setup(tmp_path)
    staqtapp.configure(write_batching=True, batch_max_wait_ms=1000)
    staqtapp.addvar("a", "1")
    staqtapp.addvar("a", "duplicate")
    staqtapp.addvar("b", "2")
    result = staqtapp.flush_writes()
    assert not result
    staqtapp.configure(write_batching=False)
    assert staqtapp.findvar("a") is False
    assert staqtapp.findvar("b") is False
    assert not isinstance(staqtapp.addvar("after", "ok"), staqtapp.CallFailure)


def test_threshold_flush_and_single_revision(tmp_path):
    _setup(tmp_path)
    before = len(staqtapp.list_revisions())
    staqtapp.configure(write_batching=True, batch_max_operations=3, batch_max_wait_ms=1000)
    staqtapp.addvar("a", "1")
    staqtapp.addvar("b", "2")
    staqtapp.addvar("c", "3")
    assert staqtapp.write_batching_info()["pending_operations"] == 0
    staqtapp.configure(write_batching=False)
    assert len(staqtapp.list_revisions()) == before + 1


def test_timer_flush(tmp_path):
    _setup(tmp_path)
    staqtapp.configure(write_batching=True, batch_max_wait_ms=20)
    staqtapp.addvar("timer", "yes")
    deadline = time.time() + 2
    while staqtapp.write_batching_info()["pending_operations"] and time.time() < deadline:
        time.sleep(0.01)
    assert staqtapp.write_batching_info()["pending_operations"] == 0
    staqtapp.configure(write_batching=False)
    assert staqtapp.findvar("timer") is True


def test_explicit_transaction_flushes_prior_batch_and_is_not_merged(tmp_path):
    _setup(tmp_path)
    staqtapp.configure(write_batching=True, batch_max_wait_ms=1000)
    staqtapp.addvar("queued", "q")
    result = staqtapp.run_transaction([("addvar", ("explicit", "e"))])
    assert result
    staqtapp.configure(write_batching=False)
    assert staqtapp.findvar("queued") and staqtapp.findvar("explicit")
    assert len(staqtapp.list_revisions()) >= 3


def test_invalid_batch_configuration_is_contained(tmp_path):
    _setup(tmp_path)
    result = staqtapp.configure(write_batching=True, batch_max_operations=0)
    assert not result
    assert not isinstance(staqtapp.addvar("still", "works"), staqtapp.CallFailure)


def test_fork_child_clears_inherited_queue_when_supported(tmp_path):
    if not hasattr(os, "fork"):
        return
    _setup(tmp_path)
    staqtapp.configure(write_batching=True, batch_max_wait_ms=1000)
    staqtapp.addvar("parent", "queued")
    pid = os.fork()
    if pid == 0:
        try:
            os._exit(0 if staqtapp.write_batching_info()["pending_operations"] == 0 else 3)
        except BaseException:
            os._exit(4)
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 0
    assert staqtapp.flush_writes()
