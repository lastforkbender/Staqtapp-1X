from __future__ import annotations

import mmap
import re
from pathlib import Path

from .errors import CorruptRecordError, FormatError, InvalidPathError
from .model import OpaqueRecord, VariableRecord, VFSImage
from .transaction import MutationPlan, plan_from_replacements

_NAME = re.compile(rb"^[A-Za-z_][A-Za-z0-9_]*$")
_HEADER = b":\xe2\x98\x86Staqtapp-v1."


def _find_block(source: bytes, marker: bytes, closing: bytes) -> tuple[int, int, int]:
    marker_start = source.find(marker)
    if marker_start < 0:
        raise InvalidPathError(f"missing SQTPP marker: {marker.decode('utf-8', 'replace')}")
    line_end = source.find(b"\n", marker_start)
    if line_end < 0:
        raise FormatError("unterminated SQTPP marker line")
    body_start = line_end + 1
    close_start = source.find(closing, body_start)
    if close_start < 0:
        raise FormatError(f"missing SQTPP closing marker: {closing.decode('utf-8', 'replace')}")
    if close_start == 0 or source[close_start - 1:close_start] != b":":
        raise FormatError("SQTPP body does not end with ':'")
    return marker_start, body_start, close_start


def _parse_variables(body: bytes) -> list[VariableRecord | OpaqueRecord]:
    if not body.endswith(b":"):
        raise FormatError("TQPT body missing terminator")
    content = body[:-1]
    lines = content.split(b"\n")
    if not lines or lines[0] != b"null":
        raise FormatError("TQPT body must start with null")
    records: list[VariableRecord | OpaqueRecord] = []
    seen: set[str] = set()
    for raw in lines[1:]:
        if not raw:
            continue
        left = raw.find(b"<")
        if left < 1 or not raw.endswith(b">"):
            records.append(OpaqueRecord(raw)); continue
        name_raw = raw[:left]
        if not _NAME.fullmatch(name_raw):
            records.append(OpaqueRecord(raw)); continue
        name = name_raw.decode("ascii")
        if name in seen:
            raise CorruptRecordError(f"duplicate variable record: {name}")
        seen.add(name)
        records.append(VariableRecord(name, raw[left + 1:-1]))
    return records


def _parse_locks(body: bytes) -> dict[str, list[str]]:
    if not body.endswith(b":"):
        raise FormatError("TPQT body missing terminator")
    content = body[:-1]
    if content == b"null":
        return {}
    if content.startswith(b"null\n"):
        content = content[5:]
    locks: dict[str, list[str]] = {}
    pos = 0
    pattern = re.compile(rb"<:([A-Za-z_][A-Za-z0-9_]*)=\n(.*?):>", re.DOTALL)
    while pos < len(content):
        while pos < len(content) and content[pos:pos+1] in (b"\n", b"\r"):
            pos += 1
        if pos >= len(content):
            break
        match = pattern.match(content, pos)
        if not match:
            raise CorruptRecordError(f"invalid TPQT record at byte {pos}")
        name = match.group(1).decode("ascii")
        values = [line.decode("utf-8") for line in match.group(2).split(b"\n") if line]
        if name in locks:
            raise CorruptRecordError(f"duplicate lock record: {name}")
        locks[name] = values
        pos = match.end()
    return locks


def _parse_histories(source: bytes, folder: str) -> tuple[dict[str, list[str]], tuple[int, int] | None]:
    start_marker = f"<sbf-{folder}-svvs:\n".encode("utf-8")
    start = source.find(start_marker)
    if start < 0:
        return {}, None
    end = source.find(b"//>", start + len(start_marker))
    if end < 0:
        raise FormatError("unterminated stalk history block")
    end += 3
    raw = source[start + len(start_marker):end - 3]
    histories: dict[str, list[str]] = {}
    for match in re.finditer(rb"\(([A-Za-z_][A-Za-z0-9_]*)=([^)]*)\)", raw):
        name = match.group(1).decode("ascii")
        values = [v.decode("ascii") for v in match.group(2).split(b",") if v]
        histories[name] = values
    return histories, (start, end)


