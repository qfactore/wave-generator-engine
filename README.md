# Wave Generator Engine

WGE-0 is a validation scaffold only. It imports the sibling `wave-gen-interchange`
project as its authority source, validates the complete handoff, verifies frozen
authority without unpacking it, and wires fail-closed safety gates.

It contains no renderer, scheduler, transform executor, generator, or exporter.
It creates no audio, WAV, playback JSON, upload JSON, render plan, or production
session plan. WGE-1 has not started.

Run:

```bash
python -m wave_generator_engine validate-interchange
wge validate-interchange --interchange-dir /path/to/wave-gen-interchange
```

Discovery order is an explicit argument, `WAVE_GEN_INTERCHANGE_DIR`, then the
exact sibling directory. Failure is closed.

## Frozen and binding policy

Frozen Alpha Motif Corpus assets are immutable Tier 0 authority. Exact mode has
no carrier-frequency control, and motif-internal timing is immutable. Calibration
and playback intensity are separate. Pulse Pattern is mode data. Complex Mode
will require macro-state scheduling before packets. Focus Role is remappable.

Profiles are versioned data, not a single Python profile. X-Alpha Standard is a
reserved locked preset that becomes the default in WGE-1. X-Alpha25 and
X-Alpha45 are delivery presets from the same source profile.

Future WAV and playback JSON outputs are sibling exporters from one validated
plan. Initial future development will use one-session, 60-second diagnostic WAV
requests. None of those exporters exists in WGE-0.
