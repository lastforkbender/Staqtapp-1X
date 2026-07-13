# Staqtapp 1.4.0 release notes

## Release purpose

Version 1.4.0 moves the original Staqtapp design toward a high-performance pure-Python storage engine without changing the public product identity or introducing native dependencies.

## Main change

Routine reads no longer copy and parse the complete `.sqtpp` file into variable payload objects. The engine opens an immutable mmap snapshot, indexes names and byte spans, and materializes only requested values.

A disposable `.sqti` sidecar provides fast fresh-process startup. It is:

- validated against device, inode, size, and nanosecond modification time;
- protected by its own SHA-256 checksum;
- atomically written;
- automatically ignored and rebuilt when stale or corrupt;
- free of unique application data.

## Transaction improvements

Writes retain the 1.3 durability model. Version 1.4 additionally:

- uses a hard link to the old immutable inode for the backup when supported;
- falls back to an fsynced byte copy when hard links are unavailable;
- reads one internally consistent source revision;
- avoids repeated whole-file conflict hashes;
- assembles serialized output once instead of repeatedly splicing complete byte strings.

## Compatibility

The original supported public signatures remain unchanged. Legacy SQTPP 1.2.615 fixtures continue to verify and migrate. Unsafe generated-code features remain disabled.

## Performance summary

On the included CPython 3.13.5/Linux benchmark:

| Records | Metric | 1.3.0 | 1.4.0 |
|---:|---|---:|---:|
| 100,000 | Warm `findvar` | 13.498 ms | 0.025 ms |
| 100,000 | Warm `loadvar` | 14.592 ms | 0.039 ms |
| 100,000 | One complete `listvars` | 9.13 ms | 2.19 ms |
| 500,000 | Warm `findvar` | 135.117 ms | 0.051 ms |
| 500,000 | Warm `loadvar` | 132.174 ms | 0.062 ms |
| 500,000 | One complete `listvars` | 84.13 ms | 38.63 ms |
| 500,000 | Fresh-process indexed reopen | n/a | 25.84 ms |

The first-ever 500,000-record select plus first lookup completed in approximately 1.85 seconds in 1.4.0 versus approximately 1.97 seconds in 1.3.0. Later opens and point lookups receive the much larger gain.

These results are environment-specific and should not be treated as universal hardware claims.
