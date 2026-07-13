# Public API contract — Staqtapp 1.4.0

The 31 original function names and their positional signatures are preserved. Valid core calls retain their established return shapes where Phase 0 evidence existed. Defects are not retained: duplicate creation, missing-source joins, missing-variable removal, and locked mutation raise typed exceptions.

## Stable legacy-facing functions

`makevfs`, `setpath`, `corevar`, `addvar`, `appvar`, `renamevar_stx`, `removevar`, `listvars`, `listfiles`, `joinvars`, `changevar`, `vardata_stx`, `lockvar`, `locklist`, `lockdel`, `keyvar`, `findvar`, `findvar_stx`, `loadvar`, and `stalkvar`.

## Explicitly disabled functions

`sqtpp_rd1`, `lambdalist`, `lambdavar`, `registry`, `genicvar`, `darkvar`, `revar`, `addtree_stx`, `addbranch_stx`, `getbranch_stx`, and `pojishon` raise `UnsupportedLegacyFeatureError`. This is intentional: the frozen implementation contains generated Python execution, incomplete branches, or unrecovered contracts.

## Additive stable API

- `configure(storage_dir=...)`
- `open_vfs(name, directory, folder)`
- `encode_value(text)`
- `verify_vfs(...)`
- `migrate_vfs(...)`
- `recover_vfs()`
- `invoke_vfs_api(...)` and `map_vfs_api_calls(...)`
- `recent_events(limit=100)`
- `diagnostic_counts()`

## Performance-sensitive metadata

`listfiles()` returns a lightweight filesystem-generation value in `revision`. A complete content SHA-256 digest is intentionally reserved for `verify_vfs()` so ordinary metadata calls do not scan a potentially large VFS. The `.sqti` index is disposable and is not part of the logical return contract.


## 1.4.4 revision API

`list_revisions(limit=None)`, `rollback_revision(revision)`, and `prune_revisions(keep=32)` are stable additive calls. Revision identifiers are lowercase SHA-256 content digests. All errors are contained as false-valued `CallFailure` results.
