# Migration guide

`migrate_vfs(source, destination, directory, folder, report_path=...)` always writes a distinct destination and refuses to overwrite it. It parses the source, canonicalizes supported TQPT/TPQT/history structures, reopens the destination, and compares record counts before reporting success.

The source file is never modified. Keep the generated report with the migrated file. Unknown line-oriented TQPT records are preserved as opaque records. Advanced legacy behavior is not activated merely because its bytes are retained.
