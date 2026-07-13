# Roadmap status at Staqtapp 1.3.0

| Roadmap phase | Status in 1.3.0 |
|---|---|
| Phase 0 — freeze and inventory | Source-only audit complete; frozen SHA-256 retained |
| Phase 1 — compatibility contract | Complete for the supported core facade; advanced contracts remain unrecovered |
| Phase 2 — mapped read foundation | Core SQTPP parser, typed records, bounded read-index cache, and corruption checks implemented |
| Phase 3 — transaction writer | Per-VFS lock, backup, conflict checks, fsync, atomic replace, and recovery implemented |
| Phase 4 — core variable parity | Stable core CRUD, search, join, corevar, and typed errors implemented |
| Phase 5 — complete hierarchy CRUD | Not complete; current selected hierarchy is supported |
| Phase 6 — locks/history/contexts/concurrency | Operation-deny locks, stalk history, context selection, and spawn dispatch implemented |
| Phase 7 — migration | Safe copy/canonicalize/verify workflow implemented for supported structures |
| Phases 8–11 — advanced recovery | Not guessed; public names fail explicitly with `UnsupportedLegacyFeatureError` |
| Phase 12 — full production consolidation | Partially complete: stable core is production-shaped, but hierarchy, sidecar indexing, platform CI, and advanced decisions remain |

The version is 1.3.0 because this is a new stable subsystem that preserves existing calls. It is not a 2.0 API break.
