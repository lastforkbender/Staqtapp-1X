# Staqtapp 1.3.0 release notes

This release replaces the production monolith with a typed package engine. It closes the Phase 0 critical defects for the supported surface: existing VFS creation is non-destructive; locks are enforced; generated Python is absent; writes gain backup, conflict detection, fsync, and atomic replacement; missing mutations no longer report false success; and multiprocessing is no longer serialized through one global library lock.

The frozen 1.2.615 source remains under `staqtapp.legacy` solely as historical evidence and a migration oracle. The production modules do not import it.


The release is intentionally scoped: it makes the supported core deterministic and safe while refusing unrecovered behavior. It is not represented as full completion of the original twelve-phase roadmap.
