# Wave Generator Engine

Version 0.2.0 implements WGE-1: a non-executable, versioned configuration
layer over the authority validation established in WGE-0.

The architecture keeps four concepts distinct:

- Source Profile: waveform-system identity, authority, topology, calibration,
  trust, and permitted configuration surface.
- Delivery Preset: duration, playback default, and run-selection policy.
- Run Request: future-run selection and allowed metadata overrides.
- LeverSet: waveform-related configuration independent of Basic or Advanced
  presentation views.

X-Alpha Standard is the one locked root Source Profile. X-Alpha25, X-Alpha45,
and Diagnostic 60s are non-executable Delivery Presets referencing it.

```bash
wge profiles validate
wge profiles list --json
wge profiles show x_alpha_standard_v1
wge presets list
wge levers list
wge requests validate request.json
```

WGE-1 contains no motif loader, array access, scheduler, renderer, transform
executor, SessionPlan builder, RenderPlan builder, or exporter. It creates no
audio, WAV, playback JSON, or upload payload. WGE-2 has not started.
