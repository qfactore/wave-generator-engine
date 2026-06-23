# First Diagnostic Session 1 WAV Pack

WGE-4B2B connects the qualified immutable Session 1 EventPlan to the existing
WGE-4A exact renderer and WGE-4B2A deterministic PCM16 writer.

The export rerenders all eight buses ephemerally and verifies their canonical
WGE-4A hashes before any file is written. WGE-4A stores its float64 buses in
native PCM-code units, so export converts representation by dividing by 32768
before contract quantization. This is the authoritative PCM decode convention;
it is not peak normalization, gain scaling, or calibration. The ×1.1 corpus
calibration remains applied exactly once.

The diagnostic pack contains four 60-second, 48 kHz stereo PCM16 RIFF/WAVE
files:

| File | Left | Right |
|---|---:|---:|
| `x_alpha_session_01_baseline_branch_01.wav` | 0 | 1 |
| `x_alpha_session_01_baseline_branch_02.wav` | 2 | 3 |
| `x_alpha_session_01_baseline_branch_03.wav` | 4 | 5 |
| `x_alpha_session_01_baseline_branch_04.wav` | 6 | 7 |

Each file has 2,880,000 frames, 11,520,000 PCM data bytes, and a total size of
11,520,044 bytes. Files contain only the standard `fmt ` and `data` chunks.

For each branch, an independent reference path calculates ties-to-even PCM16
codes. Readback parses the complete RIFF structure and requires exact integer
code equality for both channels and every frame. Maximum normalized
quantization error is `1/65536`.

The entire render/export was repeated in an isolated temporary directory.
Every WAV byte, metadata JSON document, file hash, data hash, PCM stream hash,
and canonical pack hash matched. The duplicate temporary pack was deleted
before completion.

This is a diagnostic listening pack only. It does not certify production
delivery or target hardware, and it contains no playback, upload, encryption,
or session-package metadata.
