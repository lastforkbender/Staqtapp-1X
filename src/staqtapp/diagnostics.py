from __future__ import annotations

import threading
import time
from collections import Counter, deque
from dataclasses import dataclass
from typing import Any

@dataclass(slots=True, frozen=True)
class DiagnosticEvent:
    timestamp_ns: int
    name: str
    fields: tuple[tuple[str, Any], ...]

_EVENTS: deque[DiagnosticEvent] = deque(maxlen=1024)
_COUNTS: Counter[str] = Counter()
_LOCK = threading.Lock()

def emit(name: str, **fields: Any) -> None:
    event = DiagnosticEvent(time.time_ns(), name, tuple(sorted(fields.items())))
    with _LOCK:
        _EVENTS.append(event)
        _COUNTS[name] += 1

def recent_events(limit: int = 100) -> list[DiagnosticEvent]:
    if limit < 0:
        raise ValueError("limit must be non-negative")
    with _LOCK:
        return list(_EVENTS)[-limit:]

def diagnostic_counts() -> dict[str, int]:
    with _LOCK:
        return dict(_COUNTS)
