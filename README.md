# Wave Generator Engine

Version 0.3.0 implements WGE-2: secure, read-only access to the Frozen Alpha
Motif Corpus and non-rendering calibration preflight.

The archive is resolved only through included Tier 0 Interchange authority. Its
whole-file SHA-256 is verified before `np.load(..., allow_pickle=False)` is
entered. All 84 IDs, order positions, shapes, dtypes, and per-motif hashes are
validated. Returned authoritative arrays are immutable.

```bash
wge validate-interchange
wge profiles validate
wge motifs validate
wge motifs list --json
wge motifs show medoid_64_000 --json
wge motifs verify-exact medoid_64_000 --json
wge motifs summarize --json
wge calibration inspect --json
wge calibration preflight --json
```

Exact Identity Access is a direct no-op lookup, not a renderer or transform. It
uses no randomness, normalization, gain, resampling, conversion, or operation
pipeline. Motif metrics and calibration projections are diagnostics only.

WGE-2 creates no plans or audio. No scheduler, renderer, transform executor,
WAV exporter, playback JSON exporter, or generator exists. X-Alpha Standard
remains locked and non-executable. The first audible render is planned for
WGE-4; WGE-3 has not started.
