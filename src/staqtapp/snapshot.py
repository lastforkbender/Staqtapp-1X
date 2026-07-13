from __future__ import annotations

import hashlib
import mmap
import os
import re
import struct
import tempfile
import threading
import zlib
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .errors import CorruptRecordError, FormatError, InvalidPathError, VariableNotFoundError

_HEADER = b":\xe2\x98\x86Staqtapp-v1."
_VALID_RECORD = re.compile(rb"(?m)^([A-Za-z_][A-Za-z0-9_]*)<(.*)>$")
_NONEMPTY_LINE = re.compile(rb"(?m)^.+$")
_LOCK_RECORD = re.compile(rb"<:([A-Za-z_][A-Za-z0-9_]*)=\n(.*?):>", re.DOTALL)
_HISTORY_RECORD = re.compile(rb"\(([A-Za-z_][A-Za-z0-9_]*)=([^)]*)\)")
_NAME = re.compile(rb"^[A-Za-z_][A-Za-z0-9_]*$")

_SQTI_MAGIC = b"SQTI140\0"
_SQTI_VERSION = 3
_SQTI_FLAG_OFFSETS_64 = 0x01
# magic, version, VFS identity (4Q), structural spans (5Q), history/opaque
# (3q), record count (Q), directory/folder byte lengths (2I)
_SQTI_HEADER = struct.Struct("<8sII" + "Q" * 9 + "q" * 3 + "QII")
# Small/medium files use 32-bit offsets; files beyond 4 GiB retain 64-bit
# addresses. Record boundaries are derivable from name/payload spans.
_SQTI_PHYSICAL32 = struct.Struct("<IIII")
_SQTI_PHYSICAL64 = struct.Struct("<QIQQ")
# CRC32 name hash, physical slot. Collisions are resolved against VFS bytes.
_SQTI_HASH = struct.Struct("<II")
_SQTI_DIGEST_SIZE = 32


def sidecar_path(path: str | Path) -> Path:
    """Return the disposable index path for an SQTPP file."""
    return Path(path).with_suffix(".sqti")


def _stable_name_hash(raw: bytes) -> int:
    return zlib.crc32(raw) & 0xFFFFFFFF



@dataclass(slots=True, frozen=True)
class VariableSpan:
    """Address of one variable inside an immutable SQTPP snapshot."""

    name: str
    record_start: int
    record_end: int
    payload_start: int
    payload_end: int

    @property
    def payload_length(self) -> int:
        return self.payload_end - self.payload_start


