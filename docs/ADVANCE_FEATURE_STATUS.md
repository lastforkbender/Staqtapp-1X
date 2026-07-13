# Advanced feature status

The following facilities are **not production-supported in 1.4.0**: lambda execution/listing, registry/schema execution, trees, Pojishon, dark variables, genic variables, vital internals, revar, and the internal diagnostic interpreter.

Their public names remain present so callers receive a deterministic `UnsupportedLegacyFeatureError`, not `None`, generated-code execution, or accidental partial behavior. Their bytes are preserved when possible during core-file rewrites and migration.
