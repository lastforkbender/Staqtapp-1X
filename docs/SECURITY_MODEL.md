# Security model

Staqtapp 1.4.0 does not use arbitrary `eval`, `exec`, generated-module import, or unrestricted pickle loading in production paths. Legacy core-variable pickle payloads are decoded by a strict allow-list unpickler and then structurally validated.

VFS names cannot contain path separators or traversal components. Directory, folder, and variable identifiers use published grammars. Existing files are never overwritten by `makevfs` or migration.

Regex search is bounded to a 256-character pattern and a 1 MB payload and rejects backreferences, lookbehind, and obvious nested-quantifier forms. This is a conservative safety policy, not a complete formal ReDoS proof.

Unsupported legacy records are preserved during ordinary canonical rewrites where their line-oriented framing is intact; they are not executed.
