# WGE-5B1B Session 1 Baseline Planner Integration

Status: `WGE5B1B_PLANNER_INTEGRATION_READY`

## Integration architecture

The locked Session 1 planning overlay now selects the qualified meso policy,
direct Session 1 source scope, scheduler mode, seed namespace, and exact
caller-rate packet-count reconciliation. The common Baseline planner consumes
that profile data and requests a packet-onset skeleton before applying its
existing packet grammar and content decisions.

There is no Session 1 branch in planner code. Sessions 2–4 have no meso
activation record and remain on their existing path.

## Timing-only control

The meso scheduler controls packet onset samples, inter-packet intervals,
phrase states, membership annotations, and timing-derived event overlap. It
does not control grammar, continuation offsets, motifs, gains, channels,
Focus Role, calibration, rendering, or export.

The candidate packet and session plans carry minimal policy identity, result
hash, seed provenance, phrase summary, membership summary, and anti-lattice
status. Legacy plans without this metadata remain valid and are not silently
reinterpreted.

## RNG isolation

The meso scheduler uses a dedicated SHA-derived substream rooted in the
profile seed namespace. Packet content retains the prior deterministic content
stream. A compatibility-only legacy packet-interval draw advances that stream
exactly as before but does not control candidate timing.

Changing only the meso seed namespace changes packet timing while preserving
packet IDs, grammar, channels, continuation offsets, motifs, gains, and event
content. Process-global RNG state is unchanged.

## Primary candidate

The 60-second, 48 kHz, seed-20260622 candidate was generated in memory:

- 149 packets and 960 real grammar events;
- packet rate `2.48333/s`, event rate `16.0/s`;
- 15 phrases/minute;
- phrase-active share `0.397260`;
- median phrase size 7 packets;
- median phrase duration `1.7031 s`;
- median within-phrase interval `0.2796 s`;
- median between-phrase gap `1.8119 s`;
- interval lag-1 correlation `0.5346`;
- 147 unique intervals, CV `0.8248`;
- maximum identical interval run 1;
- onset-spectrum peak-power fraction `0.0178`;
- Pulse Pattern prevalence `0.979866`;
- 83 unique motifs and immediate repetition `0.519291`;
- maximum concurrency 3.

The within-phrase and duration medians are near direct Session 1 centres. The
gap median remains inside the qualified empirical envelope without exact-value
forcing.

## Content invariance

The published current plan and primary candidate have the same non-timing
content signature:

`e3945f374c1daaf740a54903eb865d0e44aefe2dbc44a16b2ed1831ddab90307`

All 149 packet-content records and all 960 event-content records match. The
integration changes 148 packet onsets and 952 derived event onsets.

## Holdouts

Seeds 20260623 and 20260624 each produced 149 valid packets, 15 phrases,
phrase-active share `0.397260`, source-envelope timing metrics, high interval
diversity, nonzero serial dependence, and maximum concurrency 4. Same-seed
reruns are identical; different seeds differ.

## Existing guardrails

Canonical grammar, Pulse Pattern, motif identity and diversity, motif
repetition, channel assignment, Focus Role, relative gain, event bounds, and
anti-lattice checks pass. The primary 960-event sequence is unchanged.

No complete candidate plan or onset schedule is persisted. `runs/latest` and
the four diagnostic WAV files remain byte-identical.

## Authorization

`wge5b2_candidate_regeneration_authorized: true`

WGE-5B2 may separately regenerate and qualify a candidate run. It was not
started in this phase.