def parse_vfs_source(path: str | Path, source, directory: str, folder: str) -> VFSImage:
    path = Path(path)
    if not hasattr(source, "find") or not hasattr(source, "__getitem__"):
        raise TypeError("SQTPP source must be a bytes-like random-access object")
    if source[:len(_HEADER)] != _HEADER:
        raise FormatError("not a supported SQTPP Staqtapp 1.x file")
    dir_marker = f"|:{directory}<{folder}>".encode("utf-8")
    if source.find(dir_marker) < 0:
        raise InvalidPathError("directory/folder hierarchy not found")
    tqpt_marker = f"___|:tqpt-{folder}<".encode("utf-8")
    tqpt_closing = f"\n___|:(tqpt-{folder})".encode("utf-8")
    tpqt_marker = f"___|:tpqt-{folder}<".encode("utf-8")
    tpqt_closing = f"\n___|:(tpqt-{folder})".encode("utf-8")
    tqpt_marker_start, tqpt_body_start, tqpt_body_end = _find_block(source, tqpt_marker, tqpt_closing)
    _, tpqt_body_start, tpqt_body_end = _find_block(source, tpqt_marker, tpqt_closing)
    histories, history_span = _parse_histories(source, folder)
    return VFSImage(
        path=path,
        directory=directory,
        folder=folder,
        source=source,
        tqpt_body_start=tqpt_body_start,
        tqpt_body_end=tqpt_body_end,
        tpqt_body_start=tpqt_body_start,
        tpqt_body_end=tpqt_body_end,
        tqpt_marker_start=tqpt_marker_start,
        records=_parse_variables(source[tqpt_body_start:tqpt_body_end]),
        locks=_parse_locks(source[tpqt_body_start:tpqt_body_end]),
        histories=histories,
        history_span=history_span,
    )


def parse_vfs(path: str | Path, directory: str, folder: str) -> VFSImage:
    path = Path(path)
    with path.open("rb") as stream:
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
            source = mapped[:]
    return parse_vfs_source(path, source, directory, folder)



def serialize_mutation_plan(image: VFSImage) -> MutationPlan:
    """Return an ordered streaming plan without assembling destination bytes."""
    tqpt_lines = [b"null"]
    for record in image.records:
        if isinstance(record, VariableRecord):
            tqpt_lines.append(record.name.encode("ascii") + b"<" + record.payload + b">")
        else:
            tqpt_lines.append(record.raw)
    tqpt = b"\n".join(tqpt_lines) + b":"

    if image.locks:
        chunks = []
        for name, values in image.locks.items():
            safe = [v for v in values if v]
            chunks.append(b"<:" + name.encode("ascii") + b"=\n" + b"\n".join(v.encode("utf-8") for v in safe) + b":>")
        tpqt = b"\n".join(chunks) + b":"
    else:
        tpqt = b"null:"

    replacements = [
        (image.tqpt_body_start, image.tqpt_body_end, tqpt),
        (image.tpqt_body_start, image.tpqt_body_end, tpqt),
    ]
    source_size = len(image.source)
    if image.histories:
        entries = [f"({name}={','.join(values)})" for name, values in image.histories.items()]
        history = f"<sbf-{image.folder}-svvs:\n{';'.join(entries)}//>".encode("utf-8")
        if image.history_span:
            replacements.append((image.history_span[0], image.history_span[1], history))
        else:
            replacements.append((image.tqpt_marker_start, image.tqpt_marker_start, history + b"\n"))
    elif image.history_span:
        start, end = image.history_span
        if end < source_size and image.source[end:end+1] == b"\n":
            end += 1
        replacements.append((start, end, b""))
    return plan_from_replacements(source_size, replacements)

def serialize_vfs(image: VFSImage) -> bytes:
    tqpt_lines = [b"null"]
    for record in image.records:
        if isinstance(record, VariableRecord):
            tqpt_lines.append(record.name.encode("ascii") + b"<" + record.payload + b">")
        else:
            tqpt_lines.append(record.raw)
    tqpt = b"\n".join(tqpt_lines) + b":"

    if image.locks:
        chunks = []
        for name, values in image.locks.items():
            safe = [v for v in values if v]
            chunks.append(b"<:" + name.encode("ascii") + b"=\n" + b"\n".join(v.encode("utf-8") for v in safe) + b":>")
        tpqt = b"\n".join(chunks) + b":"
    else:
        tpqt = b"null:"

    source = image.source
    replacements: list[tuple[int, int, bytes]] = [
        (image.tqpt_body_start, image.tqpt_body_end, tqpt),
        (image.tpqt_body_start, image.tpqt_body_end, tpqt),
    ]
    if image.histories:
        entries = []
        for name, values in image.histories.items():
            entries.append(f"({name}={','.join(values)})")
        history = f"<sbf-{image.folder}-svvs:\n{';'.join(entries)}//>".encode("utf-8")
        if image.history_span:
            replacements.append((image.history_span[0], image.history_span[1], history))
        else:
            replacements.append((image.tqpt_marker_start, image.tqpt_marker_start, history + b"\n"))
    elif image.history_span:
        start, end = image.history_span
        if end < len(source) and source[end:end+1] == b"\n":
            end += 1
        replacements.append((start, end, b""))

    # Assemble once in physical order. Repeated reverse slicing created a new
    # full-file bytes object for every replaced section. A single bytearray
    # keeps write-path peak memory and copy count bounded to one destination.
    ordered = sorted(replacements, key=lambda item: item[0])
    output = bytearray()
    cursor = 0
    for start, end, data in ordered:
        if start < cursor:
            raise FormatError("overlapping SQTPP serialization replacements")
        output.extend(source[cursor:start])
        output.extend(data)
        cursor = end
    output.extend(source[cursor:])
    return bytes(output)
