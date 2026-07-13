from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
from collections import OrderedDict, deque
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from . import codec
from . import typed_values
from . import integrity
from . import recovery
from . import maintenance
from .config import persist_selection, selected, storage_root, temporary_selection
from .diagnostics import emit
from .errors import (
    DuplicateVariableError,
    FormatError,
    InvalidPathError,
    InvalidVariableNameError,
    InvalidValueError,
    InvalidVFSNameError,
    MigrationError,
    UnsafePatternError,
    UnsupportedLegacyFeatureError,
    VariableLockedError,
    VariableNotFoundError,
    VFSAlreadyExistsError,
    VFSNotFoundError,
)
from .model import OpaqueRecord, VariableRecord, VFSImage
from .parser import parse_vfs, parse_vfs_source, serialize_mutation_plan, serialize_vfs
from .snapshot import MappedVFS, sidecar_path
from .transaction import identity, mutate, restore_backup, restore_revision
from .revisions import ensure_current_recorded, list_revisions as revision_list, prune_revisions as revision_prune, revision_object
from .revisions import storage_report as revision_storage_stats

_VFS_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_CONTAINER_NAME = re.compile(r"^[A-Za-z][A-Za-z-]*$")
_VARIABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_UNSAFE_REGEX = re.compile(r"(?:\([^)]*[+*][^)]*\)[+*])|(?:\\[1-9])|(?:\(\?<[=!])")

_READ_CACHE: OrderedDict[tuple, MappedVFS] = OrderedDict()
_READ_CACHE_LOCK = threading.RLock()
# The cache is bounded by estimated Python index heap, not by an arbitrary
# number of potentially huge VFS files. The mapped file pages remain managed
# by the operating system.
_READ_CACHE_MAX_INDEX_BYTES = 64 * 1024 * 1024
_READ_CACHE_MAX_ENTRIES = 64
_READ_CACHE_INDEX_BYTES = 0

def _stat_key(path: Path, directory: str, folder: str) -> tuple:
    stat = path.stat()
    return (str(path.resolve()), directory, folder, stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)

def _evict_cache_locked() -> None:
    global _READ_CACHE_INDEX_BYTES
    while _READ_CACHE and (
        _READ_CACHE_INDEX_BYTES > _READ_CACHE_MAX_INDEX_BYTES
        or len(_READ_CACHE) > _READ_CACHE_MAX_ENTRIES
    ):
        _, snapshot = _READ_CACHE.popitem(last=False)
        _READ_CACHE_INDEX_BYTES -= snapshot.index_weight
        # Do not close here. A concurrent operation may still hold a reference.
        # CPython closes the mapping when the final reference is released.

def _invalidate_read_cache(path: Path) -> None:
    global _READ_CACHE_INDEX_BYTES
    resolved = str(path.resolve())
    with _READ_CACHE_LOCK:
        for key in [candidate for candidate in _READ_CACHE if candidate[0] == resolved]:
            snapshot = _READ_CACHE.pop(key)
            _READ_CACHE_INDEX_BYTES -= snapshot.index_weight

def _read_snapshot(path: Path, directory: str, folder: str) -> MappedVFS:
    global _READ_CACHE_INDEX_BYTES
    key = _stat_key(path, directory, folder)
    # Persistent mappings are safe across atomic replacement on POSIX. On
    # Windows, use an operation-scoped mapping so replacement is never held up
    # by the process-local cache.
    cacheable = os.name != "nt"
    if cacheable:
        with _READ_CACHE_LOCK:
            cached = _READ_CACHE.get(key)
            if cached is not None and not cached.closed:
                _READ_CACHE.move_to_end(key)
                emit("index_cache_hit", path=str(path))
                return cached

    snapshot = MappedVFS(path, directory, folder)
    final_key = _stat_key(path, directory, folder)
    if final_key != key:
        snapshot.close()
        snapshot = MappedVFS(path, directory, folder)
        final_key = _stat_key(path, directory, folder)
    if cacheable:
        with _READ_CACHE_LOCK:
            previous = _READ_CACHE.pop(final_key, None)
            if previous is not None:
                _READ_CACHE_INDEX_BYTES -= previous.index_weight
            _READ_CACHE[final_key] = snapshot
            _READ_CACHE_INDEX_BYTES += snapshot.index_weight
            _READ_CACHE.move_to_end(final_key)
            _evict_cache_locked()
    emit(
        "sidecar_index_loaded" if snapshot.index_source == "sidecar" else "mapped_index_built",
        path=str(path),
        variables=snapshot.variable_count,
        index_bytes=snapshot.index_weight,
    )
    return snapshot


def validate_vfs_name(name: str) -> str:
    if not isinstance(name, str) or not _VFS_NAME.fullmatch(name) or name in {".", ".."}:
        raise InvalidVFSNameError("VFS name must use letters, digits, '_' or '-' and cannot contain a path")
    return name


