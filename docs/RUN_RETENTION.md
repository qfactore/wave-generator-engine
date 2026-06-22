# Run Retention

`runs/latest` is atomically replaced scratch output. `runs/saved/<safe-id>` is
created only with an explicit safe identifier and refuses overwrite unless
requested. Path traversal is rejected.

Each run snapshots the request, authority, source profile, delivery preset,
planning profile, core plans, validation, diagnostic manifest, raw arrays, and
figures. WGE-3 creates no audio directory. Archived-run lifecycle remains future
work.
