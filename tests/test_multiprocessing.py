from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path


def test_spawn_dispatch(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    env["STAQTAPP_TEST_HOME"] = str(tmp_path / "spawn-home")
    subprocess.run([sys.executable, str(root / "tests" / "spawn_check.py")], check=True, env=env)
