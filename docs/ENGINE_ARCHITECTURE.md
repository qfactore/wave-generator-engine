# Engine Architecture

WGE-3 adds deterministic metadata planning above the WGE-2 identity bank:

`Authority → Source Profile → Delivery Preset → Planning Snapshot → common stage pipeline → validated diagnostic plans`

One pipeline serves Baseline, Dense, and Complex registrations. Baseline is
implemented; Dense and Complex return a structured unsupported-mode error.

Planning uses identity-index metadata rather than waveform samples. The event
plan contains sample-aligned timing, logical channels, grammar, roles, exact
motif IDs and hashes, and neutral relative-gain metadata. It is explicitly
non-executable for rendering.
