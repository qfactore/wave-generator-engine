# Run Requests

A Run Request selects a Source Profile, Delivery Preset, one or more of the
seven sessions, a positive duration, optional permitted metadata overrides, and
a requested future export target.

Validation checks references, sessions, duration, playback safety, Focus Role
permission, and exact-mode blocks. Export targets remain non-executable. A valid
request is only a validated document; it creates no SessionPlan or RenderPlan.
