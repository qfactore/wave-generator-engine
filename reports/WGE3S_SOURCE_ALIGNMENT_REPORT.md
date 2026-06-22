# WGE-3S Session 1 Source Alignment

Status: WGE3_SESSION1_SOURCE_ALIGNED

- Engine version: 0.4.2
- Planning overlay: `x_alpha_session_01_baseline_v1`
- Primary seed: 20260622
- Packets: 149, or 2.4833/s
- Events: 960, or 16.0/s
- Packet interval: 12,513 / 19,089.5 / 26,366 samples min/median/max
- Packet interval CV: 0.1906
- Primary-to-continuation gap median: 47.84 ms
- Trailing-spacing median: 54.29 ms
- Cycle-span median: 308.71 ms
- Pulse Pattern prevalence: 0.9799
- Immediate exact-asset repetition: 0.5193
- Motif entropy: 6.1590 bits
- Maximum motif share: 3.854%
- Focus/non-focus ratio: 1.0095
- Maximum concurrency: 2
- Qualification: `qualified_with_documented_caveats`
- WGE-4 authorization: true
- Deterministic rerun: byte-identical core plans, raw diagnostics, and qualification

Packet-onset spectrum remains not assessable against source waveform-activity
spectrum. Packet-label grammar proportions remain not assessable against source
descriptive sweep windows. These are semantic limitations, not downgraded
divergences.

Holdout seeds 20260623 and 20260624 both pass hard validation and qualify for
diagnostic rendering. No renderer, exporter, waveform buffer, audio, WAV, or
playback payload was created.
