# WGE-4B2B First Diagnostic Session 1 WAV Export

Status: `WGE4B2B_DIAGNOSTIC_EXPORT_READY`

- Starting checkpoint: `ab8b1ffe9dfbe85e2841eedc2e6d7dd5690ca3b1`
- Qualified plan: X-Alpha Standard, Session 1 Baseline, seed 20260622
- Plan structure: 149 packets, 960 events, Focus Role channel 2
- Rerender: 960 events exactly once; all eight WGE-4A bus hashes matched
- Representation conversion: native PCM-code units divided by 32768
- Calibration: ×1.1 already applied; export multiplier 1.0
- Playback intensity: not applied
- Files: four stereo PCM16 RIFF/WAVE files, 48 kHz
- Frames per file: 2,880,000
- File size: 11,520,044 bytes each
- Exact readback code equality: passed for every frame and channel
- Global maximum quantization error: 0.0000152587890625
- Global mean absolute quantization error: 0.00000027206129497952033
- Global maximum decoded sample level: 0.261749267578125
- Pack SHA-256 contract hash: `67209fbe2e18fb070647b1f0d94e533bace77489155d900cd2e7211b57bd6d9d`
- Duplicate export: byte-identical; temporary duplicate deleted
- Tests: 304
- WGE-4C authorization: true

## File hashes

| Branch | WAV SHA-256 | Data SHA-256 |
|---:|---|---|
| 01 | `9c5ed5994f9e4d8ec15dac91851f788508df106185b4816ddc11054ae2170747` | `759ea8ff786ef7362ea09d3a69f73dd38f0f4d0e1d0075057bb810c076c0361f` |
| 02 | `28472051eea75634ef0dae74eb3cab7f214b09c47e89e35487f7168113057d9c` | `723d5a80496f0b4a23c687cb4d518bcdd872c93bc4d81d9ea840fc45593212b0` |
| 03 | `4954c3e6ac8e01fed500b85bcdd46e4cb29dc62e336787aed7ce5c9df726d9e4` | `ff395e7aa48f8a0913001923b8c9218d73ee9755458a8db3f7c630a896d80c18` |
| 04 | `9b1dbdf3eb955c80bd37203c8ef6d0bfabbeee551ed84e73460143863ec6df61` | `a35d77a00d2beb9625c4460707e75f595f0d00a3eb4f185daa086aa50d9f50f5` |

The pack is diagnostic-only. No PCM24, production exporter, playback JSON,
upload JSON, encryption, or session packaging was created.
