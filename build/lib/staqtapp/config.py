from __future__ import annotations

import contextvars
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .errors import PathNotSelectedError

_STORAGE_ROOT = Path(os.environ.get("STAQTAPP_HOME", Path.home() / ".staqtapp" / "v1"))
_SELECTED: contextvars.ContextVar[tuple[str, str, str] | None] = contextvars.ContextVar(
    "staqtapp_selected", default=None
)

def storage_root() -> Path:
    _STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    return _STORAGE_ROOT

def configure(*, storage_dir: str | os.PathLike[str]) -> Path:
    global _STORAGE_ROOT
    _STORAGE_ROOT = Path(storage_dir).expanduser().resolve()
    os.environ["STAQTAPP_HOME"] = str(_STORAGE_ROOT)
    _STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    return _STORAGE_ROOT

def _settings_path() -> Path:
    return storage_root() / "selection.json"

def persist_selection(vfs: str, directory: str, folder: str) -> None:
    _SELECTED.set((vfs, directory, folder))
    target = _settings_path()
    fd, tmp = tempfile.mkstemp(prefix=".selection-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"vfs": vfs, "directory": directory, "folder": folder}, stream)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp, target)
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass

def selected() -> tuple[str, str, str]:
    value = _SELECTED.get()
    if value is not None:
        return value
    try:
        data = json.loads(_settings_path().read_text(encoding="utf-8"))
        value = (str(data["vfs"]), str(data["directory"]), str(data["folder"]))
        _SELECTED.set(value)
        return value
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PathNotSelectedError("no Staqtapp VFS path is selected") from exc

@contextmanager
def temporary_selection(vfs: str, directory: str, folder: str):
    token = _SELECTED.set((vfs, directory, folder))
    try:
        yield
    finally:
        _SELECTED.reset(token)
