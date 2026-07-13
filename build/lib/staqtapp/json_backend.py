from __future__ import annotations

import contextvars
import json
from dataclasses import dataclass
from typing import Any, Literal

from .errors import InvalidValueError

BackendChoice = Literal["auto", "orjson", "stdlib"]
_choice: contextvars.ContextVar[BackendChoice] = contextvars.ContextVar("staqtapp_json_backend", default="auto")

try:
    import orjson as _orjson
except Exception:
    _orjson = None


def _stdlib_dumps(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _stdlib_loads(payload: bytes) -> Any:
    return json.loads(payload.decode("utf-8"))


def _orjson_dumps(value: Any) -> bytes:
    if _orjson is None:
        raise InvalidValueError("orjson backend is unavailable; install staqtapp[fastjson]")
    return _orjson.dumps(value, option=_orjson.OPT_SORT_KEYS)


def _orjson_loads(payload: bytes) -> Any:
    if _orjson is None:
        raise InvalidValueError("orjson backend is unavailable; install staqtapp[fastjson]")
    return _orjson.loads(payload)

_EQUIVALENCE_CORPUS = (
    None, True, False, 0, 1, -1, "", "ascii", "Zażółć gęślą jaźń", "\u0000\n\t\\\"",
    [], {}, [1, "two", False, None],
    {"codec": "staqt-json-v1", "value": {"t": "dict", "v": [[{"t":"str","v":"β"},{"t":"int","v":"12345678901234567890"}]]}},
)


def _verify_orjson() -> tuple[bool, str | None]:
    if _orjson is None:
        return False, "not installed"
    try:
        for value in _EQUIVALENCE_CORPUS:
            reference = _stdlib_dumps(value)
            accelerated = _orjson_dumps(value)
            if accelerated != reference:
                return False, "canonical byte mismatch"
            if _orjson_loads(reference) != _stdlib_loads(reference):
                return False, "decode mismatch"
        return True, None
    except Exception as exc:
        return False, f"verification failed: {type(exc).__name__}: {exc}"

_ORJSON_VERIFIED, _ORJSON_REASON = _verify_orjson()


def set_backend(choice: str) -> str:
    normalized = str(choice).lower()
    if normalized not in {"auto", "orjson", "stdlib"}:
        raise InvalidValueError("json_backend must be 'auto', 'orjson', or 'stdlib'")
    if normalized == "orjson" and not _ORJSON_VERIFIED:
        raise InvalidValueError(f"orjson backend cannot be activated: {_ORJSON_REASON}")
    _choice.set(normalized)  # type: ignore[arg-type]
    return active_backend()


def requested_backend() -> str:
    return _choice.get()


def active_backend() -> str:
    choice = _choice.get()
    if choice == "stdlib":
        return "stdlib"
    if choice == "orjson":
        return "orjson"
    return "orjson" if _ORJSON_VERIFIED else "stdlib"


def dumps_canonical(value: Any) -> bytes:
    if active_backend() == "orjson":
        try:
            result = _orjson_dumps(value)
        except Exception:
            if requested_backend() == "orjson":
                raise
            result = _stdlib_dumps(value)
        reference = _stdlib_dumps(value)
        if result != reference:
            if requested_backend() == "orjson":
                raise InvalidValueError("orjson produced noncanonical bytes")
            return reference
        return result
    return _stdlib_dumps(value)


def loads_strict(payload: bytes) -> Any:
    if active_backend() == "orjson":
        try:
            return _orjson_loads(payload)
        except Exception:
            if requested_backend() == "orjson":
                raise
    return _stdlib_loads(payload)


def backend_info() -> dict[str, Any]:
    return {
        "requested": requested_backend(),
        "active": active_backend(),
        "accelerated": active_backend() == "orjson",
        "format": "staqt-json-v1",
        "orjson_installed": _orjson is not None,
        "canonical_equivalence_verified": _ORJSON_VERIFIED,
        "fallback": "stdlib",
        "verification_reason": _ORJSON_REASON,
        "orjson_version": getattr(_orjson, "__version__", None),
    }
