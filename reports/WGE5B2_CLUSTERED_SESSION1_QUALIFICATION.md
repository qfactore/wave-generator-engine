# WGE-5B2 Clustered Session 1 Qualification

Status: `WGE5B2_CLUSTERED_SESSION1_QUALIFIED`

- Candidate: `runs/candidates/session_01_baseline_clustered_60s_v1`
- Verdict: `qualified_with_documented_caveats`
- WGE-5C authorized: `true`
- Approved first-audio run: unchanged

## Content invariance

- Required signature: `e3945f374c1daaf740a54903eb865d0e44aefe2dbc44a16b2ed1831ddab90307`
- Passed: `true`
- Packets/events: 149 / 960

## Gap semantics

- Phrase-boundary packet gap is source-equivalent. Candidate median: 1.8119 s; result: `near_source_reference`.
- Background-span duration excludes boundary intervals and is descriptive only.
- Empty-activity gaps are event-free intervals and have no qualified source distribution.

## Primary meso metrics

- Phrase-active share: 0.397260
- Phrases/minute: 15.000
- Median phrase size: 7.0 packets
- Median phrase duration: 1.7031 s
- Median within-phrase interval: 0.2796 s
- Median phrase-boundary gap: 1.8119 s
- Maximum concurrency: 3

## Qualification

The candidate passes direct Session 1 policy bands, existing source
qualification, content invariance, primary/holdout validation,
anti-lattice checks, and independent deterministic reruns.
The gap upper tail and reduced phrase-size upper tail are retained as
documented Tier 2 caveats rather than hidden or retuned.
