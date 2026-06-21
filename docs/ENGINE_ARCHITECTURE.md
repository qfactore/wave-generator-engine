# Engine Architecture

WGE-2 adds a read-only authority boundary beneath the WGE-1 profile system:

`Interchange authority → hash gate → Frozen Motif Bank → Exact Identity Access`

The bank verifies the whole archive before waveform access and returns immutable
copies with identity metadata. Exact access bypasses transforms and randomness.
Metrics and calibration preflight inspect values without persisting altered
arrays.

The future flow remains:

`Source Profile → SessionPackPlan → SessionPlan → RenderPlan → Exporter`

None of those planning or output stages is implemented in WGE-2.