class MappedVFS:
    """Read-only, low-allocation view over one committed SQTPP revision.

    The VFS itself remains memory-mapped. A disposable, checksummed ``.sqti``
    sidecar is also mapped and searched by stable name hash, so a subsequent
    process can open a large VFS without rebuilding Python objects for every
    record. On a first scan, compact arrays and one temporary name dictionary
    are used to construct the sidecar. Locks and histories remain lazy.
    """

    __slots__ = (
        "path", "directory", "folder", "_stream", "_mapped", "_closed",
        "_stat", "tqpt_body_start", "tqpt_body_end", "tpqt_body_start",
        "tpqt_body_end", "tqpt_marker_start", "history_span", "_variables",
        "_variable_order", "name_starts", "name_lengths", "name_hashes",
        "payload_starts", "payload_ends",
        "opaque_records", "_locks", "_histories", "_lazy_lock",
        "index_weight", "_digest", "index_source", "_index_stream",
        "_index_mapped", "_entry_count", "_physical_offset", "_hash_offset",
        "_names_offset", "_names_end", "_physical_struct",
    )

    def __init__(self, path: str | Path, directory: str, folder: str):
        self.path = Path(path)
        self.directory = directory
        self.folder = folder
        self._stream = self.path.open("rb")
        self._index_stream = None
        self._index_mapped = None
        try:
            self._stat = os.fstat(self._stream.fileno())
            if self._stat.st_size == 0:
                raise FormatError("empty SQTPP file")
            self._mapped = mmap.mmap(self._stream.fileno(), 0, access=mmap.ACCESS_READ)
            self._closed = False
            self._locks: dict[str, list[str]] | None = None
            self._histories: dict[str, list[str]] | None = None
            self._lazy_lock = threading.RLock()
            self._digest: str | None = None
            self._variables: dict[str, int] | None = None
            self._variable_order: list[str] | None = None
            self.name_starts = array("Q")
            self.name_lengths = array("I")
            self.name_hashes = array("I")
            self.payload_starts = array("Q")
            self.payload_ends = array("Q")
            self.opaque_records = 0
            self._entry_count = 0
            self._physical_offset = 0
            self._hash_offset = 0
            self._names_offset = 0
            self._names_end = 0
            self._physical_struct = _SQTI_PHYSICAL64
            self.index_source = "scan"
            self._open_index()
            self.index_weight = self._estimate_index_weight()
        except Exception:
            self._close_resources()
            raise

    @property
    def size(self) -> int:
        return self._stat.st_size

    @property
    def identity_key(self) -> tuple[int, int, int, int]:
        return (self._stat.st_dev, self._stat.st_ino, self._stat.st_size, self._stat.st_mtime_ns)

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def revision_id(self) -> str:
        device, inode, size, mtime_ns = self.identity_key
        return f"{device:x}-{inode:x}-{size:x}-{mtime_ns:x}"

    @property
    def variable_count(self) -> int:
        return self._entry_count

    @property
    def variables(self) -> dict[str, int]:
        """First-scan name map retained for compatibility with internal tests.

        Sidecar-backed snapshots intentionally do not materialize this map.
        Public engine code uses ``contains`` and ``span`` instead.
        """
        return self._variables or {}

    @property
    def variable_order(self) -> list[str]:
        return self.list_names()

    def list_names(self) -> list[str]:
        if self._variable_order is not None:
            return list(self._variable_order)
        if self._entry_count == 0:
            return []
        try:
            compressed = self._index_mapped[self._names_offset:self._names_end]
            raw = zlib.decompress(compressed)
            names = raw.decode("ascii").split("\n")
        except (zlib.error, UnicodeDecodeError) as exc:
            raise FormatError("invalid compressed SQTI name table") from exc
        if len(names) != self._entry_count or any(not name for name in names):
            raise FormatError("SQTI name table count does not match record count")
        return names

    def iter_names(self) -> Iterator[str]:
        yield from self.list_names()

    def _estimate_index_weight(self) -> int:
        if self.index_source == "sidecar":
            # Both files are mmap-backed; only a handful of Python objects are
            # retained regardless of record count.
            return 4096
        order = self._variable_order or []
        names_weight = sum(64 + len(name) for name in order)
        numeric_weight = sum(
            offsets.buffer_info()[1] * offsets.itemsize
            for offsets in (
                self.name_starts, self.name_lengths, self.name_hashes,
                self.payload_starts, self.payload_ends,
            )
        )
        return 1024 + names_weight + numeric_weight + len(self._variables or {}) * 44

    def _validate_file_header_and_path(self) -> None:
        mapped = self._mapped
        if mapped[: len(_HEADER)] != _HEADER:
            raise FormatError("not a supported SQTPP Staqtapp 1.x file")
        dir_marker = f"|:{self.directory}<{self.folder}>".encode("utf-8")
        head_end = min(len(mapped), 1024 * 1024)
        if mapped.find(dir_marker, 0, head_end) < 0 and mapped.find(dir_marker) < 0:
            raise InvalidPathError("directory/folder hierarchy not found")

    def _open_index(self) -> None:
        self._validate_file_header_and_path()
        if self._load_sidecar():
            self.index_source = "sidecar"
            return
        self._scan_structure()
        self.index_source = "scan"
        self._write_sidecar()

    def _find_block(self, marker: bytes, closing: bytes) -> tuple[int, int, int]:
        marker_start = self._mapped.find(marker)
        if marker_start < 0:
            raise InvalidPathError(f"missing SQTPP marker: {marker.decode('utf-8', 'replace')}")
        line_end = self._mapped.find(b"\n", marker_start)
        if line_end < 0:
            raise FormatError("unterminated SQTPP marker line")
        body_start = line_end + 1
        close_start = self._mapped.find(closing, body_start)
        if close_start < 0:
            raise FormatError(f"missing SQTPP closing marker: {closing.decode('utf-8', 'replace')}")
        if close_start == 0 or self._mapped[close_start - 1] != 0x3A:
            raise FormatError("SQTPP body does not end with ':'")
        return marker_start, body_start, close_start

    def _scan_structure(self) -> None:
        mapped = self._mapped
        tqpt_marker = f"___|:tqpt-{self.folder}<".encode("utf-8")
        tqpt_closing = f"\n___|:(tqpt-{self.folder})".encode("utf-8")
        tpqt_marker = f"___|:tpqt-{self.folder}<".encode("utf-8")
        tpqt_closing = f"\n___|:(tpqt-{self.folder})".encode("utf-8")
        self.tqpt_marker_start, self.tqpt_body_start, self.tqpt_body_end = self._find_block(
            tqpt_marker, tqpt_closing
        )
        _, self.tpqt_body_start, self.tpqt_body_end = self._find_block(tpqt_marker, tpqt_closing)

        history_marker = f"<sbf-{self.folder}-svvs:\n".encode("utf-8")
        history_start = mapped.find(history_marker)
        if history_start < 0:
            self.history_span = None
        else:
            history_end = mapped.find(b"//>", history_start + len(history_marker))
            if history_end < 0:
                raise FormatError("unterminated stalk history block")
            self.history_span = (history_start, history_end + 3)
        self._scan_variables()

    def _scan_variables(self) -> None:
        mapped = self._mapped
        start = self.tqpt_body_start
        end = self.tqpt_body_end
        if end <= start or mapped[end - 1] != 0x3A:
            raise FormatError("TQPT body missing terminator")
        content_end = end - 1
        first_end = mapped.find(b"\n", start, content_end)
        if first_end < 0:
            first_end = content_end
        if mapped[start:first_end] != b"null":
            raise FormatError("TQPT body must start with null")

        records_start = first_end + 1 if first_end < content_end else content_end
        variables: dict[str, int] = {}
        order: list[str] = []
        self._variables = variables
        self._variable_order = order

        append_name_start = self.name_starts.append
        append_name_length = self.name_lengths.append
        append_name_hash = self.name_hashes.append
        append_payload_start = self.payload_starts.append
        append_payload_end = self.payload_ends.append

        valid_count = 0
        opaque_count = 0
        expected_start = records_start
        for match in _VALID_RECORD.finditer(mapped, records_start, content_end):
            if match.start(0) != expected_start:
                opaque_count += sum(
                    1 for _ in _NONEMPTY_LINE.finditer(mapped, expected_start, match.start(0))
                )
            name_start, name_end = match.span(1)
            name_raw = mapped[name_start:name_end]
            name = name_raw.decode("ascii")
            if name in variables:
                raise CorruptRecordError(f"duplicate variable record: {name}")
            slot = valid_count
            valid_count += 1
            variables[name] = slot
            order.append(name)
            append_name_start(name_start)
            append_name_length(name_end - name_start)
            append_name_hash(_stable_name_hash(name_raw))
            payload_start, payload_end = match.span(2)
            append_payload_start(payload_start)
            append_payload_end(payload_end)
            expected_start = match.end(0)
            if expected_start < content_end and mapped[expected_start] == 0x0A:
                expected_start += 1

        if expected_start < content_end:
            opaque_count += sum(
                1 for _ in _NONEMPTY_LINE.finditer(mapped, expected_start, content_end)
            )
        self._entry_count = valid_count
        self.opaque_records = opaque_count

    def _sidecar_identity_matches(self, fields: tuple[int, ...]) -> bool:
        return tuple(fields) == self.identity_key

    def _load_sidecar(self) -> bool:
        index_path = sidecar_path(self.path)
        stream = None
        index_map = None
        try:
            stream = index_path.open("rb")
            stat = os.fstat(stream.fileno())
            if stat.st_size < _SQTI_HEADER.size + _SQTI_DIGEST_SIZE:
                return False
            index_map = mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ)
            payload_end = len(index_map) - _SQTI_DIGEST_SIZE
            payload_view = memoryview(index_map)[:payload_end]
            try:
                actual_digest = hashlib.sha256(payload_view).digest()
            finally:
                payload_view.release()
            if actual_digest != index_map[payload_end:]:
                return False
            header = _SQTI_HEADER.unpack_from(index_map, 0)
            (
                magic, version, flags,
                device, inode, size, mtime_ns,
                tqpt_marker_start, tqpt_body_start, tqpt_body_end,
                tpqt_body_start, tpqt_body_end,
                history_start, history_end, opaque_records,
                record_count, directory_len, folder_len,
            ) = header
            if magic != _SQTI_MAGIC or version != _SQTI_VERSION:
                return False
            if flags & ~_SQTI_FLAG_OFFSETS_64:
                return False
            physical_struct = _SQTI_PHYSICAL64 if flags & _SQTI_FLAG_OFFSETS_64 else _SQTI_PHYSICAL32
            if not self._sidecar_identity_matches((device, inode, size, mtime_ns)):
                return False
            metadata_start = _SQTI_HEADER.size
            physical_offset = metadata_start + directory_len + folder_len
            hash_offset = physical_offset + record_count * physical_struct.size
            names_offset = hash_offset + record_count * _SQTI_HASH.size
            if names_offset > payload_end:
                return False
            if record_count and names_offset == payload_end:
                return False
            directory = index_map[metadata_start:metadata_start + directory_len].decode("utf-8")
            folder_start = metadata_start + directory_len
            folder = index_map[folder_start:folder_start + folder_len].decode("utf-8")
            if directory != self.directory or folder != self.folder:
                return False
            if not self._valid_structure_spans(
                tqpt_marker_start, tqpt_body_start, tqpt_body_end,
                tpqt_body_start, tpqt_body_end, history_start, history_end,
            ):
                return False

            self.tqpt_marker_start = tqpt_marker_start
            self.tqpt_body_start = tqpt_body_start
            self.tqpt_body_end = tqpt_body_end
            self.tpqt_body_start = tpqt_body_start
            self.tpqt_body_end = tpqt_body_end
            self.history_span = None if history_start < 0 else (history_start, history_end)
            self.opaque_records = opaque_records
            self._entry_count = record_count
            self._physical_offset = physical_offset
            self._hash_offset = hash_offset
            self._names_offset = names_offset
            self._names_end = payload_end
            self._physical_struct = physical_struct
            self._index_stream = stream
            self._index_mapped = index_map
            stream = None
            index_map = None
            return True
        except (OSError, UnicodeError, struct.error, ValueError, OverflowError):
            return False
        finally:
            if index_map is not None:
                index_map.close()
            if stream is not None:
                stream.close()

    def _valid_structure_spans(
        self,
        tqpt_marker_start: int,
        tqpt_body_start: int,
        tqpt_body_end: int,
        tpqt_body_start: int,
        tpqt_body_end: int,
        history_start: int,
        history_end: int,
    ) -> bool:
        size = self.size
        if not (0 <= tqpt_marker_start < tqpt_body_start < tqpt_body_end <= size):
            return False
        if not (0 <= tpqt_body_start < tpqt_body_end <= size):
            return False
        if self._mapped[tqpt_body_end - 1] != 0x3A or self._mapped[tpqt_body_end - 1] != 0x3A:
            return False
        if history_start < 0 or history_end < 0:
            return history_start == -1 and history_end == -1
        return 0 <= history_start < history_end <= size

    def _write_sidecar(self) -> None:
        index_path = sidecar_path(self.path)
        directory_raw = self.directory.encode("utf-8")
        folder_raw = self.folder.encode("utf-8")
        history_start, history_end = self.history_span if self.history_span is not None else (-1, -1)
        physical_struct = _SQTI_PHYSICAL32 if self.size <= 0xFFFFFFFF else _SQTI_PHYSICAL64
        flags = 0 if physical_struct is _SQTI_PHYSICAL32 else _SQTI_FLAG_OFFSETS_64
        header = _SQTI_HEADER.pack(
            _SQTI_MAGIC,
            _SQTI_VERSION,
            flags,
            self._stat.st_dev,
            self._stat.st_ino,
            self._stat.st_size,
            self._stat.st_mtime_ns,
            self.tqpt_marker_start,
            self.tqpt_body_start,
            self.tqpt_body_end,
            self.tpqt_body_start,
            self.tpqt_body_end,
            history_start,
            history_end,
            self.opaque_records,
            self._entry_count,
            len(directory_raw),
            len(folder_raw),
        )
        if self._entry_count > 0xFFFFFFFF:
            return
        hash_slots = sorted((self.name_hashes[slot], slot) for slot in range(self._entry_count))
        fd = None
        tmp = None
        try:
            index_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=f".{index_path.name}.", suffix=".tmp", dir=index_path.parent)
            digest = hashlib.sha256()
            with os.fdopen(fd, "wb") as stream:
                fd = None
                for chunk in (header, directory_raw, folder_raw):
                    stream.write(chunk)
                    digest.update(chunk)
                for slot in range(self._entry_count):
                    entry = physical_struct.pack(
                        self.name_starts[slot],
                        self.name_lengths[slot],
                        self.payload_starts[slot],
                        self.payload_ends[slot],
                    )
                    stream.write(entry)
                    digest.update(entry)
                for name_hash, slot in hash_slots:
                    entry = _SQTI_HASH.pack(name_hash, slot)
                    stream.write(entry)
                    digest.update(entry)
                names_blob = "\n".join(self._variable_order or ()).encode("ascii")
                compressed_names = zlib.compress(names_blob, level=1) if names_blob else b""
                stream.write(compressed_names)
                digest.update(compressed_names)
                stream.write(digest.digest())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, index_path)
            tmp = None
        except OSError:
            pass
        finally:
            if fd is not None:
                os.close(fd)
            if tmp is not None:
                try:
                    os.unlink(tmp)
                except FileNotFoundError:
                    pass

    def _physical(self, slot: int) -> tuple[int, int, int, int]:
        if not 0 <= slot < self._entry_count:
            raise FormatError("SQTI physical slot is out of range")
        if self.index_source == "sidecar":
            return self._physical_struct.unpack_from(
                self._index_mapped,
                self._physical_offset + slot * self._physical_struct.size,
            )
        return (
            self.name_starts[slot],
            self.name_lengths[slot],
            self.payload_starts[slot],
            self.payload_ends[slot],
        )

    def _hash_entry(self, index: int) -> tuple[int, int]:
        return _SQTI_HASH.unpack_from(
            self._index_mapped,
            self._hash_offset + index * _SQTI_HASH.size,
        )

    def _lookup_slot(self, name: str) -> int:
        if self._variables is not None:
            try:
                return self._variables[name]
            except KeyError as exc:
                raise VariableNotFoundError(f"variable not found: {name}") from exc

        raw = name.encode("ascii")
        target = _stable_name_hash(raw)
        lo = 0
        hi = self._entry_count
        while lo < hi:
            mid = (lo + hi) // 2
            value, _ = self._hash_entry(mid)
            if value < target:
                lo = mid + 1
            else:
                hi = mid
        while lo < self._entry_count:
            value, slot = self._hash_entry(lo)
            if value != target:
                break
            name_start, name_length, payload_start, payload_end = self._physical(slot)
            record_start = name_start
            record_end = payload_end + 1
            if not (0 <= record_start <= name_start < name_start + name_length < payload_start <= payload_end < record_end <= self.size):
                raise FormatError("SQTI record span is invalid")
            if name_length == len(raw) and self._mapped[name_start:name_start + name_length] == raw:
                if self._mapped[payload_start - 1] != 0x3C or self._mapped[payload_end] != 0x3E:
                    raise FormatError("SQTI payload delimiters are invalid")
                return slot
            lo += 1
        raise VariableNotFoundError(f"variable not found: {name}")

    def contains(self, name: str) -> bool:
        try:
            self._lookup_slot(name)
            return True
        except VariableNotFoundError:
            return False

    def span(self, name: str) -> VariableSpan:
        slot = self._lookup_slot(name)
        name_start, _, payload_start, payload_end = self._physical(slot)
        return VariableSpan(name, name_start, payload_end + 1, payload_start, payload_end)

    def payload_length(self, name: str) -> int:
        slot = self._lookup_slot(name)
        _, _, payload_start, payload_end = self._physical(slot)
        return payload_end - payload_start

    def payload_bytes(self, name: str) -> bytes:
        slot = self._lookup_slot(name)
        _, _, payload_start, payload_end = self._physical(slot)
        return self._mapped[payload_start:payload_end]

    def payload_slice(self, name: str, start: int = 0, length: int | None = None) -> bytes:
        """Return a bounded slice directly from the mmap-backed payload.

        This path never materializes bytes outside the requested range.
        """
        if type(start) is not int or start < 0:
            raise ValueError("start must be a non-negative integer")
        if length is not None and (type(length) is not int or length < 0):
            raise ValueError("length must be None or a non-negative integer")
        slot = self._lookup_slot(name)
        _, _, payload_start, payload_end = self._physical(slot)
        payload_length = payload_end - payload_start
        if start > payload_length:
            raise ValueError("start exceeds payload size")
        stop = payload_length if length is None else min(payload_length, start + length)
        return self._mapped[payload_start + start:payload_start + stop]

    def index_info(self) -> dict[str, object]:
        index = sidecar_path(self.path)
        return {
            "path": str(index),
            "exists": index.is_file(),
            "source": self.index_source,
            "variables": self.variable_count,
            "vfs_revision": self.revision_id,
            "vfs_size": self.size,
            "index_size": index.stat().st_size if index.is_file() else 0,
            "memory_weight_estimate": self.index_weight,
            "format_version": _SQTI_VERSION,
        }

    def payload_contains(self, name: str, needle: bytes) -> bool:
        slot = self._lookup_slot(name)
        _, _, payload_start, payload_end = self._physical(slot)
        return self._mapped.find(needle, payload_start, payload_end) >= 0

    def payload_startswith(self, name: str, prefix: bytes) -> bool:
        slot = self._lookup_slot(name)
        _, _, start, end = self._physical(slot)
        return end - start >= len(prefix) and self._mapped[start:start + len(prefix)] == prefix

    def payload_equal(self, left_name: str, right_name: str) -> bool:
        left = self._lookup_slot(left_name)
        right = self._lookup_slot(right_name)
        _, _, left_start, left_end = self._physical(left)
        _, _, right_start, right_end = self._physical(right)
        if left_end - left_start != right_end - right_start:
            return False
        left_view = memoryview(self._mapped)[left_start:left_end]
        right_view = memoryview(self._mapped)[right_start:right_end]
        try:
            return left_view == right_view
        finally:
            left_view.release()
            right_view.release()

    @property
    def locks(self) -> dict[str, list[str]]:
        if self._locks is None:
            with self._lazy_lock:
                if self._locks is None:
                    self._locks = self._parse_locks()
        return self._locks

    def _parse_locks(self) -> dict[str, list[str]]:
        body = self._mapped[self.tpqt_body_start:self.tpqt_body_end]
        if not body.endswith(b":"):
            raise FormatError("TPQT body missing terminator")
        content = body[:-1]
        if content == b"null":
            return {}
        if content.startswith(b"null\n"):
            content = content[5:]
        locks: dict[str, list[str]] = {}
        pos = 0
        while pos < len(content):
            while pos < len(content) and content[pos:pos + 1] in (b"\n", b"\r"):
                pos += 1
            if pos >= len(content):
                break
            match = _LOCK_RECORD.match(content, pos)
            if not match:
                raise CorruptRecordError(f"invalid TPQT record at byte {pos}")
            name = match.group(1).decode("ascii")
            values = [line.decode("utf-8") for line in match.group(2).split(b"\n") if line]
            if name in locks:
                raise CorruptRecordError(f"duplicate lock record: {name}")
            locks[name] = values
            pos = match.end()
        return locks

    @property
    def histories(self) -> dict[str, list[str]]:
        if self._histories is None:
            with self._lazy_lock:
                if self._histories is None:
                    self._histories = self._parse_histories()
        return self._histories

    def _parse_histories(self) -> dict[str, list[str]]:
        if self.history_span is None:
            return {}
        start_marker = f"<sbf-{self.folder}-svvs:\n".encode("utf-8")
        start, end = self.history_span
        raw = self._mapped[start + len(start_marker):end - 3]
        histories: dict[str, list[str]] = {}
        for match in _HISTORY_RECORD.finditer(raw):
            name = match.group(1).decode("ascii")
            histories[name] = [v.decode("ascii") for v in match.group(2).split(b",") if v]
        return histories

    def sha256(self) -> str:
        digest = self._digest
        if digest is None:
            digest = hashlib.sha256(self._mapped).hexdigest()
            self._digest = digest
        return digest

    def _close_resources(self) -> None:
        index_mapped = getattr(self, "_index_mapped", None)
        index_stream = getattr(self, "_index_stream", None)
        mapped = getattr(self, "_mapped", None)
        stream = getattr(self, "_stream", None)
        if index_mapped is not None:
            index_mapped.close()
            self._index_mapped = None
        if index_stream is not None:
            index_stream.close()
            self._index_stream = None
        if mapped is not None:
            mapped.close()
        if stream is not None:
            stream.close()

    def close(self) -> None:
        if getattr(self, "_closed", True):
            return
        self._closed = True
        self._close_resources()

    def __enter__(self) -> "MappedVFS":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
