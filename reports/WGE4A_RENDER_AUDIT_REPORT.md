# WGE-4A Exact Diagnostic Render Audit

Status: `WGE4A_RENDER_CORE_READY`

- Starting checkpoint: `a967b3160b4b815ed454c88de9522175c593db9b`
- Qualified run: Session 1 Baseline, 60 seconds, 48 kHz
- Rendered events: 960 of 960
- Exact frozen identities: verified
- Architecture: eight independent ephemeral float64 logical-channel buses
- Calibration: relative event gain, then corpus calibration ×1.1 exactly once
- Playback intensity: not applied
- Same-channel overlap additions: 3,271
- Maximum same-channel concurrency: 2
- Maximum simultaneously active logical channels: 2; channels were not summed
- Global calibrated sample peak: 0.2617401, −11.6426 dBFS, channel 0
- Global estimated true peak: 0.2626926, −11.6110 dBFS, channel 0
- Margin to −3 dBFS ceiling: 8.6110 dB
- Headroom verdict: `headroom_pass`
- Deterministic rerender: identical bus hashes, receipts, event traces, metrics,
  and verdicts in independent temporary workspaces
- Tests: 252
- WGE-4B authorization: true

The true-peak estimator is a faithful port of the permitted closure method:
eight phases, normalized sinc, raised-cosine window, radius 16, the 64 largest
absolute sample candidates per channel, offsets −1 and 0, and clipped boundary
support. The generated true peak is descriptively below the Tier 2 calibrated
source maximum of 0.2676167; that comparison is advisory.

No transform, normalization, limiter, playback intensity, stereo packaging,
audio export, WAV output, or persistent waveform array was created.
