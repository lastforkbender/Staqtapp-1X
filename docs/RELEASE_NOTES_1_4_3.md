# Staqtapp 1X 1.4.3 Release Notes

## Multi-operation transaction sessions

Staqtapp 1X 1.4.3 adds non-halting, all-or-nothing transaction execution across multiple supported mutations.

### New public API

- `run_transaction(calls)`
- `run_vfs_transaction(vfs_file, directory, folder, calls)`
- `TransactionResult`

Supported transaction mutations are `addvar`, `appvar`, `changevar`, `renamevar_stx`, `removevar`, and `joinvars`.

A transaction parses one locked source revision, applies operations sequentially to one in-memory overlay, supports read-your-own-writes between pending operations, builds one final mutation plan, and performs one atomic commit. Any rejected operation discards the complete overlay and returns a false-valued `TransactionResult` containing a structured `CallFailure`; no normal application exception escapes.

Independent `map_api_calls()` behavior is unchanged and remains per-call rather than all-or-nothing.
