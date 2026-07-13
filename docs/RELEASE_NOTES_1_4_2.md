# Staqtapp 1X 1.4.2 — Non-Halting API Containment

Staqtapp 1X now contains ordinary application failures at every callable public API boundary.

## Behavior

- Successful calls preserve their existing return values.
- Failed calls return a false-valued immutable `CallFailure` object.
- Failure details include the API name, exception type, message, and bounded argument representation.
- Failures emit `api_failure_contained` diagnostic events.
- `invoke_api()` never exposes unknown-call, argument-shape, or engine exceptions.
- `map_api_calls()` and `map_vfs_api_calls()` return exactly one result per submitted call.
- One failed operation does not prevent later operations from executing.
- Process-pool infrastructure failures fall back to contained in-process execution.
- Transaction failures preserve the last committed VFS revision and return `CallFailure`.

## Scope

Containment applies to Python application exceptions (`Exception`). Process termination, interpreter failure, operating-system kill, and hardware failure cannot be converted into return values by an in-process library.

`open_vfs()` remains an advanced context-manager primitive because suppressing a failed context entry would allow the body to run against an incorrect VFS. Non-halting callers should use `invoke_vfs_api()` or `map_vfs_api_calls()`.
