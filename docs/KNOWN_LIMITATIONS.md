# Known limitations in 1.4.0

Staqtapp 1.4.0 is a stable **mapped-read core**, not completion of every phase in the overhaul roadmap.

- Mutations still read and rewrite the complete canonical SQTPP destination. Hard-link backups and one-pass assembly reduce overhead, but write amplification still grows with VFS size.
- Complete streaming span-patch transactions are not implemented yet.
- The package supports the existing selected directory/folder hierarchy; complete directory, folder, subfolder, movement, and embedded-file CRUD is not yet exposed.
- One `.sqti` sidecar represents the selected hierarchy model currently supported by the stable facade. A future multi-container engine will need a hierarchy-wide index format.
- The first open after a mutation or sidecar removal performs a structural scan and rebuild. Subsequent opens are much faster.
- `listvars()` must return a complete Python list for compatibility; extremely large callers still pay for the returned string objects. A streaming iterator API is planned.
- Advanced features with unsafe or unrecovered contracts remain explicitly disabled.
- Regex safety uses a conservative bounded policy rather than a separate linear-time regex engine.
- The validation run covers Linux/Python 3.13. Cross-platform lock and mapping paths exist, but Windows CI validation is still required before claiming full Windows certification.


## 1.4.1 write-path note

The destination is streamed and is no longer assembled as one complete Python `bytes` object. The current compatibility parser still materializes canonical variable and metadata sections while constructing replacement bytes; later optimization may make individual record edits fully span-native without altering the public API.
