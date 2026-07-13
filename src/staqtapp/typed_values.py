from __future__ import annotations

import base64
import math
from dataclasses import dataclass
from typing import Any

from .errors import InvalidValueError
from . import json_backend

MAGIC = "stqv1:"
MAX_DEPTH = 64
MAX_NODES = 1_000_000
MAX_ENCODED_BYTES = 256 * 1024 * 1024

@dataclass(frozen=True, slots=True)
class ValueInfo:
    type: str
    encoded_size: int
    logical_length: int | None
    codec: str = "staqt-json-v1"

    def as_dict(self):
        return {"type": self.type, "encoded_size": self.encoded_size, "logical_length": self.logical_length, "codec": self.codec}


def _json_bytes(node: Any) -> bytes:
    return json_backend.dumps_canonical(node)


def _encode_node(value: Any, seen: set[int], depth: int, counter: list[int]) -> Any:
    if depth > MAX_DEPTH:
        raise InvalidValueError(f"typed value exceeds maximum depth {MAX_DEPTH}")
    counter[0] += 1
    if counter[0] > MAX_NODES:
        raise InvalidValueError(f"typed value exceeds maximum node count {MAX_NODES}")
    if value is None: return {"t":"none"}
    if type(value) is bool: return {"t":"bool","v":value}
    if type(value) is int: return {"t":"int","v":str(value)}
    if type(value) is float:
        if math.isnan(value): token = "nan"
        elif math.isinf(value): token = "+inf" if value > 0 else "-inf"
        else: token = value.hex()
        return {"t":"float","v":token}
    if type(value) is complex:
        return {"t":"complex","r":_encode_node(value.real, seen, depth+1, counter),"i":_encode_node(value.imag, seen, depth+1, counter)}
    if type(value) is str: return {"t":"str","v":value}
    if type(value) is bytes: return {"t":"bytes","v":base64.b64encode(value).decode("ascii")}
    if type(value) in (list, tuple, set, frozenset, dict):
        marker = id(value)
        if marker in seen: raise InvalidValueError("cyclic typed values are not supported")
        seen.add(marker)
        try:
            if type(value) is dict:
                pairs=[]
                for k,v in value.items():
                    kn=_encode_node(k, seen, depth+1, counter); vn=_encode_node(v, seen, depth+1, counter)
                    pairs.append((_json_bytes(kn), [kn,vn]))
                pairs.sort(key=lambda x:x[0])
                return {"t":"dict","v":[p for _,p in pairs]}
            items=[_encode_node(x, seen, depth+1, counter) for x in value]
            tag={list:"list",tuple:"tuple",set:"set",frozenset:"frozenset"}[type(value)]
            if type(value) in (set,frozenset): items.sort(key=_json_bytes)
            return {"t":tag,"v":items}
        finally: seen.remove(marker)
    raise InvalidValueError(f"unsupported typed value: {type(value).__module__}.{type(value).__qualname__}")


def encode_typed(value: Any) -> bytes:
    raw=_json_bytes({"codec":"staqt-json-v1","value":_encode_node(value,set(),0,[0])})
    if len(raw)>MAX_ENCODED_BYTES: raise InvalidValueError("typed value exceeds maximum encoded size")
    return raw


def envelope(value: Any) -> str:
    return MAGIC + base64.urlsafe_b64encode(encode_typed(value)).decode("ascii")


def unenvelope(text: str) -> bytes:
    if not isinstance(text,str) or not text.startswith(MAGIC): raise InvalidValueError("variable does not contain a Staqtapp typed value")
    try: raw=base64.urlsafe_b64decode(text[len(MAGIC):].encode("ascii"))
    except Exception as exc: raise InvalidValueError("invalid typed-value envelope") from exc
    if len(raw)>MAX_ENCODED_BYTES: raise InvalidValueError("typed value exceeds maximum encoded size")
    return raw


