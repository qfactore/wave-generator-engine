# Meso-Cluster and Rhythmic-Phrasing Model

WGE-5A defines the intended planning layer between canonical packet grammar
and long-session macro evolution. WGE-5A1 supplies a held-out source-derived
measurement model and advisory target distributions. The policy remains
non-executable.

## Layer boundary

A meso phrase is a local group of two or more canonical packets. It may
coordinate packet-onset timing, grammar selection, motif reuse, channel
transitions, and permitted overlap. It does not replace packet grammar, alter
frozen motifs, change calibration, or introduce a waveform component.

Micro timing remains inside motifs and packets. Packet structure remains one
start plus continuations. Macro state scheduling remains a separate mode-level
architecture. In particular, Complex Mode deep gaps are not a shortcut for
Baseline phrasing.

## Evidence-supported shape

The source architecture supports stochastic renewal timing with a rate
trajectory and limited serial dependence. Baseline evidence supports
continuation-heavy clean stepping and substantial exact motif repetition.
Hum/put-put guidance identifies timing plus duration as the strongest
diagnostic and treats density contrast, compression, gain, and overlap as
coordinated dimensions.

That evidence supports future local packet phrases, not a global metronome.
Local quasi-periodicity may emerge within a phrase, but each phrase must retain
interval variation and stochastic transitions.

## Source-derived phrase state

Permitted, hash-verified training and validation event metadata establishes a
source-equivalent packet-start population. A packet begins at a
`packet_start` row and includes following continuations until the next start
in the same source block. Channels are merged within a block; overlap does not
create or merge starts.

A fixed packet-gap threshold is not defensible: mixture boundaries and cluster
counts are threshold-sensitive, while aggregate Baseline timing is
session-heterogeneous. The advisory model therefore uses recurrent phrase
states:

1. three exact sample-aligned intervals span a four-packet phrase window;
2. training interval triples form a measurement-only dictionary;
3. held-out validation windows are active when their triple recurred in
   training;
4. overlapping or adjacent active packet spans merge into clusters.

Direct Session 1 validation provides phrase initiation and continuation
probabilities, cluster rate, cluster size and duration, within-cluster timing,
between-cluster gaps, occupancy, motif repetition, channel transitions, and
overlap. Baseline Sessions 1–4 statistics remain a separate aggregate
reference.

Exact source triples are not runtime vocabulary. WGE-5B may consume only
aggregate state transitions and target distributions; it may not embed or
replay source tuples or source block sequences.

## Generated limitation

The existing 60-second plan is stochastic at the packet level but has no
recurrent three-interval phrase and no direct Session 1 source-matched phrase
window under the held-out measurement model. Human listening and the source
comparison therefore agree that higher-order grouping is missing.

The direct Session 1 12,376-sample threshold still cannot be used as a meso
cutoff: it groups same-channel source bursts into packets. Complex Mode
plateau/gap targets also remain non-transferable to Baseline.

## Carrier boundary

The perceived hum-like continuity is most consistently explained as repeated
packet phrasing and dense discrete texture. Schedule spectra are not carrier
frequencies, and no continuous oscillator is certified or proposed.

## Implementation authorization

WGE-5B is authorized as a future, separate implementation phase. It must use
versioned profile data, deterministic stage seeds, at least two holdout seeds,
no exact source sequence, no fixed global rhythm, canonical packet grammar,
and no planner changes outside the new meso modulation layer. WGE-5A1 itself
does not implement that layer.
