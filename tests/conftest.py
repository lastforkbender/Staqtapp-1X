from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import staqtapp

@pytest.fixture
def home(tmp_path):
    root = tmp_path / "home"
    staqtapp.configure(storage_dir=root)
    return root

@pytest.fixture
def selected(home):
    staqtapp.makevfs("testvfs", "AuditDir", "AuditFolder")
    return home
