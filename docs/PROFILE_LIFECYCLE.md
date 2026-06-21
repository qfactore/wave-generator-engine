# Profile Lifecycle

Supported states are reserved, preset locked, draft, active, archived,
deprecated, and invalid.

Preset-locked, active, and archived profiles are immutable in place. Drafts may
be edited before activation. Deprecated profiles remain loadable for provenance
but are not selected by default. Invalid profiles are never selectable.

Forking creates a new draft and records the parent ID, version, content hash,
fork time, requested trust, changed fields, and authority snapshot. It never
modifies the parent, overwrites a profile, changes frozen authority, or unlocks
exact-mode carrier and timing blocks.
