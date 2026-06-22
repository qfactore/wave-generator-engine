from typing import Any

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.planning.hashing import content_hash
from wave_generator_engine.planning.seeds import derive_seed, local_rng


def _weighted_choice(rng, weights: dict[str, float]) -> str:
    names = list(weights)
    return rng.choices(names, weights=[weights[name] for name in names], k=1)[0]


def _channels(
    grammar: str, start: int, rng, event_counts: dict[str, list[int]]
) -> list[int]:
    length = rng.choice(event_counts[grammar])
    if grammar == "clean_plus_one_sweep":
        return [(start + offset) % 8 for offset in range(length)]
    if grammar == "sweep_with_repeats":
        sequence = [(start + offset) % 8 for offset in range(length - 1)]
        sequence.insert(3, sequence[2])
        return sequence
    if grammar == "partial_sweep":
        return [(start + offset) % 8 for offset in range(length)]
    if grammar == "scattered_packet":
        result = [start]
        disruptive_index = rng.randrange(1, length)
        while len(result) < length:
            step = (
                rng.choice([2, 3, 7]) if len(result) == disruptive_index
                else rng.choice([0, 1, 1, 1, 2, 7])
            )
            result.append((result[-1] + step) % 8)
        if len(set(result)) < 2:
            result[-1] = (result[-1] + 2) % 8
        return result
    return [start] * length


def _seconds_to_samples(value: float, sample_rate_hz: int) -> int:
    return max(1, round(value * sample_rate_hz))


def _draw_range(rng, policy: dict[str, Any], sample_rate_hz: int) -> int:
    return _seconds_to_samples(
        rng.uniform(policy["minimum"], policy["maximum"]), sample_rate_hz
    )


def _spacing_family(grammar: str) -> str:
    if grammar.endswith("_impulse_burst"):
        return "burst"
    if grammar == "scattered_packet":
        return "scattered"
    return "sweep"


