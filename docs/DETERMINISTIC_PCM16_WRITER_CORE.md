# Deterministic PCM16 WAV Writer Core

WGE-4B2A implements the narrow byte writer and independent readback validator
required by `diagnostic_wav_export_contract_v1`. It is validated only with
small synthetic float64 arrays.

The writer supports exactly stereo, 48 kHz, little-endian signed PCM16 in a
standard RIFF/WAVE container. It creates a deterministic 44-byte header
containing only `RIFF`, `WAVE`, `fmt `, and `data`, then writes interleaved
codes in `L0, R0, L1, R1` order.

Quantization is:

```text
code = round_ties_to_even(sample × 32768)
```

The accepted range is `[-1.0, 32767/32768]`. There is no clipping,
saturation, dither, normalization, limiter, calibration multiplier, playback
intensity, metadata chunk, resampling, or alternate encoding.

The independent readback path parses RIFF and chunks directly, checks every
header field and exact chunk order, reconstructs little-endian integer codes,
and independently calculates expected reference codes. It fails on channel
swaps, modified codes, truncation, malformed headers, unknown chunks, subtype
changes, frame changes, and excess quantization error.

`DiagnosticExportManifestBuilder` defines future metadata records only. WGE-4B2A
does not build the real Session 1 manifest or create its four files.

No command writes a real diagnostic WAV. Synthetic tests create temporary files
inside pytest-owned directories and explicitly delete them.
