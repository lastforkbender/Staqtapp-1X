from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Union


@dataclass(slots=True, frozen=True)
class FileIdentity:
    device: int
    inode: int
    size: int
    mtime_ns: int
    digest: str


@dataclass(slots=True)
class VariableRecord:
    name: str
    payload: bytes


@dataclass(slots=True)
class OpaqueRecord:
    raw: bytes


Record = Union[VariableRecord, OpaqueRecord]


@dataclass(slots=True)
class VFSImage:
    """Mutable transaction image used only on the write/migration path."""

    path: Path
    directory: str
    folder: str
    source: bytes
    tqpt_body_start: int
    tqpt_body_end: int
    tpqt_body_start: int
    tpqt_body_end: int
    tqpt_marker_start: int
    records: list[Record] = field(default_factory=list)
    locks: dict[str, list[str]] = field(default_factory=dict)
    histories: dict[str, list[str]] = field(default_factory=dict)
    history_span: tuple[int, int] | None = None
    _variables: dict[str, VariableRecord] | None = field(default=None, init=False, repr=False)

    def variable_map(self) -> dict[str, VariableRecord]:
        index = self._variables
        if index is None:
            index = {record.name: record for record in self.records if isinstance(record, VariableRecord)}
            self._variables = index
        return index

    def invalidate_variable_map(self) -> None:
        self._variables = None
