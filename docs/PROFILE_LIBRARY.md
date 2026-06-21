# Profile Library

X-Alpha Standard is the locked root Source Profile. Future custom profiles are
draft forks with immutable parent identity and content-hash provenance.

Profiles and Delivery Presets are distinct. X-Alpha25 and X-Alpha45 share the
same source profile; they do not duplicate waveform-system identity. Session
selection belongs to a Run Request, while product duration belongs to a
Delivery Preset.

The profile stores seven session-to-mode assignments as data: sessions 1–4 use
Baseline Mode, 5–6 use Dense Mode, and 7 uses Complex Mode. No Python branch
implements those assignments.
