# Immutable Revision Model

Each VFS `<name>.sqtpp` owns a hidden sibling directory:

```
.<name>.sqtpp.revisions/
  timeline.json
  objects/
    <sha256>.sqtpp
```

`objects` is content-addressed and deduplicated. `timeline.json` records commit order, parent content ID, event name, byte size, timestamp, and a contiguous sequence number. A rollback appends a new timeline event whose content ID may equal an earlier entry; prior entries and objects are never rewritten.

The VFS file is the source of truth. Revision discovery verifies that the timeline head matches the current file digest and records an `observed` reconciliation entry when needed. Corrupt timelines or objects are reported through the public non-halting failure envelope and are never silently trusted.
