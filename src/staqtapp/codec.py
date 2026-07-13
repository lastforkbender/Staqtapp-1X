from __future__ import annotations

import base64
import builtins
import copyreg
import io
import pickle
import re
from collections import deque
from decimal import Decimal
from typing import Any

from .errors import InvalidValueError, UnsafeLegacyContentError

_QP = re.compile(r"@qp\((.*?)\):", re.DOTALL)
_QV1 = re.compile(r"@qv1\(([A-Za-z0-9_-]*)\):")

class _RestrictedUnpickler(pickle.Unpickler):
    _SAFE = {"bool", "bytes", "complex", "dict", "float", "frozenset", "int", "list", "object", "set", "str", "tuple"}
    def find_class(self, module: str, name: str):
        if module in {"builtins", "__builtin__"} and name in self._SAFE:
            return getattr(builtins, name)
        if module in {"copyreg", "copy_reg"} and name == "_reconstructor":
            return copyreg._reconstructor
        if module == "collections" and name == "deque":
            return deque
        raise pickle.UnpicklingError(f"global {module}.{name} is not allowed")

def restricted_loads(payload: bytes) -> Any:
    try:
        return _RestrictedUnpickler(io.BytesIO(payload)).load()
    except Exception as exc:
        raise UnsafeLegacyContentError("legacy pickle payload is not in the safe allow-list") from exc

def encode_text(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    if "\n" not in value and "):" not in value:
        return f"@qp({value}):"
    data = base64.urlsafe_b64encode(value.encode("utf-8")).rstrip(b"=").decode("ascii")
    return f"@qv1({data}):"

def normalize_payload(value: str) -> bytes:
    if not isinstance(value, str):
        raise TypeError("variable data must be a string")
    if value.startswith("@qp(") or value.startswith("@qv1(") or value.startswith("@q*p("):
        decode_payload(value.encode("utf-8"), all_numbers=False)
        return value.encode("utf-8")
    return encode_text(value).encode("utf-8")

def _number(value: str):
    stripped = value.strip()
    if not stripped:
        raise InvalidValueError("empty value is not numeric")
    try:
        if any(c in stripped.lower() for c in (".", "e")):
            return Decimal(stripped)
        return int(stripped)
    except Exception as exc:
        raise InvalidValueError(f"value is not numeric: {value!r}") from exc

def decode_payload(payload: bytes, *, all_numbers: bool) -> list[Any]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidValueError("payload is not valid UTF-8") from exc
    if text.startswith("@q*p("):
        raise InvalidValueError("core variable payload must be read with corevar")
    values: list[Any] = []
    position = 0
    while position < len(text):
        qp = _QP.match(text, position)
        if qp:
            raw = qp.group(1)
            parts = raw.split(",") if "," in raw else [raw]
            for part in parts:
                if all_numbers:
                    values.append(_number(part))
                else:
                    try: values.append(_number(part))
                    except InvalidValueError: values.append(part)
            position = qp.end(); continue
        qv = _QV1.match(text, position)
        if qv:
            encoded = qv.group(1); encoded += "=" * (-len(encoded) % 4)
            try: decoded = base64.urlsafe_b64decode(encoded).decode("utf-8")
            except Exception as exc: raise InvalidValueError("invalid @qv1 payload") from exc
            if all_numbers: values.append(_number(decoded))
            else: values.append(decoded)
            position = qv.end(); continue
        raise InvalidValueError(f"invalid payload syntax at offset {position}")
    if not values:
        raise InvalidValueError("variable payload contains no values")
    return values

def _delta_rle_encode(values: list[bool]) -> list[tuple[int, int]]:
    bits = [1 if bool(v) else 0 for v in values]
    if not bits: return []
    delta = [bits[0]] + [bits[i] ^ bits[i-1] for i in range(1, len(bits))]
    out: list[tuple[int, int]] = []
    current = delta[0]; count = 1
    for bit in delta[1:]:
        if bit == current: count += 1
        else: out.append((current, count)); current = bit; count = 1
    out.append((current, count)); return out

def _delta_rle_decode(runs: list[tuple[int, int]]) -> list[bool]:
    delta: list[int] = []
    for bit, count in runs:
        if bit not in (0, 1) or not isinstance(count, int) or count < 1:
            raise InvalidValueError("invalid corevar run-length payload")
        delta.extend([bit] * count)
    if not delta: return []
    bits = [delta[0]]
    for item in delta[1:]: bits.append(bits[-1] ^ item)
    return [bool(v) for v in bits]

def encode_core(values: list[bool]) -> bytes:
    if not isinstance(values, list) or any(type(v) is not bool for v in values):
        raise TypeError("booleanList must contain only bool values")
    runs = _delta_rle_encode(values)
    data = base64.b64encode(pickle.dumps(runs, protocol=4)).decode("ascii")
    return f"@q*p({data}):".encode("ascii")

def decode_core(payload: bytes, *, runs: bool = False):
    text = payload.decode("ascii")
    if not (text.startswith("@q*p(") and text.endswith("):") ):
        raise InvalidValueError("not a corevar payload")
    try:
        raw = base64.b64decode(text[5:-2].encode("ascii"), validate=True)
        value = restricted_loads(raw)
    except Exception as exc:
        if isinstance(exc, UnsafeLegacyContentError): raise
        raise InvalidValueError("invalid corevar payload") from exc
    if not isinstance(value, list) or any(not isinstance(x, tuple) or len(x) != 2 for x in value):
        raise InvalidValueError("invalid corevar run list")
    checked = [(int(bit), int(count)) for bit, count in value]
    return checked if runs else _delta_rle_decode(checked)
