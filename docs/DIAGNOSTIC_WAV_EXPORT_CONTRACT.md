# Diagnostic WAV Export Contract

WGE-4B1 freezes the contract for a later diagnostic export without creating a
WAV file or persisting waveform samples.

## Channel packaging

The permitted closure implementation defines:

```text
logical_channel = (track_in_session - 1) * 2 + stereo_channel_index
```

Therefore source-order branches map as:

| Branch | Left | Right | Meaning |
|---|---:|---:|---|
| `branch_01` | 0 | 1 | independent output device 1 |
| `branch_02` | 2 | 3 | independent output device 2 |
| `branch_03` | 4 | 5 | independent output device 3 |
| `branch_04` | 6 | 7 | independent output device 4 |

Focus Role is not wiring authority and cannot alter this mapping.

## Diagnostic encoding

The first diagnostic pack uses source-equivalent stereo signed PCM16 at
48,000 Hz in standard little-endian RIFF/WAVE files. This is diagnostic-only:
it does not certify a production delivery format or target hardware.

24-bit PCM is not selected because Interchange authority explicitly leaves it
Tier 3 and provisional pending target hardware and player validation.

The deterministic PCM16 quantizer accepts float64 values in:

```text
[-1.0, 32767 / 32768]
```

It computes the nearest integer to `sample × 32768`, resolving exact ties to
the even integer. `-1.0` maps to `-32768`; `+1.0` is rejected as overflow.
NaN, infinity, and out-of-range samples fail. No clipping or saturation is
permitted. The maximum normalized quantization error is `1 / 65536`.

No dither is permitted in this diagnostic contract. Authority introduces no
dither, and deterministic code-equivalence validation excludes unrecorded
random noise.

## Calibration boundary

Input buses are WGE-4A calibrated 100% buses. The ×1.1 corpus calibration has
already been applied and is not applied again. Playback intensity `0.80`
remains later playback metadata and is not baked into samples.

Normalization, automatic gain scaling, limiting, compression, saturation,
soft clipping, per-file peak matching, resampling, and channel swapping are
blocked.

## Readback validation required in WGE-4B2

Before quantization, all eight float64 buses must match the WGE-4A canonical
bus hashes. After writing and reading back, all four files must have exactly
two channels, 48,000 Hz, the qualified frame count, PCM16 subtype, and the
declared left/right mapping. Decoded integer codes must equal the reference
quantizer exactly, with no frame changes, channel swaps, clipping, second
calibration, normalization, or playback-intensity application.

Only `fmt ` and `data` chunks are permitted. Software identifiers, comments,
source names, and unknown chunks are forbidden.
