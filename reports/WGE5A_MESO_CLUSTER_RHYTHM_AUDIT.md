# WGE-5A Meso-Cluster and Rhythmic-Phrasing Evidence Audit

Status: `WGE5A_MESO_CLUSTER_POLICY_READY`

The WGE-5A policy is now complete as a non-executable, Tier 2 advisory
specification. WGE-5A1 resolved the earlier evidence blocker by deriving
packet-start cluster statistics from permitted, hash-verified training and
validation event metadata referenced through
`phase5l_unit_grammar_audit_report`.

## Evidence resolution

Source packet starts are semantically comparable with engine packet starts:
one `packet_start` row begins a packet, continuations belong to that packet
until the next start, channel rows are merged within source blocks, and event
overlap does not alter the start population.

The derived populations contain:

- 752 direct Session 1 packet starts across 8 blocks;
- 6,112 Baseline Sessions 1–4 packet starts across 32 blocks;
- no simultaneous duplicate starts;
- training and validation partitions only;
- no blocked final-test access.

The full methods and statistics are recorded in
`reports/WGE5A1_SOURCE_CLUSTER_STATISTICS.md`.

## Cluster model

A fixed gap threshold is not supported. Mixture intersections and threshold
outcomes are unstable, and the aggregate Baseline population is
session-heterogeneous.

The selected model is a held-out recurrent interval phrase state. A phrase
window spans four packet starts and the three exact sample-aligned intervals
between them. Validation windows are active when their interval triple
occurred in the matching training population. Overlapping or adjacent active
spans merge into clusters.

This is a measurement model, not a source-sequence recipe. Future runtime may
use aggregate state transitions and target distributions only. Exact source
tuples and source block sequences may not be embedded or replayed.

## Source findings

Direct Session 1 validation has:

- phrase-active share `0.397554`;
- inactive→active probability `0.266667`;
- active→active probability `0.609375`;
- `15.3888` clusters per observed minute;
- cluster size p10/median/p90 `4 / 6 / 17.4` packets;
- cluster duration p10/median/p90
  `0.8213 / 1.5820 / 4.6676 s`;
- within-cluster interval p10/median/p90
  `0.2153 / 0.2819 / 0.3511 s`;
- between-cluster gap p10/median/p90
  `0.4422 / 0.7835 / 2.2062 s`;
- cluster-conditioned motif repetition `0.691517`;
- maximum concurrency 3.

Baseline Sessions 1–4 validation has phrase-active share `0.651550`,
active→active probability `0.828471`, and `15.7162` clusters per observed
minute. Its timing distributions are retained separately rather than
substituted for direct Session 1.

## Generated comparison

The existing generated plan remains unchanged. It has 149 packets, 960
events, and 146 three-interval windows. Every interval triple is unique and
none matches the direct Session 1 training phrase population, yielding zero
clusters under the selected model.

Its local interval CV is source-like, but phrase recurrence, serial
dependence, and packet-interval distribution are outside source reference.
This objectively supports the human observation that the plan is stochastic
but meso-flat.

## Interpretation and boundaries

The “hum–put put” interpretation remains:

- primary: repeated packet phrase;
- secondary: dense discrete packet texture;
- continuous component: unsupported.

No carrier, oscillator, fixed global lattice, source-sequence replay,
canonical grammar replacement, motif transformation, calibration change, or
Complex/Baseline conflation is authorized.

## Authorization

`wge5b_meso_cluster_implementation_authorized: true`

WGE-5B may begin only as a separate implementation phase. It must remain
profile-driven, deterministic, grammar-preserving, source-compared across
primary and holdout seeds, and non-replaying. Perceptual, headset,
production-duration, and binding-tolerance qualification remain unresolved.
