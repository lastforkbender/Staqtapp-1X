# Performance report — Staqtapp 1.4.0

## Environment

- Python: CPython 3.13.5
- Platform: Linux 4.4.0, x86_64, glibc 2.41
- Date: 2026-07-13
- Workload: generated canonical SQTPP files containing short `@qp(...)` values
- Cache state: warm point tests follow one selected/opened snapshot

## Results

| Records | File size | Version | Initial select/build | First lookup | Warm `findvar` median | Warm `loadvar` median | One `listvars` |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 100,000 | 2,578,099 B | 1.3.0 | 208.27 ms | 133.68 ms | 13.498 ms | 14.592 ms | 9.13 ms |
| 100,000 | 2,578,099 B | 1.4.0 | 325.26 ms | 0.115 ms | 0.025 ms | 0.039 ms | 2.19 ms |
| 500,000 | 13,778,099 B | 1.3.0 | 999.42 ms | 966.23 ms | 135.117 ms | 132.174 ms | 84.13 ms |
| 500,000 | 13,778,099 B | 1.4.0 | 1,826.29 ms | 26.97 ms* | 0.051 ms | 0.062 ms | 38.63 ms |

`*` At 500,000 records, the temporary first-scan Python index exceeds the bounded cache budget and is evicted. The first lookup therefore maps the newly created sidecar. Subsequent lookups use that mapping.

End-to-end first use is 325.37 ms versus 341.95 ms at 100,000 records, and 1,853.26 ms versus 1,965.65 ms at 500,000 records. The one-time sidecar construction is therefore paid without making the complete first use slower in these measurements.

## Fresh-process sidecar result

For the 500,000-record file, a new Python process reopened the existing `.sqti` index in 25.84 ms and performed its first lookup in 0.208 ms. Under `tracemalloc`, sidecar reopen retained approximately 17.8 KB and peaked at approximately 24.7 KB of traced Python memory; the mapped file pages are operating-system-managed and are not counted as Python heap.

## First-build memory comparison

At 100,000 records:

- 1.3.0 first cached lookup peak: 34,590,274 traced Python bytes.
- 1.4.0 first mapped-index build peak: 29,874,127 traced Python bytes.

After a sidecar exists, 1.4.0 avoids rebuilding that per-record Python object graph on later process starts.

## Interpretation

Version 1.4.0 changes lookup scaling from repeated full dictionary reconstruction to a retained or mapped index. The improvement is architectural rather than a micro-optimization.

The remaining dominant cost is mutation. A small update still produces a complete canonical destination file. The next performance milestone is a streaming span-patch transaction writer that copies unchanged ranges directly and never constructs a complete new VFS in Python memory.
