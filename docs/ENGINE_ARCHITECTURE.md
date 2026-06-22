# Engine Architecture

WGE-3 adds deterministic metadata planning above the WGE-2 identity bank:

`Authority → Source Profile → Delivery Preset → Planning Snapshot → common stage pipeline → validated diagnostic plans`

One pipeline serves Baseline, Dense, and Complex registrations. Baseline is
implemented; Dense and Complex return a structured unsupported-mode error.

Planning uses identity-index metadata rather than waveform samples. The event
plan contains sample-aligned timing, logical channels, grammar, roles, exact
motif IDs and hashes, and neutral relative-gain metadata. It is explicitly
non-executable for rendering.

WGE-3Q adds an orthogonal, read-only qualification layer. It reads committed
plans and manifest-permitted source statistics, writes only additive
qualification artifacts, and verifies core plan hashes before and after. The
qualification layer has no renderer or waveform access path.

WGE-3S adds locked session-planning overlays beneath the common Baseline
planner. Selection is performed by profile registry data using source-profile
ID, content hash, logical session, and mode. No Session 1 scheduler branch
exists. Overlay parameters carry source scope, authority, binding status, and
provisional status.
