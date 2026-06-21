# Frozen Motif Bank

The Frozen Motif Bank resolves the archive, asset manifest, storage contract,
and identity index through reviewed Interchange manifests. A source must be
classified `include`, carry Tier 0 authority, and be neither superseded nor
conflicted.

The complete archive hash is checked before NPZ access. Loading uses
`allow_pickle=False`; object arrays are rejected. Exactly 84 IDs must match the
declared archive order. Shape, dtype, sample rate, and the documented
dtype-plus-shape-plus-bytes hash are verified per motif.

Arrays returned by the default API are non-writeable. Detached diagnostic copies
are explicitly labelled non-authoritative and cannot replace exact identity.
The archive is hashed again after access and is never extracted or copied into
the engine repository.
