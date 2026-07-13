# Performance methodology

The reusable benchmark is `tools/benchmark.py`. The included baseline was captured on Python 3.13.5 with 2,000 variables. It measures VFS creation, atomic batch insertion, warm `listvars`, exact lookup, load, one small change, resulting file size, and verification.

Read operations use a bounded 16-entry process-local index cache keyed by file identity (`device`, `inode`, size, and nanosecond modification time). Atomic replacement naturally invalidates the key, and the engine also removes the old path entry after its own mutations.

The current transaction writer deliberately favors correctness over low write amplification. A small variable change rewrites the canonical SQTPP file and therefore writes approximately one file-size of data. This is recorded in the baseline and is not represented as an optimized large-file result. Region copying and versioned sidecar indexes remain future performance work.

## 1.4 mapped-index measurements

Large-read reports distinguish:

- first structural scan and `.sqti` construction;
- first lookup after selection;
- warm lookup against an existing process snapshot;
- fresh-process reopen against an existing sidecar;
- complete listing, which necessarily materializes public Python strings;
- Python heap measured by `tracemalloc`, excluding operating-system-managed mmap pages.

The benchmark source is `tools/benchmark_large_reads.py`. Generated fixtures use canonical short `@qp(...)` records so record-count scaling is visible without embedded-file payload size dominating the result.
