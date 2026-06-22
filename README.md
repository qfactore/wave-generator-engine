# Wave Generator Engine

Version 0.4.2 implements source-aligned, deterministic Session 1 Baseline
planning plus read-only source-reference qualification.

The committed diagnostic run follows one common pipeline:

`Run Request → profile and preset → planning snapshot → macro state → packet grammar → Pulse Pattern → channel grammar → exact motif selection → EventPlan → validation → diagnostics`

Session 1 receives Baseline Mode through X-Alpha Standard profile data. The
planner never branches on Session 1. Dense and Complex Mode are registered but
fail closed as unsupported in WGE-3.

```bash
wge plans build --request examples/run_requests/x_alpha_session1_diagnostic_60s.json
wge plans validate runs/latest/session_pack_plan.json
wge runs show latest --json
wge diagnostics generate --plan runs/latest
wge qualify baseline --run runs/latest
wge qualification show runs/latest
wge qualification validate runs/latest
```

`runs/latest` contains plans, CSV, diagnostic JSON, and PNG figures only. Events
reference exact frozen motif identities; no waveform samples are embedded or
accessed during planning. Focus Role target `2` is explicit and run-specific,
not a profile default.

No renderer, audio exporter, transform executor, WAV, playback JSON, or audio
buffer exists. Headroom is not certified before waveform render and overlap
summation. The current qualification authorizes a future diagnostic WGE-4
render with documented evidence caveats, but no renderer or audible output is
implemented here.
## WGE-4A exact diagnostic rendering

`wge render audit --run runs/latest` evaluates the qualified EventPlan using
exact frozen motif identities, eight independent ephemeral float64 logical
channel buses, identity event gain, and the authoritative ×1.1 corpus
calibration. Same-channel overlaps are summed; different logical channels are
never summed.

The audit persists receipts, metrics, true-peak method provenance, headroom
verdict, and non-reconstructive figures under `runs/latest/render_audit/`.
It does not persist waveform arrays or create audio. Playback intensity,
normalization, limiting, stereo packaging, and WAV export remain absent.

## WGE-4B1 diagnostic export contract

`wge export contract show --json` and `wge export contract validate --json`
inspect the immutable diagnostic WAV contract. WGE-4B1 defines authoritative
stereo pairing, diagnostic PCM16 quantization, naming, and later readback
validation only. It does not provide a WAV-writing command or persist audio.

WGE-4B2A adds a contract-specific PCM16 byte writer and independent readback
validator for synthetic tests only. It does not expose a real export command,
render the qualified plan, or create the Session 1 diagnostic files.