def validate_container(name: str, label: str) -> str:
    if not isinstance(name, str) or not _CONTAINER_NAME.fullmatch(name):
        raise InvalidPathError(f"{label} name must begin with a letter and contain only letters or '-'")
    return name


def validate_variable(name: str) -> str:
    if not isinstance(name, str) or not _VARIABLE_NAME.fullmatch(name):
        raise InvalidVariableNameError("variable name must match [A-Za-z_][A-Za-z0-9_]*")
    return name


def vfs_path(name: str) -> Path:
    return storage_root() / f"{validate_vfs_name(name)}.sqtpp"


def _current() -> tuple[Path, str, str, str]:
    name, directory, folder = selected()
    path = vfs_path(name)
    if not path.is_file():
        raise VFSNotFoundError(f"VFS does not exist: {path}")
    return path, name, directory, folder


def _snapshot() -> MappedVFS:
    path, _, directory, folder = _current()
    snapshot = _read_snapshot(path, directory, folder)
    emit("vfs_opened", path=str(path), variables=snapshot.variable_count)
    return snapshot


def _find_record(image: VFSImage, name: str) -> VariableRecord:
    record = image.variable_map().get(name)
    if record is None:
        raise VariableNotFoundError(f"variable not found: {name}")
    return record


def _ensure_not_locked(image: VFSImage, name: str, operation: str) -> None:
    locks = image.locks.get(name, [])
    if "*" in locks or operation in locks:
        raise VariableLockedError(f"variable {name!r} is locked against {operation}")


def _mutate_current(event: str, change) -> None:
    path, _, directory, folder = _current()
    _invalidate_read_cache(path)
    def operation(source):
        image = parse_vfs_source(path, source, directory, folder)
        change(image)
        return serialize_mutation_plan(image)
    try:
        mutate(path, operation, event=event)
    finally:
        _invalidate_read_cache(path)
        # Sidecars contain no unique data. Removing a possibly stale index is
        # cheaper and clearer than carrying it across an atomic VFS revision.
        try:
            sidecar_path(path).unlink()
        except OSError:
            # A Windows reader may still have the disposable sidecar mapped.
            # Its identity check makes the stale index unusable, so failure to
            # unlink cannot compromise the committed VFS.
            pass
        try:
            integrity.publish_map(path, directory, folder)
        except Exception as exc:
            emit("integrity_map_publish_failed", path=str(path), error_type=type(exc).__name__, message=str(exc)[:1024])
        try:
            sidecar_path(path).unlink()
        except OSError:
            pass


