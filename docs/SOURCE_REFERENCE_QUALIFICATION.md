# Source-Reference Qualification

WGE-3Q compares an immutable metadata plan with permitted, hash-verified source
references discovered through Interchange manifests. It does not inspect
blocked recordings or final-test arrays, regenerate a plan, or render audio.

Evidence priority is direct Session 1 metrics, Baseline Sessions 1–4 aggregate
metrics, Tier 2 distributions, then engine provisional policy. Aggregate
evidence is never presented as direct Session 1 evidence. Missing raw schedules
produce `not_assessable`; synthetic source observations are not created.

Metric results are `within_source_reference`, `near_source_reference`,
`outside_source_reference`, or `not_assessable`. Tier 1 structural rules remain
binding. Tier 2 distributions and diagnostic divergence bands remain advisory.
The verdict separately records whether WGE-4 is authorized.

Packet-onset spectrum is a statistic of schedule timing. It is not a continuous
carrier frequency and must never be labelled as one.
