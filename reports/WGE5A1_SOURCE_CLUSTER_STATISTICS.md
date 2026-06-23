# WGE-5A1 Source Packet-Start Cluster Statistics

Status: `complete`

WGE-5A1 establishes a semantically comparable packet-start population and a
held-out, state-based description of meso phrasing. It does not select an
arbitrary gap threshold, modify the planner, or implement WGE-5B.

## Evidence and packet semantics

The permitted Tier 2 parent artifact is
`phase5l_unit_grammar_audit_report`. Its hash-inventoried Phase 5C training and
validation event tables are classified audit-only and contain packet position,
sample-aligned event starts and ends, channel, asset, split, session, and
source-block metadata. Their SHA-256 hashes were reverified.

A `packet_start` row begins one source packet. Following continuation rows
belong to it until the next packet start in the same source block. Channel rows
are merged and sorted within a block. Event overlap does not create or merge
packet starts, and no measurement crosses a block or session boundary.

- Direct Session 1: 752 packet starts (413 training, 339 validation), 8 blocks.
- Baseline Sessions 1–4: 6,112 starts (3,418 training, 2,694 validation),
  32 blocks.
- Simultaneous duplicate packet starts: 0 in both populations.

The prior 12,376-sample threshold remains prohibited as a meso boundary. It
groups same-channel source bursts into source packets.

## Boundary analysis

Inter-packet quantiles, deterministic log-Gaussian mixture fits, component
intersection sensitivity, and threshold sensitivity do not support one fixed
gap threshold. Session 1 is mostly unimodal, mixture intersections shift with
component count, and pooled Baseline timing is heterogeneous across sessions.

The selected advisory model is a
`probabilistic_recurrent_interval_phrase_state`:

1. A phrase window contains three exact sample-aligned intervals spanning four
   packet starts.
2. Training triples form a measurement-only reference dictionary.
3. A held-out validation window is active when its triple occurred in the
   corresponding training population.
4. Overlapping or adjacent active-window packet spans merge into one cluster.

Future runtime may use only aggregate transition probabilities and target
distributions. It may not embed or replay source tuples or block sequences.

## Direct Session 1 validation

- Phrase-active validation windows: 130/327 (`0.397554`).
- State transitions: inactive→active `0.266667`; active→active `0.609375`.
- 24 clusters across 93.5744 seconds of observed block support:
  `15.3888` clusters per observed minute.
- Packets per cluster: p10/median/p90 `4 / 6 / 17.4`.
- Cluster onset span: p10/median/p90
  `0.8213 / 1.5820 / 4.6676 s`.
- Within-cluster packet interval: p10/median/p90
  `0.2153 / 0.2819 / 0.3511 s`.
- Between-cluster onset gap: p10/median/p90
  `0.4422 / 0.7835 / 2.2062 s`.
- Cluster onset-span occupancy: `0.704542`.
- Quiet-gap onset-span occupancy: `0.252784`.
- Events per cluster: p10/median/p90 `24.2 / 40 / 106.7`.
- Exact adjacent motif repetition in clusters: `0.691517`.
- Cluster channel transitions:
  same `0.844473`, +1 `0.149743`, reverse `0.003213`, skip `0.002571`.
- Maximum concurrency: 3; overlap duration: `0.270417 s`.

## Baseline Sessions 1–4 validation

- Phrase-active validation windows: 1,724/2,646 (`0.651550`).
- State transitions: inactive→active `0.330786`; active→active `0.828471`.
- 97 clusters across 370.3197 seconds of observed block support:
  `15.7162` clusters per observed minute.
- Packets per cluster: p10/median/p90 `4 / 12 / 65`.
- Cluster onset span: p10/median/p90
  `0.5880 / 1.5820 / 6.9895 s`.
- Within-cluster packet interval: p10/median/p90
  `0.0350 / 0.1080 / 0.2410 s`.
- Between-cluster onset gap: p10/median/p90
  `0.1040 / 0.4349 / 1.7858 s`.
- Cluster onset-span occupancy: `0.824401`.
- Quiet-gap onset-span occupancy: `0.144834`.
- Exact adjacent motif repetition in clusters: `0.492686`.
- Maximum concurrency: 3.

Aggregate Baseline values are reported separately because Sessions 1–4 have
different timing populations. They are not substituted for direct Session 1.

## Rhythmic phrase findings

Exact three-interval recurrence is substantial in source data: repeated
occurrences account for `0.549451` of direct Session 1 source windows and
`0.712600` of aggregate Baseline source windows. Session 1 interval lag
correlations also differ materially from the generated plan. These findings
support local recurrent packet phrases, not a global periodic lattice.

The “hum–put put” interpretation remains:

- primary: repeated packet phrase;
- secondary: dense discrete packet texture;
- continuous component: unsupported.

## Existing generated plan

The unchanged 60-second generated plan has 149 packet starts and 146
three-interval windows. Every generated triple is unique and none matches the
direct Session 1 source phrase dictionary. It therefore has zero phrase-state
clusters under this measurement model.

Local interval variability is similar to source, but recurrence, serial
dependence, and packet-interval distribution are outside source reference.
This quantifies the existing human observation that the plan is stochastic
yet meso-flat.

## Authorization

`wge5b_meso_cluster_implementation_authorized: true`

The evidence now supports a non-executable advisory policy for future WGE-5B:
cluster initiation and persistence, cluster size and duration, within-cluster
timing, between-cluster gaps, density occupancy, motif repetition, channel
transitions, overlap, deterministic holdouts, and anti-lattice gates are all
measurable with explicit provenance.

WGE-5B must remain profile-driven, preserve canonical packet grammar, avoid
exact source replay, and perform its own primary/holdout qualification.