def make_vfs(name: str, directory: str, folder: str) -> None:
    name = validate_vfs_name(name)
    directory = validate_container(directory, "directory")
    folder = validate_container(folder, "folder")
    if directory == folder:
        raise InvalidPathError("directory and folder names must differ")
    path = vfs_path(name)
    if path.exists():
        raise VFSAlreadyExistsError(f"refusing to overwrite existing VFS: {path}")
    source = (
        f":☆Staqtapp-v1.4.1\n"
        f"|:{directory}<{folder}>\n"
        f"_|:{folder}<sub-{folder}>\n"
        f"__|:sub-{folder}<tqpt-{folder},tpqt-{folder},null>\n"
        f"___|:tqpt-{folder}<tqpt,null,n>:\n"
        f"null:\n"
        f"___|:(tqpt-{folder})\n"
        f"___|:tpqt-{folder}<tpqt,null,n>:\n"
        f"null:\n"
        f"___|:(tpqt-{folder})\n"
        f"__|:(sub-{folder})\n"
        f"_|:({folder})\n"
        f"|:({directory})"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(source); stream.flush(); os.fsync(stream.fileno())
        try:
            os.link(tmp, path)
            os.unlink(tmp); tmp = ""
        except (AttributeError, OSError):
            # O_EXCL fallback preserves the no-overwrite guarantee.
            with path.open("xb") as target:
                target.write(source); target.flush(); os.fsync(target.fileno())
            os.unlink(tmp); tmp = ""
    finally:
        if tmp:
            try: os.unlink(tmp)
            except FileNotFoundError: pass
    persist_selection(name, directory, folder)
    integrity.publish_map(path, directory, folder)
    emit("vfs_created", path=str(path))


def select_vfs(name: str, directory: str, folder: str) -> None:
    name = validate_vfs_name(name)
    directory = validate_container(directory, "directory")
    folder = validate_container(folder, "folder")
    path = vfs_path(name)
    if not path.is_file():
        raise VFSNotFoundError(f"VFS does not exist: {path}")
    snapshot = _read_snapshot(path, directory, folder)
    if os.name == "nt":
        snapshot.close()
    persist_selection(name, directory, folder)
    emit("vfs_selected", path=str(path))


@contextmanager
def open_vfs(name: str, directory: str, folder: str) -> Iterator[None]:
    name = validate_vfs_name(name)
    directory = validate_container(directory, "directory")
    folder = validate_container(folder, "folder")
    path = vfs_path(name)
    if not path.is_file():
        raise VFSNotFoundError(f"VFS does not exist: {path}")
    snapshot = _read_snapshot(path, directory, folder)
    if os.name == "nt":
        snapshot.close()
    with temporary_selection(name, directory, folder):
        yield


def list_files() -> dict[str, Any]:
    path, name, directory, folder = _current()
    snapshot = _read_snapshot(path, directory, folder)
    return {
        "vfs_file": str(path),
        "vfs_name": name,
        "directory": directory,
        "folder": folder,
        "subfolder": f"sub-{folder}",
        "tqpt": f"tqpt-{folder}",
        "tpqt": f"tpqt-{folder}",
        "exists": path.is_file(),
        "revision": ensure_current_recorded(path).revision,
        "revision_kind": "sha256-content",
        "filesystem_generation": snapshot.revision_id,
        "read_engine": "mmap-span-index",
        "index_source": snapshot.index_source,
        "index_file": str(sidecar_path(path)),
        "index_exists": sidecar_path(path).is_file(),
        "variables": snapshot.variable_count,
    }



def _typed_text(name: str) -> str:
    name = validate_variable(name)
    values = load_variable(False, name, "s")
    if len(values) != 1 or not isinstance(values[0], str):
        raise InvalidValueError("variable does not contain one typed-value envelope")
    return values[0]

def set_typed_value(name: str, value: Any):
    name = validate_variable(name); text = typed_values.envelope(value)
    if find_variable(name):
        change_variable(name, text); return 8
    add_variable(name, text); return None

def get_typed_value(name: str, expected_type=None):
    value = typed_values.decode_typed(typed_values.unenvelope(_typed_text(name)))
    if expected_type is not None and type(value) is not expected_type:
        raise InvalidValueError(f"typed value has type {type(value).__name__}, expected {getattr(expected_type, '__name__', expected_type)!s}")
    return value

def inspect_typed_value(name: str):
    info = typed_values.inspect_raw(typed_values.unenvelope(_typed_text(name))).as_dict(); info["name"] = validate_variable(name); return info

def validate_typed_value(name: str):
    inspect_typed_value(name); return True

def read_payload_range(name: str, start=0, length=None):
    name = validate_variable(name)
    return _snapshot().payload_slice(name, start, length)

def read_typed_range(name: str, start=0, length=None):
    """Read canonical typed JSON bytes with bounded Base64 decoding.

    A finite ``length`` causes only the Base64 quartets covering that range to
    be copied and decoded from the mmap-backed VFS.
    """
    name = validate_variable(name)
    if type(start) is not int or start < 0: raise ValueError("start must be a non-negative integer")
    if length is not None and (type(length) is not int or length < 0): raise ValueError("length must be None or a non-negative integer")
    snapshot = _snapshot()
    span = snapshot.span(name)
    prefix = b"@qp(" + typed_values.MAGIC.encode("ascii")
    suffix = b"):"
    payload_length = span.payload_length
    if payload_length < len(prefix) + len(suffix):
        raise InvalidValueError("variable does not contain a Staqtapp typed value")
    if snapshot.payload_slice(name, 0, len(prefix)) != prefix or snapshot.payload_slice(name, payload_length-len(suffix), len(suffix)) != suffix:
        raise InvalidValueError("variable does not contain a Staqtapp typed value")
    encoded_length = payload_length - len(prefix) - len(suffix)
    tail = snapshot.payload_slice(name, len(prefix) + max(0, encoded_length-2), min(2, encoded_length))
    raw_size = typed_values.decoded_size_from_base64(encoded_length, tail)
    if start > raw_size:
        raise ValueError("start exceeds encoded typed-value size")
    requested_end = raw_size if length is None else min(raw_size, start + length)
    if requested_end == start:
        return b""
    quartet_start = (start // 3) * 4
    quartet_end = min(encoded_length, ((requested_end + 2) // 3) * 4)
    encoded = snapshot.payload_slice(name, len(prefix) + quartet_start, quartet_end - quartet_start)
    decoded_offset = (quartet_start // 4) * 3
    return typed_values.decode_base64_range(encoded, decoded_offset=decoded_offset, requested_start=start, requested_end=requested_end)

def iter_typed_value(name: str, chunk_size=1024*1024):
    if type(chunk_size) is not int or chunk_size < 1: raise ValueError("chunk_size must be a positive integer")
    raw = typed_values.unenvelope(_typed_text(name))
    return tuple(raw[i:i+chunk_size] for i in range(0,len(raw),chunk_size))

def list_variables() -> list[str]:
    return _snapshot().list_names()


def find_variable(name: str) -> bool:
    name = validate_variable(name)
    return _snapshot().contains(name)


def add_variable(name: str, value: str) -> None:
    name = validate_variable(name); payload = codec.normalize_payload(value)
    def change(image: VFSImage):
        if name in image.variable_map():
            raise DuplicateVariableError(f"variable already exists: {name}")
        image.records.append(VariableRecord(name, payload))
    _mutate_current("variable_added", change)


def add_variables(names: list[str], values: list[str], locks) -> None:
    if not isinstance(names, list) or not isinstance(values, list):
        raise TypeError("varNames and varDatas must be lists")
    checked = [validate_variable(n) for n in names]
    if len(set(checked)) != len(checked):
        raise DuplicateVariableError("batch contains duplicate variable names")
    payloads = [codec.normalize_payload(values[i]) if i < len(values) and values[i] is not None else codec.normalize_payload("null") for i in range(len(checked))]
    parsed_locks: dict[str, list[str]] = {}
    if locks is not None:
        if not isinstance(locks, list):
            raise TypeError("varLocks must be None or a list")
        for item in locks:
            if not isinstance(item, str) or ":" not in item:
                raise ValueError("each lock specification must be 'variable:operation[,operation]' ")
            var, ops = item.split(":", 1)
            var = validate_variable(var.strip())
            parsed_locks[var] = [validate_variable(op.strip()) if op.strip() != "*" else "*" for op in ops.split(",") if op.strip()]
    def change(image: VFSImage):
        existing = image.variable_map()
        collisions = [n for n in checked if n in existing]
        if collisions:
            raise DuplicateVariableError(f"variables already exist: {', '.join(collisions)}")
        for name, payload in zip(checked, payloads):
            image.records.append(VariableRecord(name, payload))
        for name, ops in parsed_locks.items():
            if name not in checked and name not in existing:
                raise VariableNotFoundError(f"cannot lock missing variable: {name}")
            image.locks[name] = list(dict.fromkeys(ops))
    _mutate_current("variables_added", change)


def load_variable(all_numbers: bool, name: str, mode: str):
    snapshot = _snapshot()
    if name == "*":
        recent = snapshot.locks.get("___SQTPP___MRSV___", [])
        if not recent:
            raise VariableNotFoundError("no stalk history value is available")
        name = recent[-1]
    else:
        name = validate_variable(name)
    normalized = mode.replace(" ", "")
    if normalized in {"d", "mode=deque"}: as_deque = True
    elif normalized in {"s", "mode=str"}: as_deque = False
    else: raise ValueError("mode must be 'd'/'mode=deque' or 's'/'mode=str'")
    payload = snapshot.payload_bytes(name)
    values = codec.decode_payload(payload, all_numbers=bool(all_numbers))
    return deque(values) if as_deque else values


def change_variable(name: str, value: str) -> int:
    name = validate_variable(name); payload = codec.normalize_payload(value)
    def change(image: VFSImage):
        _ensure_not_locked(image, name, "changevar")
        record = _find_record(image, name)
        record.payload = payload
    _mutate_current("variable_changed", change)
    return 8


def rename_variable(name: str, new_name: str) -> int:
    name = validate_variable(name); new_name = validate_variable(new_name)
    def change(image: VFSImage):
        _ensure_not_locked(image, name, "renamevar_stx")
        if any(name in values for values in image.histories.values()):
            raise VariableLockedError("history records cannot be renamed independently of their root")
        if new_name in image.variable_map():
            raise DuplicateVariableError(f"variable already exists: {new_name}")
        record = _find_record(image, name); record.name = new_name
        if name in image.locks: image.locks[new_name] = image.locks.pop(name)
        renamed_history: dict[str, str] = {}
        if name in image.histories:
            old_items = image.histories.pop(name)
            new_items = []
            for item in old_items:
                suffix = item[len(name):] if item.startswith(name) else f"_{len(new_items)+1}"
                target = new_name + suffix
                history_record = image.variable_map().get(item)
                if history_record: history_record.name = target
                renamed_history[item] = target
                new_items.append(target)
            image.histories[new_name] = new_items
        if renamed_history and "___SQTPP___MRSV___" in image.locks:
            image.locks["___SQTPP___MRSV___"] = [renamed_history.get(item, item) for item in image.locks["___SQTPP___MRSV___"]]
    _mutate_current("variable_renamed", change)
    return 1


def remove_variable(name: str) -> None:
    name = validate_variable(name)
    def change(image: VFSImage):
        _ensure_not_locked(image, name, "removevar")
        record = _find_record(image, name)
        if name in image.histories:
            raise VariableLockedError("stalked variables must have their history removed explicitly")
        if any(name in values for values in image.histories.values()):
            raise VariableLockedError("history records cannot be removed independently of their root")
        image.records.remove(record); image.locks.pop(name, None)
    _mutate_current("variable_removed", change)


def join_variables(new_name: str, names: list[str]) -> None:
    new_name = validate_variable(new_name)
    if not isinstance(names, list) or not names:
        raise ValueError("varNames must be a non-empty list")
    checked = [validate_variable(n) for n in names]
    def change(image: VFSImage):
        if new_name in image.variable_map():
            raise DuplicateVariableError(f"variable already exists: {new_name}")
        payloads = []
        for name in checked:
            _ensure_not_locked(image, name, "joinvars")
            payloads.append(_find_record(image, name).payload)
        image.records.append(VariableRecord(new_name, b"".join(payloads)))
    _mutate_current("variables_joined", change)


def search_variable_data(is_regex: bool, names: list[str], search: str) -> list[str]:
    if not isinstance(names, list) or not isinstance(search, str):
        raise TypeError("varNameList must be a list and search must be a string")
    checked = [validate_variable(n) for n in names]
    pattern = None
    if is_regex:
        if len(search) > 256 or _UNSAFE_REGEX.search(search):
            raise UnsafePatternError("regex rejected by Staqtapp's bounded safe-pattern policy")
        try: pattern = re.compile(search)
        except re.error as exc: raise UnsafePatternError(f"invalid regex: {exc}") from exc
    snapshot = _snapshot(); found = []
    literal = search.encode("utf-8") if not is_regex else None
    for name in checked:
        if not snapshot.contains(name):
            continue
        if snapshot.payload_length(name) > 1_000_000:
            raise UnsafePatternError("search payload exceeds the 1 MB safety limit")
        # @qp payloads store their text literally, so most non-matches can be
        # rejected against the mapping without allocating or decoding. Encoded
        # @qv1 payloads still require semantic decoding for correctness.
        payload = None
        if literal is not None and snapshot.payload_startswith(name, b"@qp("):
            if not snapshot.payload_contains(name, literal):
                continue
            payload = snapshot.payload_bytes(name)
        else:
            payload = snapshot.payload_bytes(name)
        try:
            decoded = codec.decode_payload(payload, all_numbers=False)
            text = " ".join(str(value) for value in decoded)
        except Exception:
            text = payload.decode("utf-8", "replace")
        if (pattern.search(text) if pattern else search in text):
            found.append(name)
    return found


def add_lock(name: str, operations) -> None:
    name = validate_variable(name)
    if isinstance(operations, str): operations = [operations]
    if not isinstance(operations, list) or not operations:
        raise TypeError("fncName must be a string or non-empty list")
    checked = [validate_variable(op) if op != "*" else "*" for op in operations]
    def change(image: VFSImage):
        _find_record(image, name)
        image.locks[name] = list(dict.fromkeys(image.locks.get(name, []) + checked))
    _mutate_current("lock_added", change)


def list_locks(name: str) -> list[str]:
    name = validate_variable(name); snapshot = _snapshot(); snapshot.span(name)
    return list(snapshot.locks.get(name, []))


def delete_lock(all_locks: bool, name: str, operations) -> None:
    name = validate_variable(name)
    def change(image: VFSImage):
        _find_record(image, name)
        if all_locks: image.locks.pop(name, None); return
        ops = [operations] if isinstance(operations, str) else operations
        if not isinstance(ops, list): raise TypeError("fncName must be a string or list")
        remaining = [v for v in image.locks.get(name, []) if v not in ops]
        if remaining: image.locks[name] = remaining
        else: image.locks.pop(name, None)
    _mutate_current("lock_removed", change)


def has_lock(name: str, operation: str) -> bool:
    name = validate_variable(name)
    snapshot = _snapshot(); snapshot.span(name)
    return operation in snapshot.locks.get(name, []) or "*" in snapshot.locks.get(name, [])


def stalk_variable(name: str, value: str) -> None:
    name = validate_variable(name); payload = codec.normalize_payload(value)
    def change(image: VFSImage):
        _ensure_not_locked(image, name, "stalkvar")
        base = _find_record(image, name)
        if base.payload == payload:
            raise ValueError("stalk value must differ from the base variable value")
        items = image.histories.setdefault(name, [])
        history_name = f"{name}_{len(items)+1}"
        if history_name in image.variable_map():
            raise DuplicateVariableError(f"history variable already exists: {history_name}")
        image.records.append(VariableRecord(history_name, payload)); items.append(history_name)
        image.locks.setdefault("___SQTPP___MRSV___", [])
        if history_name not in image.locks["___SQTPP___MRSV___"]:
            image.locks["___SQTPP___MRSV___"].append(history_name)
    _mutate_current("history_appended", change)


def find_variables_stx(names: list[str], stalk_name: str | None) -> list:
    if not isinstance(names, list) or not names:
        raise ValueError("varNameList must be a non-empty list")
    checked = [validate_variable(n) for n in names]
    snapshot = _snapshot()
    if not isinstance(stalk_name, str):
        return [snapshot.contains(name) for name in checked]
    stalk_name = validate_variable(stalk_name)
    history = snapshot.histories.get(stalk_name)
    if not history:
        raise VariableNotFoundError(f"stalk history not found: {stalk_name}")
    result = []
    for history_name, query_name in zip(history, checked):
        if not snapshot.contains(history_name):
            result.append(f"!spawned-var ({history_name}) data not found:None")
        elif not snapshot.contains(query_name):
            result.append(f"!searched-var ({query_name}) data not found:None")
        else:
            result.append(f"{history_name}={'1' if snapshot.payload_equal(history_name, query_name) else '-1'}")
    return result


def core_variable(mode: int, name: str, booleans: list):
    name = validate_variable(name)
    if mode == 1:
        payload = codec.encode_core(booleans)
        def change(image: VFSImage):
            if name in image.variable_map(): raise DuplicateVariableError(f"variable already exists: {name}")
            image.records.append(VariableRecord(name, payload))
        _mutate_current("corevar_added", change); return None
    if mode not in {2, 3}:
        raise ValueError("corevar mode must be 1, 2, or 3")
    payload = _snapshot().payload_bytes(name)
    return codec.decode_core(payload, runs=(mode == 3))


def verify(path: str | Path | None = None, directory: str | None = None, folder: str | None = None) -> dict[str, Any]:
    if path is None:
        current_path, _, current_dir, current_folder = _current()
        path = current_path; directory = current_dir; folder = current_folder
    else:
        path = Path(path).expanduser().resolve()
        if directory is None or folder is None:
            raise InvalidPathError("directory and folder are required when verifying an explicit path")
    try:
        with MappedVFS(path, directory, folder) as snapshot:
            return {
                "ok": True,
                "path": str(path),
                "sha256": snapshot.sha256(),
                "variables": snapshot.variable_count,
                "opaque_records": snapshot.opaque_records,
                "lock_records": len(snapshot.locks),
                "history_roots": len(snapshot.histories),
                "read_engine": "mmap-span-index",
                "index_source": snapshot.index_source,
                "index_file": str(sidecar_path(path)),
                "index_bytes_estimate": snapshot.index_weight,
            }
    except Exception as exc:
        return {"ok": False, "path": str(path), "error_type": type(exc).__name__, "error": str(exc)}


def migrate(source: str | Path, destination: str | Path, directory: str, folder: str, *, report_path: str | Path | None = None) -> dict[str, Any]:
    source = Path(source).expanduser().resolve(); destination = Path(destination).expanduser().resolve()
    if source == destination:
        raise MigrationError("migration destination must differ from source")
    if destination.exists():
        raise VFSAlreadyExistsError(f"migration destination exists: {destination}")
    image = parse_vfs(source, directory, folder)
    canonical = serialize_vfs(image)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp, destination); tmp = ""
    finally:
        if tmp:
            try: os.unlink(tmp)
            except FileNotFoundError: pass
    reopened = parse_vfs(destination, directory, folder)
    report = {
        "ok": True,
        "source": str(source),
        "destination": str(destination),
        "source_sha256": hashlib.sha256(image.source).hexdigest(),
        "destination_sha256": hashlib.sha256(reopened.source).hexdigest(),
        "variables_before": len(image.variable_map()),
        "variables_after": len(reopened.variable_map()),
        "locks_before": len(image.locks),
        "locks_after": len(reopened.locks),
        "history_roots_before": len(image.histories),
        "history_roots_after": len(reopened.histories),
        "opaque_records_preserved": sum(isinstance(r, OpaqueRecord) for r in reopened.records),
    }
    if report["variables_before"] != report["variables_after"] or report["locks_before"] != report["locks_after"]:
        destination.unlink(missing_ok=True)
        raise MigrationError("migration verification failed")
    if report_path is not None:
        Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    emit("vfs_migrated", source=str(source), destination=str(destination))
    return report


def recover_current() -> None:
    path, _, directory, folder = _current()
    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.is_file():
        raise MigrationError(f"backup does not exist: {backup}")
    parse_vfs(backup, directory, folder)
    restore_backup(path)
    _invalidate_read_cache(path)
    try:
        sidecar_path(path).unlink()
    except OSError:
        pass
    parse_vfs(path, directory, folder)
    integrity.publish_map(path, directory, folder)
    try: sidecar_path(path).unlink()
    except OSError: pass


def list_revision_history(limit: int | None = None) -> list[dict[str, Any]]:
    path, _, _, _ = _current()
    return [entry.as_dict() for entry in revision_list(path, limit)]


def rollback_to_revision(revision: str) -> dict[str, Any]:
    path, _, directory, folder = _current()
    target = revision_object(path, revision)
    # Never publish a revision that cannot be parsed in the selected container.
    parsed = parse_vfs(target, directory, folder)
    before = ensure_current_recorded(path).revision
    restored = restore_revision(path, revision)
    _invalidate_read_cache(path)
    try:
        sidecar_path(path).unlink()
    except OSError:
        pass
    parse_vfs(path, directory, folder)
    integrity.publish_map(path, directory, folder)
    try: sidecar_path(path).unlink()
    except OSError: pass
    return {
        "ok": True, "from_revision": before, "revision": restored,
        "variables": len(parsed.variable_map()), "vfs_file": str(path),
    }


def prune_revision_history(keep: int = 32) -> dict[str, Any]:
    path, _, _, _ = _current()
    removed = revision_prune(path, keep)
    return {"ok": True, "kept": keep, "objects_removed": removed}

def revision_storage_report() -> dict[str, Any]:
    path, _, _, _ = _current()
    return revision_storage_stats(path)

def rebuild_integrity_map() -> dict[str, Any]:
    path, _, directory, folder = _current()
    return integrity.publish_map(path, directory, folder)

def verify_integrity_map(*, deep: bool = True) -> dict[str, Any]:
    path, _, directory, folder = _current()
    return integrity.verify_map(path, directory, folder, deep=deep)

def integrity_report(*, rebuild_if_missing: bool = False, deep: bool = True) -> dict[str, Any]:
    path, _, directory, folder = _current()
    if rebuild_if_missing and not integrity.integrity_path(path).is_file():
        integrity.publish_map(path, directory, folder)
    return integrity.verify_map(path, directory, folder, deep=deep)



def read_index_info() -> dict[str, Any]:
    path, _, directory, folder = _current()
    with MappedVFS(path, directory, folder) as snapshot:
        return snapshot.index_info()

def rebuild_read_index() -> dict[str, Any]:
    path, _, directory, folder = _current()
    _invalidate_read_cache(path)
    try:
        sidecar_path(path).unlink(missing_ok=True)
    except OSError:
        pass
    with MappedVFS(path, directory, folder) as snapshot:
        info = snapshot.index_info()
    emit("read_index_rebuilt", path=str(path), variables=info["variables"], index_size=info["index_size"])
    return info

def repair_current(*, strategy: str = "surgical", source: str = "latest-valid-revision") -> dict[str, Any]:
    path, _, directory, folder = _current()
    _invalidate_read_cache(path)
    try:
        result = recovery.repair_vfs(path, directory, folder, strategy=strategy, source=source)
    finally:
        _invalidate_read_cache(path)
        try:
            sidecar_path(path).unlink()
        except OSError:
            pass
    return result


def optimize_current() -> dict[str, Any]:
    path, _, directory, folder = _current()
    _invalidate_read_cache(path)
    try:
        return maintenance.optimize_vfs(path, directory, folder)
    finally:
        _invalidate_read_cache(path)

def compact_current(*, keep_revisions: int = 32) -> dict[str, Any]:
    path, _, directory, folder = _current()
    _invalidate_read_cache(path)
    try:
        return maintenance.compact_vfs(path, directory, folder, keep_revisions=keep_revisions)
    finally:
        _invalidate_read_cache(path)

def unsupported(name: str):
    raise UnsupportedLegacyFeatureError(
        f"{name} is disabled in the stable engine because its legacy contract is unsafe or not yet recovered"
    )

# --- 1.4.3 multi-operation transaction overlay ---------------------------
_TRANSACTION_MUTATIONS = {"set_value", "addvar", "appvar", "changevar", "renamevar_stx", "removevar", "joinvars"}


def _apply_transaction_call(image: VFSImage, api_name: str, args: tuple, kwargs: dict):
    """Apply one supported public mutation to an uncommitted VFS image."""
    if kwargs:
        raise TypeError("transaction mutation calls currently accept positional arguments only")
    if api_name not in _TRANSACTION_MUTATIONS:
        raise ValueError(f"API is not transaction-capable: {api_name}")

    if api_name == "set_value":
        if len(args) != 2:
            raise TypeError("set_value requires (name, value)")
        name = validate_variable(args[0]); payload = codec.normalize_payload(typed_values.envelope(args[1]))
        current = image.variable_map().get(name)
        if current is None:
            image.records.append(VariableRecord(name, payload)); image.invalidate_variable_map(); return None
        _ensure_not_locked(image, name, "changevar")
        current.payload = payload
        return 8

    if api_name == "addvar":
        if len(args) != 2:
            raise TypeError("addvar requires (varName, varData)")
        name = validate_variable(args[0]); payload = codec.normalize_payload(args[1])
        if name in image.variable_map():
            raise DuplicateVariableError(f"variable already exists: {name}")
        image.records.append(VariableRecord(name, payload)); image.invalidate_variable_map()
        return None

    if api_name == "appvar":
        if len(args) != 3:
            raise TypeError("appvar requires (varNames, varDatas, varLocks)")
        names, values, locks = args
        if not isinstance(names, list) or not isinstance(values, list):
            raise TypeError("varNames and varDatas must be lists")
        checked = [validate_variable(n) for n in names]
        if len(set(checked)) != len(checked):
            raise DuplicateVariableError("batch contains duplicate variable names")
        existing = image.variable_map()
        collisions = [n for n in checked if n in existing]
        if collisions:
            raise DuplicateVariableError(f"variables already exist: {', '.join(collisions)}")
        payloads = [codec.normalize_payload(values[i]) if i < len(values) and values[i] is not None else codec.normalize_payload("null") for i in range(len(checked))]
        parsed_locks: dict[str, list[str]] = {}
        if locks is not None:
            if not isinstance(locks, list):
                raise TypeError("varLocks must be None or a list")
            for item in locks:
                if not isinstance(item, str) or ":" not in item:
                    raise ValueError("each lock specification must be 'variable:operation[,operation]'")
                var, ops = item.split(":", 1); var = validate_variable(var.strip())
                parsed_locks[var] = [validate_variable(op.strip()) if op.strip() != "*" else "*" for op in ops.split(",") if op.strip()]
        for name, payload in zip(checked, payloads):
            image.records.append(VariableRecord(name, payload))
        image.invalidate_variable_map()
        current = image.variable_map()
        for name, ops in parsed_locks.items():
            if name not in current:
                raise VariableNotFoundError(f"cannot lock missing variable: {name}")
            image.locks[name] = list(dict.fromkeys(ops))
        return None

    if api_name == "changevar":
        if len(args) != 2:
            raise TypeError("changevar requires (varName, newVarData)")
        name = validate_variable(args[0]); payload = codec.normalize_payload(args[1])
        _ensure_not_locked(image, name, "changevar")
        _find_record(image, name).payload = payload
        return 8

    if api_name == "renamevar_stx":
        if len(args) != 2:
            raise TypeError("renamevar_stx requires (varName, newVarName)")
        name = validate_variable(args[0]); new_name = validate_variable(args[1])
        _ensure_not_locked(image, name, "renamevar_stx")
        if any(name in values for values in image.histories.values()):
            raise VariableLockedError("history records cannot be renamed independently of their root")
        if new_name in image.variable_map():
            raise DuplicateVariableError(f"variable already exists: {new_name}")
        record = _find_record(image, name); record.name = new_name
        if name in image.locks: image.locks[new_name] = image.locks.pop(name)
        if name in image.histories:
            old_items = image.histories.pop(name); new_items = []
            for index, item in enumerate(old_items):
                suffix = item[len(name):] if item.startswith(name) else f"_{index + 1}"
                target = new_name + suffix
                history_record = image.variable_map().get(item)
                if history_record: history_record.name = target
                new_items.append(target)
            image.histories[new_name] = new_items
        image.invalidate_variable_map()
        return 1

    if api_name == "removevar":
        if len(args) != 1:
            raise TypeError("removevar requires (varName,)")
        name = validate_variable(args[0]); _ensure_not_locked(image, name, "removevar")
        record = _find_record(image, name)
        image.records.remove(record); image.locks.pop(name, None)
        image.histories.pop(name, None)
        image.invalidate_variable_map()
        return None

    if len(args) != 2:
        raise TypeError("joinvars requires (newVarName, varNames)")
    new_name = validate_variable(args[0]); names = args[1]
    if not isinstance(names, list) or not names:
        raise ValueError("varNames must be a non-empty list")
    checked = [validate_variable(n) for n in names]
    if new_name in image.variable_map():
        raise DuplicateVariableError(f"variable already exists: {new_name}")
    payloads = []
    for name in checked:
        _ensure_not_locked(image, name, "joinvars")
        payloads.append(_find_record(image, name).payload)
    image.records.append(VariableRecord(new_name, b"".join(payloads))); image.invalidate_variable_map()
    return None


def run_transaction_calls(calls: list[tuple[str, tuple, dict]]) -> tuple:
    """Commit supported mutations as one all-or-nothing VFS revision."""
    path, _, directory, folder = _current()
    results: list[Any] = []
    _invalidate_read_cache(path)

    def operation(source):
        image = parse_vfs_source(path, source, directory, folder)
        for api_name, args, kwargs in calls:
            results.append(_apply_transaction_call(image, api_name, args, kwargs))
        return serialize_mutation_plan(image)

    try:
        mutate(path, operation, event="transaction_committed")
        targets = []
        for api_name, args, _ in calls:
            if args and api_name in {"set_value", "addvar", "changevar", "renamevar_stx", "removevar", "joinvars"}:
                targets.append(str(args[0]))
            elif api_name == "appvar" and args and isinstance(args[0], list):
                targets.extend(str(item) for item in args[0])
        superseded = max(0, len(targets) - len(set(targets)))
        emit("transaction_operations_applied", path=str(path), operations=len(calls),
             unique_targets=len(set(targets)), superseded_operations=superseded,
             physical_commits=1)
        return tuple(results)
    finally:
        _invalidate_read_cache(path)
        try:
            sidecar_path(path).unlink()
        except OSError:
            pass
