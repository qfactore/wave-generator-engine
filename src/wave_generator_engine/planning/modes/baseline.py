from typing import Any

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.planning.hashing import content_hash
from wave_generator_engine.planning.seeds import derive_seed, local_rng


def _weighted_choice(rng, weights: dict[str, float]) -> str:
    names = list(weights)
    return rng.choices(names, weights=[weights[name] for name in names], k=1)[0]


def _channels(grammar: str, start: int, rng) -> list[int]:
    if grammar == "clean_plus_one_sweep":
        return [(start + offset) % 8 for offset in range(8)]
    if grammar == "sweep_with_repeats":
        sequence = [(start + offset) % 8 for offset in range(6)]
        sequence.insert(3, sequence[2])
        return sequence
    if grammar == "partial_sweep":
        length = rng.choice([3, 4, 5, 6, 7])
        return [(start + offset) % 8 for offset in range(length)]
    if grammar == "scattered_packet":
        length = rng.choice([3, 4, 5])
        result = [start]
        while len(result) < length:
            candidate = rng.randrange(8)
            if candidate != result[-1]:
                result.append(candidate)
        return result
    burst_count = {
        "one_impulse_burst": 1,
        "two_impulse_burst": 2,
        "three_impulse_burst": 3,
    }[grammar]
    return [start] * burst_count


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
        packet_interval = defaults["packet_interval_seconds"]["value"]
        spacing = defaults["continuation_spacing_seconds"]["value"]
        weights = defaults["grammar_weights"]["value"]
        pulse_fraction = planning_profile["numeric_guidance_used"][
            "fraction_with_trailing_events"
        ]["value"]
        packet_count = int(duration_seconds / packet_interval)
        duration_samples = duration_seconds * sample_rate_hz
        packet_seed = derive_seed(root_seed, f"session:{session_id}", "packet_grammar")
        channel_seed = derive_seed(root_seed, f"session:{session_id}", "channel_grammar")
        motif_seed = derive_seed(root_seed, f"session:{session_id}", "motif_selection")
        pulse_seed = derive_seed(root_seed, f"session:{session_id}", "pulse_pattern")
        packet_rng = local_rng(root_seed, f"session:{session_id}", "packet_grammar")
        channel_rng = local_rng(root_seed, f"session:{session_id}", "channel_grammar")
        motif_rng = local_rng(root_seed, f"session:{session_id}", "motif_selection")
        pulse_rng = local_rng(root_seed, f"session:{session_id}", "pulse_pattern")
        motifs = {item["motif_id"]: item for item in motif_metadata}
        motif_ids = [item["motif_id"] for item in motif_metadata]
        if len(motif_ids) != 84:
            raise ValidationFailure("Baseline planning requires 84 frozen motif identities")
        packets: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        previous_motif: str | None = None
        for packet_index in range(packet_count):
            packet_id = f"s{session_id:02d}_p{packet_index:04d}"
            grammar = _weighted_choice(packet_rng, weights)
            start_weights = [2.0 if channel == focus_role_target else 1.0 for channel in range(8)]
            start_channel = channel_rng.choices(range(8), weights=start_weights, k=1)[0]
            sequence = _channels(grammar, start_channel, channel_rng)
            has_continuations = pulse_rng.random() < pulse_fraction
            if not has_continuations:
                sequence = sequence[:1]
            onset_base = round(packet_index * packet_interval * sample_rate_hz)
            packet_events: list[str] = []
            for unit_index, channel in enumerate(sequence):
                candidates = motif_ids if previous_motif is None else [
                    item for item in motif_ids if item != previous_motif
                ]
                motif_id = motif_rng.choice(candidates)
                metadata = motifs[motif_id]
                onset = onset_base + round(unit_index * spacing * sample_rate_hz)
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
                    "identity_mode": "exact_frozen_identity",
                    "relative_event_gain": 1.0,
                    "gain_source": "provisional_identity_1_0",
                    "random_selection_trace": {
                        "packet_seed": packet_seed,
                        "channel_seed": channel_seed,
                        "motif_seed": motif_seed,
                        "pulse_seed": pulse_seed,
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
                "authority_references": ["canonical_unit_grammar_terms"],
            })
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
                "packet_grammar": packet_seed,
                "pulse_pattern": pulse_seed,
                "channel_grammar": channel_seed,
                "motif_selection": motif_seed,
            },
            "seed_derivation": "sha256_first_64_bits",
        }
        return packet_plan, event_plan, seeds