def _decode_node(node: Any, depth=0, counter=None):
    if counter is None: counter=[0]
    if depth>MAX_DEPTH: raise InvalidValueError("typed value nesting limit exceeded")
    counter[0]+=1
    if counter[0]>MAX_NODES: raise InvalidValueError("typed value node limit exceeded")
    if not isinstance(node,dict) or set(node)-{"t","v","r","i"}: raise InvalidValueError("malformed typed node")
    t=node.get("t")
    if t=="none": return None
    if t=="bool" and type(node.get("v")) is bool: return node["v"]
    if t=="int" and isinstance(node.get("v"),str):
        try: return int(node["v"])
        except Exception as exc: raise InvalidValueError("invalid integer payload") from exc
    if t=="float" and isinstance(node.get("v"),str):
        token=node["v"]
        if token=="nan": return float("nan")
        if token=="+inf": return float("inf")
        if token=="-inf": return float("-inf")
        try: return float.fromhex(token)
        except Exception as exc: raise InvalidValueError("invalid float payload") from exc
    if t=="complex": return complex(_decode_node(node.get("r"),depth+1,counter),_decode_node(node.get("i"),depth+1,counter))
    if t=="str" and isinstance(node.get("v"),str): return node["v"]
    if t=="bytes" and isinstance(node.get("v"),str):
        try: return base64.b64decode(node["v"].encode("ascii"),validate=True)
        except Exception as exc: raise InvalidValueError("invalid bytes payload") from exc
    if t in {"list","tuple","set","frozenset"} and isinstance(node.get("v"),list):
        values=[_decode_node(x,depth+1,counter) for x in node["v"]]
        return {"list":list,"tuple":tuple,"set":set,"frozenset":frozenset}[t](values)
    if t=="dict" and isinstance(node.get("v"),list):
        out={}
        for pair in node["v"]:
            if not isinstance(pair,list) or len(pair)!=2: raise InvalidValueError("invalid dictionary entry")
            key=_decode_node(pair[0],depth+1,counter)
            try: hash(key)
            except Exception as exc: raise InvalidValueError("decoded dictionary key is unhashable") from exc
            if key in out: raise InvalidValueError("duplicate dictionary key")
            out[key]=_decode_node(pair[1],depth+1,counter)
        return out
    raise InvalidValueError(f"unknown or malformed typed tag: {t!r}")


def decode_typed(raw: bytes) -> Any:
    try: doc=json_backend.loads_strict(raw)
    except Exception as exc: raise InvalidValueError("typed value is not canonical UTF-8 JSON") from exc
    if not isinstance(doc,dict) or doc.get("codec")!="staqt-json-v1" or "value" not in doc: raise InvalidValueError("unsupported typed-value codec")
    if _json_bytes(doc)!=raw: raise InvalidValueError("typed value is not canonically encoded")
    return _decode_node(doc["value"])


def inspect_raw(raw: bytes) -> ValueInfo:
    value=decode_typed(raw)
    logical=len(value) if isinstance(value,(str,bytes,list,tuple,dict,set,frozenset)) else None
    return ValueInfo(type(value).__name__,len(raw),logical)


def decoded_size_from_base64(encoded_length: int, tail: bytes) -> int:
    """Return decoded size for a canonical padded Base64 payload."""
    if encoded_length < 0 or encoded_length % 4:
        raise InvalidValueError("typed-value Base64 length is invalid")
    padding = tail.count(b"=")
    if padding > 2:
        raise InvalidValueError("typed-value Base64 padding is invalid")
    return (encoded_length // 4) * 3 - padding

def decode_base64_range(encoded: bytes, *, decoded_offset: int, requested_start: int, requested_end: int) -> bytes:
    """Decode one aligned Base64 window and return the requested decoded slice."""
    try:
        raw = base64.urlsafe_b64decode(encoded)
    except Exception as exc:
        raise InvalidValueError("invalid typed-value envelope") from exc
    left = requested_start - decoded_offset
    right = requested_end - decoded_offset
    return raw[left:right]
