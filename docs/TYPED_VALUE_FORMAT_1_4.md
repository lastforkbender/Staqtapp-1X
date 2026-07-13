# Typed Value Format 1.4

Typed values are stored as a legacy-safe text envelope containing URL-safe Base64 of canonical JSON. The canonical document identifies codec `staqt-json-v1` and contains an explicit tagged node tree.

Security rules:
- no `eval`, `exec`, or arbitrary object construction;
- no pickle in the typed-value path;
- exact built-in type allow-list;
- cycle rejection;
- depth, node-count, and encoded-size limits;
- canonical re-encoding validation on every read;
- exact expected-type checks use `type(value) is expected_type`.

Determinism rules:
- compact UTF-8 JSON, sorted object keys, no JSON NaN tokens;
- integers encoded as decimal strings;
- finite floats encoded with `float.hex()`;
- NaN and infinities use explicit tokens;
- sets/frozensets sorted by canonical child bytes;
- dictionaries encoded as sorted key/value pairs, preserving non-string keys.
