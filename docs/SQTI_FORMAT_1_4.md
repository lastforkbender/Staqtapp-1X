# SQTI disposable index format — Staqtapp 1.4

`.sqti` files accelerate SQTPP reads. They are caches, not storage authorities.

## Invariants

- The matching `.sqtpp` file remains the only authoritative data source.
- An `.sqti` file contains no payload bytes and no unique data.
- Failure to open, validate, or parse an index causes a normal SQTPP scan.
- Index replacement is atomic.
- A VFS mutation invalidates the previous sidecar.

## Validation

The header records:

- format magic and version;
- offset-width flags;
- VFS device, inode, size, and nanosecond modification time;
- TQPT and TPQT structural spans;
- optional history span;
- opaque record count;
- variable count;
- selected directory and folder names.

The sidecar ends with a SHA-256 digest of all preceding index bytes.

## Sections

1. Fixed header.
2. UTF-8 directory and folder names.
3. Physical-order entries containing name and payload offsets.
4. Hash-order entries containing CRC32 and physical slot.
5. Zlib-compressed newline-separated variable names in physical order.
6. SHA-256 sidecar checksum.

For VFS files up to 4 GiB, physical spans use 32-bit offsets. Larger files use 64-bit offsets. CRC32 collisions are resolved by comparing the requested ASCII name directly against the mapped `.sqtpp` bytes before any payload is returned.

## Staleness

Atomic SQTPP replacement changes file identity. If device, inode, size, or modification time differs, the index is rejected. A stale sidecar may remain temporarily on platforms where another process still maps it; it cannot be used because the identity check fails.
