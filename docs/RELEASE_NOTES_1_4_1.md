# Staqtapp 1X 1.4.1 Release Notes

Staqtapp 1.4.1 introduces the Phase 1 streaming span-patch commit engine. Supported core mutations are represented as ordered unchanged source ranges plus replacement bytes and are streamed into a temporary destination. The committed VFS is never modified in place.

## Durability

The writer validates the source revision, creates a hard-link backup when possible (or a durable bounded-buffer copy), streams and hashes the destination, flushes and fsyncs it, revalidates the source identity, atomically replaces the active VFS, fsyncs the directory, and invalidates the disposable `.sqti` sidecar.

## Scope

This release intentionally does not add transaction sessions, immutable revision browsing, typed values, integrity maps, or TDS-style telemetry.

## Validation

The release passes 26 tests, including the complete 1.4.0 regression suite and new span-plan, required-mutation, interruption, and backup-recovery coverage.
