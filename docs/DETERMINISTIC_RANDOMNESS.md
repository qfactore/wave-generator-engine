# Deterministic Randomness

WGE-3 uses local `random.Random` instances. Stage seeds derive from the root
seed and stable labels using the first 64 bits of SHA-256. Python's randomized
`hash()` and global random state are not used.

Event traces explicitly identify stage-level seeds and use packet and unit
indices as draw coordinates. Their names do not imply per-packet seed
uniqueness.

The committed root seed is `20260622`. The same request, authority, and profiles
produce byte-identical core plans and raw diagnostics. Timestamps and paths do
not enter core hashes.
