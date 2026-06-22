# Session 1 Source Planning Profile

`x_alpha_session_01_baseline_v1` is a locked, non-user-editable planning
overlay for `x_alpha_standard_v1` Session 1. It is keyed to the source profile's
content hash and selected through `profiles/planning_profiles/registry.json`.

The overlay records direct Session 1 packet-rate, Pulse Pattern, primary-gap,
and continuation-timing evidence. Baseline aggregate sweep-window and novelty
evidence provide provisional grammar weighting and exact-asset repetition
guidance. Every parameter records unit, authority tier, artifact, field, scope,
binding status, provisional status, and rationale.

The common Baseline planner consumes the overlay. Sessions 2–4 do not inherit
its direct Session 1 values. Focus Role remains a run-request role mapping.
Motif samples, calibration, and playback intensity are untouched.
