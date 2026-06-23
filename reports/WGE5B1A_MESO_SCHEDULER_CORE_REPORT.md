# WGE-5B1A Deterministic Meso Phrase Scheduler Core

Status: `WGE5B1A_MESO_SCHEDULER_CORE_READY`

## Architecture

The reusable `wave_generator_engine.meso` package produces a packet-onset
skeleton with phrase states, phrase records, packet membership, metrics, and
policy/seed provenance. It is not connected to the Session 1 planner.

The core controls only packet onset timing and meso phrase state. It has no
responsibility for packet grammar, motifs, event continuation timing, channel
assignment, Focus Role, calibration, rendering, or export.

## Qualified policy

The loader validates the Draft 2020-12 policy schema, canonical content hash,
qualification status, WGE-5B authorization, required Session 1 parameters,
fixed-threshold prohibition, and source scope. Unsupported scopes and
unresolved execution fields fail closed.

The scheduler consumes direct Session 1 aggregate parameters from
`x_alpha_meso_cluster_rhythm_policy_v1`. It does not reopen source timing
tables, rederive source statistics, store source interval triples, or replay
source block sequences.

## Phrase-state model

The core implements background and phrase-active states using:

- source-supported phrase-active share and cluster rate;
- source-supported initiation and continuation probabilities;
- bounded phrase-size and duration distributions;
- source-supported within-phrase interval quantiles;
- source-supported between-phrase gap quantiles.

Phrase records are contiguous, contain at least four packets, and terminate
before the next background span. A binary fixed-gap detector is not used.

## Determinism

Each schedule owns a local Python MT19937 RNG. The scheduler seed is derived
from the root seed, scheduler stage label, policy hash, and source scope using
the first 64 bits of SHA-256. Process-global random state is untouched.

Canonical JSON hashing makes identical requests byte-identical. Seeds
20260622, 20260623, and 20260624 produced three different valid hashes.

## Rate, duration, and boundaries

The API accepts exactly one caller constraint: packet count or packet rate.
Packet rate is deterministically rounded to a count; packet count is preserved
exactly.

Phrase intervals are sampled within policy bounds. The remaining onset-span
budget is reconciled only through bounded between-phrase gaps. No global
interval stretch is used, phrases are never silently truncated, and the final
boundary retains one caller-rate interval of margin.

## Anti-replay and anti-lattice

Hard validation rejects protected source dependency, embedded source tuples,
fixed intervals, repeated fixed cycles, inadequate interval diversity, narrow
onset-spectrum concentration, and absent local recurrent relationships.

Across the three 60-second synthetic schedules:

- unique interval counts were 146–148 of 148 intervals;
- interval CV was 0.739–0.963;
- maximum identical interval run was 1;
- onset-spectrum peak-power fraction was 0.0117–0.0155;
- lag-1 interval correlation was 0.602–0.670;
- phrase and background states both occurred.

Schedule spectra describe onset timing only and are not carrier frequencies.

## Synthetic validation

All three synthetic requests used 48 kHz, 60 seconds, and exactly 149 packets.
Each produced:

- 15 phrases, or 15 phrases/minute;
- phrase-active window share `0.397260`;
- median phrase size 7 packets;
- median phrase duration 1.606–1.692 seconds;
- median within-phrase interval 0.277–0.299 seconds;
- median between-phrase gap 1.340–1.903 seconds.

These are temporary in-memory scheduler tests. No production plan or full
onset schedule was persisted.

## Authorization

`wge5b1b_planner_integration_authorized: true`

The reusable core is ready for a separate WGE-5B1B integration phase. That
phase must preserve planner grammar, exact motifs, profile-driven selection,
deterministic holdouts, existing qualification, and all render/export
boundaries.