class BaselinePlanner:
    mode = "baseline"

    def plan(
        self,
        *,
        session_id: int,
        duration_seconds: int,
        sample_rate_hz: int,
        root_seed: int,
        focus_role_target: int,
        planning_profile: dict[str, Any],
        motif_metadata: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        defaults = planning_profile["provisional_defaults"]
        packet_interval_policy = defaults["packet_interval_distribution"]["value"]
        primary_gap_policy = defaults["primary_to_trailing_gap_distribution"]["value"]
        spacing_policies = defaults["continuation_spacing_distributions"]["value"]
        weights = defaults["grammar_weights"]["value"]
        event_counts = defaults["grammar_event_counts"]["value"]
        pulse_fraction = defaults["pulse_pattern_prevalence"]["value"]
        repeat_probability = defaults["immediate_motif_repeat_probability"]["value"]
        duration_samples = duration_seconds * sample_rate_hz
        packet_seed = derive_seed(root_seed, f"session:{session_id}", "packet_timing_and_grammar")
        channel_seed = derive_seed(root_seed, f"session:{session_id}", "channel_grammar")
        timing_seed = derive_seed(root_seed, f"session:{session_id}", "continuation_timing")
        motif_seed = derive_seed(root_seed, f"session:{session_id}", "motif_selection")
        pulse_seed = derive_seed(root_seed, f"session:{session_id}", "pulse_pattern_presence")
        packet_rng = local_rng(root_seed, f"session:{session_id}", "packet_timing_and_grammar")
        channel_rng = local_rng(root_seed, f"session:{session_id}", "channel_grammar")
        timing_rng = local_rng(root_seed, f"session:{session_id}", "continuation_timing")
        motif_rng = local_rng(root_seed, f"session:{session_id}", "motif_selection")
        pulse_rng = local_rng(root_seed, f"session:{session_id}", "pulse_pattern_presence")
        motifs = {item["motif_id"]: item for item in motif_metadata}
        motif_ids = [item["motif_id"] for item in motif_metadata]
        if len(motif_ids) != 84:
            raise ValidationFailure("Baseline planning requires 84 frozen motif identities")
        packets: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        previous_motif: str | None = None
        packet_index = 0
        onset_base = 0
        while onset_base < duration_samples:
            packet_id = f"s{session_id:02d}_p{packet_index:04d}"
            has_continuations = pulse_rng.random() < pulse_fraction
            grammar = (
                _weighted_choice(packet_rng, weights)
                if has_continuations else "one_impulse_burst"
            )
            start_weights = [2.0 if channel == focus_role_target else 1.0 for channel in range(8)]
            start_channel = channel_rng.choices(range(8), weights=start_weights, k=1)[0]
            sequence = _channels(grammar, start_channel, channel_rng, event_counts)
            spacing_family = _spacing_family(grammar)
            spacings = []
            if len(sequence) > 1:
                spacings.append(_draw_range(timing_rng, primary_gap_policy, sample_rate_hz))
                spacings.extend(
                    _draw_range(
                        timing_rng, spacing_policies[spacing_family], sample_rate_hz
                    )
                    for _ in range(max(0, len(sequence) - 2))
                )
            relative_onsets = [0]
            for spacing in spacings:
                relative_onsets.append(relative_onsets[-1] + spacing)
            maximum_motif_duration = max(int(item["shape"][0]) for item in motif_metadata)
            if onset_base + relative_onsets[-1] + maximum_motif_duration > duration_samples:
                break
            packet_events: list[str] = []
            for unit_index, channel in enumerate(sequence):
                repeat_selected = (
                    previous_motif is not None
                    and motif_rng.random() < repeat_probability
                )
                candidates = (
                    [previous_motif] if repeat_selected
                    else motif_ids if previous_motif is None
                    else [item for item in motif_ids if item != previous_motif]
                )
                motif_id = motif_rng.choice(candidates)
                metadata = motifs[motif_id]
                onset = onset_base + relative_onsets[unit_index]
                motif_duration = int(metadata["shape"][0])
                if onset + motif_duration > duration_samples:
                    break
                event_id = f"{packet_id}_e{unit_index:02d}"
                event = {
                    "event_id": event_id,
                    "session_id": session_id,
                    "packet_id": packet_id,
                    "unit_id": f"{packet_id}_u{unit_index:02d}",
                    "unit_grammar": grammar,
                    "pulse_role": "packet_start" if unit_index == 0 else "packet_continuation",
                    "onset_sample": onset,
                    "duration_samples": motif_duration,
                    "end_sample_exclusive": onset + motif_duration,
                    "logical_channel": channel,
                    "channel_role": "focus" if channel == focus_role_target else "support",
                    "motif_id": motif_id,
                    "motif_hash": metadata["per_motif_sha256"],
                    "motif_source_order": metadata["ordered_index"],
                    "motif_selection_mode": (
                        "adjacent_source_guided_repeat"
                        if repeat_selected else "eligible_identity_draw"
                    ),
                    "identity_mode": "exact_frozen_identity",
                    "relative_event_gain": 1.0,
                    "gain_source": "provisional_identity_1_0",
                    "random_selection_trace": {
                        "packet_stage_seed": packet_seed,
                        "channel_stage_seed": channel_seed,
                        "continuation_timing_stage_seed": timing_seed,
                        "motif_stage_seed": motif_seed,
                        "pulse_stage_seed": pulse_seed,
                        "packet_index": packet_index,
                        "unit_index": unit_index,
                    },
                    "authority_references": [
                        "canonical_unit_grammar_terms",
                        "x_alpha_pulse_pattern_grammar_v1",
                        "frozen_motif_identity_index",
                    ],
                }
                events.append(event)
                packet_events.append(event_id)
                previous_motif = motif_id
            packets.append({
                "packet_id": packet_id,
                "session_id": session_id,
                "packet_index": packet_index,
                "onset_sample": onset_base,
                "unit_grammar": grammar,
                "channel_sequence": sequence[:len(packet_events)],
                "event_ids": packet_events,
                "continuation_count": max(0, len(packet_events) - 1),
                "pulse_pattern_present": len(packet_events) > 1,
                "continuation_spacings_samples": spacings[:max(0, len(packet_events) - 1)],
                "timing_policy": {
                    "packet_interval": "provisional_stochastic_uniform",
                    "continuation_family": spacing_family,
                    "primary_to_trailing_gap": "direct_session_profile_uniform",
                    "continuation_spacing": "direct_session_grammar_aware_uniform",
                },
                "authority_references": ["canonical_unit_grammar_terms"],
            })
            interval = _draw_range(packet_rng, packet_interval_policy, sample_rate_hz)
            onset_base += interval
            packet_index += 1
        packet_plan = {
            "schema_version": "wge.packet_plan.v1",
            "packet_plan_id": f"session_{session_id:02d}_packets",
            "mode": "baseline",
            "packets": packets,
            "pulse_pattern_plan": {
                "schema_version": "wge.pulse_pattern_plan.v1",
                "definition": "packet start followed by zero or more continuation events until the next packet start",
                "packet_roles": [
                    {
                        "packet_id": item["packet_id"],
                        "continuation_count": item["continuation_count"],
                        "pulse_pattern_present": item["pulse_pattern_present"],
                    }
                    for item in packets
                ],
                "content_hash": "",
            },
            "channel_unit_plan": {
                "schema_version": "wge.channel_unit_plan.v1",
                "channel_convention": "zero_based_0_7",
                "units": [
                    {
                        "packet_id": item["packet_id"],
                        "unit_grammar": item["unit_grammar"],
                        "channel_sequence": item["channel_sequence"],
                    }
                    for item in packets
                ],
                "content_hash": "",
            },
            "content_hash": "",
        }
        packet_plan["pulse_pattern_plan"]["content_hash"] = content_hash(
            packet_plan["pulse_pattern_plan"]
        )
        packet_plan["channel_unit_plan"]["content_hash"] = content_hash(
            packet_plan["channel_unit_plan"]
        )
        packet_plan["content_hash"] = content_hash(packet_plan)
        event_plan = {
            "schema_version": "wge.event_plan.v1",
            "event_plan_id": f"session_{session_id:02d}_events",
            "session_id": session_id,
            "sample_rate_hz": sample_rate_hz,
            "duration_samples": duration_samples,
            "events": events,
            "contains_waveform_samples": False,
            "calibration_applied": False,
            "playback_intensity_applied": False,
            "content_hash": "",
        }
        event_plan["content_hash"] = content_hash(event_plan)
        seeds = {
            "random_algorithm": "python_random_mt19937_local",
            "root_seed": root_seed,
            "session_seed": derive_seed(root_seed, f"session:{session_id}"),
            "stage_seeds": {
                "packet_timing_and_grammar": packet_seed,
                "pulse_pattern_presence": pulse_seed,
                "channel_grammar": channel_seed,
                "continuation_timing": timing_seed,
                "motif_selection": motif_seed,
            },
            "seed_derivation": "sha256_first_64_bits",
        }
        return packet_plan, event_plan, seeds
