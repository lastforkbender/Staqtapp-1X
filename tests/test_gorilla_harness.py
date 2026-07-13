from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    path = Path(__file__).parents[1] / "tools" / "gorilla_benchmark.py"
    spec = importlib.util.spec_from_file_location("gorilla_benchmark", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_quick_gorilla_profile_is_reproducible_and_clean(tmp_path):
    module = _load_module()
    report = module.run("quick", seed=149)
    assert report["schema"] == "staqtapp-gorilla-v1"
    assert report["summary"]["failed"] == 0
    assert report["summary"]["samples"] >= 20
    assert len(report["report_sha256"]) == 64
    module.write_outputs(report, tmp_path)
    assert json.loads((tmp_path / "benchmark-results.json").read_text())["summary"]["failed"] == 0
    assert (tmp_path / "benchmark-results.csv").stat().st_size > 100
    assert "Passed cases" in (tmp_path / "benchmark-summary.md").read_text()


def test_unknown_profile_is_rejected():
    module = _load_module()
    try:
        module.run("impossible")
    except ValueError as exc:
        assert "unknown profile" in str(exc)
    else:
        raise AssertionError("unknown profile must fail")
