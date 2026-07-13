# Recovery guide

Every committed mutation writes `<name>.sqtpp.bak` from the previously committed source before atomically replacing the active VFS. `recover_vfs()` restores that backup under the same per-VFS process lock and validates the selected hierarchy afterward.

The backup is a last-commit recovery point, not a complete version history. Copy important VFS files through an external backup policy as well.
