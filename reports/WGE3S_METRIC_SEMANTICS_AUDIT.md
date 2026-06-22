# WGE-3S Metric-Semantics Audit

Status: completed before planner repair.

- Source and engine packets are equivalent: `packet_start` followed by
  continuations until the next start within a block/run.
- Source and engine events are equivalent metadata events. The Phase 4D
  `source_burst_rate_per_second` field is not an equivalent event-rate metric.
  Session 1's equivalent event rate is 14.8791/s, derived from packet count and
  packet-start event share.
- A canonical clean +1 sweep is an eight-event circular traversal. Nine events
  are not required by the reviewed authority.
- Canonical engine grammar mappings are explicit:
  - `clean_plus_one_sweep`: exactly eight events covering all channels once
    with seven circular +1 transitions;
  - `sweep_with_repeats`: at least four events, containing both circular +1
    and same-channel transitions and no other transition type;
  - `partial_sweep`: two through seven circular +1 events;
  - `scattered_packet`: multiple channels with at least one transition that is
    neither same-channel nor circular +1;
  - one-, two-, and three-impulse bursts: exactly one, two, or three
    same-channel events respectively.
- Source trailing spacing is a per-packet median that excludes the
  primary-to-first-continuation gap.
- Source cycle span includes the final event duration.
- Immediate motif repetition is exact-asset equality between globally adjacent
  events within a source block; the single generated run is comparable.
- Pulse Pattern prevalence uses the same packet denominator.
- Source schedule spectrum uses signed 10 ms waveform-activity means per
  channel. A packet-onset impulse spectrum is not equivalent and is now
  `not_assessable`.
- Source grammar proportions describe descriptive sweep windows that may
  contain multiple packet starts. They are not one-to-one local packet-label
  proportions and are now `not_assessable`; they remain provisional Tier 2
  planning guidance.

Planner changes are tied only to semantically valid evidence: direct Session 1
packet count and duration guide central packet rate; direct primary-gap and
trailing-spacing quantiles guide continuation timing; direct equivalent packet
denominators guide Pulse Pattern prevalence; equivalent source event rows guide
event rate; exact adjacent-asset equality guides motif repetition. Grammar
weights use aggregate descriptive windows only as explicitly provisional
builder guidance. Schedule spectrum and grammar-category qualification remain
`not_assessable` rather than being relabeled as agreement.

No blocked final-test material was accessed.
