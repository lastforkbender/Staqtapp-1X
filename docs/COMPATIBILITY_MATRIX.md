# Compatibility matrix

| Area | 1.4.0 state |
|---|---|
| SQTPP 1.2.615 core files | Read/write compatible for core variables, locks, and stalk history |
| Original public function names | Preserved |
| Valid core return shapes | Preserved where evidence existed |
| Silent overwrite / false success | Removed; typed errors |
| Plain string variable data | Accepted and normalized |
| Corevar legacy pickle | Restricted read; compatible safe write |
| Global module-directory storage | Replaced by configurable storage root |
| Global API lock | Replaced by per-VFS writer locks; reads use snapshots |
| Lambda/registry generated Python | Disabled |
| Trees/Pojishon/dark/genic/revar | Explicitly unsupported pending contract recovery |
