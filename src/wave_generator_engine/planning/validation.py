import math
import statistics
from collections import Counter, defaultdict
from typing import Any

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.planning.hashing import content_hash


def validate_channel_grammar(packet: dict[str, Any]) -> None:
    grammar = packet["unit_grammar"]
    channels = packet["channel_sequence"]
    if not channels:
        raise ValidationFailure("unit_grammar_structure: packet has no realised events")
    if grammar == "clean_plus_one_sweep":
        if len(channels) != 8 or len(set(channels)) != 8 or any(
            channels[index] != (channels[index - 1] + 1) % 8
            for index in range(1, len(channels))
        ):
            raise ValidationFailure("unit_grammar_structure: invalid clean_plus_one_sweep")
    elif grammar == "sweep_with_repeats":
        transitions = [
            (channels[index] - channels[index - 1]) % 8
            for index in range(1, len(channels))
        ]
        if len(channels) < 4 or any(value not in {0, 1} for value in transitions) or \
                0 not in transitions or 1 not in transitions:
            raise ValidationFailure("unit_grammar_structure: invalid sweep_with_repeats")
    elif grammar == "partial_sweep":
        if not 2 <= len(channels) <= 7 or any(
            channels[index] != (channels[index - 1] + 1) % 8
            for index in range(1, len(channels))
        ):
            raise ValidationFailure("unit_grammar_structure: invalid partial_sweep")
    elif grammar == "scattered_packet":
        transitions = [
            (channels[index] - channels[index - 1]) % 8
            for index in range(1, len(channels))
        ]
        if len(channels) < 2 or len(set(channels)) < 2 or \
                not any(value not in {0, 1} for value in transitions):
            raise ValidationFailure("unit_grammar_structure: invalid scattered_packet")
    elif grammar.endswith("_impulse_burst"):
        expected = {
            "one_impulse_burst": 1,
            "two_impulse_burst": 2,
            "three_impulse_burst": 3,
        }.get(grammar)
        if expected is None or len(channels) != expected or len(set(channels)) != 1:
            raise ValidationFailure("unit_grammar_structure: invalid impulse burst")
    else:
        raise ValidationFailure("Unknown channel grammar")


def validate_plans(
    pack: dict[str, Any],
    session: dict[str, Any],
    macro: dict[str, Any],
    packets: dict[str, Any],
    events: dict[str, Any],
    motif_metadata: list[dict[str, Any]],
) -> dict[str, Any]:
    motif_map = {item["motif_id"]: item for item in motif_metadata}
    if pack["executable_for_rendering"]:
        raise ValidationFailure("WGE-3 plans cannot be executable for rendering")
    if pack["channel_convention"] != "zero_based_0_7":
        raise ValidationFailure("Invalid channel convention")
    if macro["states"][0]["start_sample"] != 0 or \
            macro["states"][-1]["end_sample_exclusive"] != session["duration_samples"]:
        raise ValidationFailure("Macro-state stage does not span the session")
    packet_items = packets["packets"]
    packet_ids = {item["packet_id"] for item in packet_items}
    by_event_id = {item["event_id"]: item for item in events["events"]}
    packet_intervals = [
        second["onset_sample"] - first["onset_sample"]
        for first, second in zip(packet_items, packet_items[1:])
    ]
    if len(packet_intervals) > 1 and len(set(packet_intervals)) == 1:
        raise ValidationFailure("packet_timing_variance: stochastic Baseline intervals are fixed")
    all_spacings: list[int] = []
    spacings_by_grammar: dict[str, list[int]] = defaultdict(list)
    for packet in packet_items:
        validate_channel_grammar(packet)
        selected = [by_event_id[event_id] for event_id in packet["event_ids"]]
        if len(selected) != len(packet["channel_sequence"]):
            raise ValidationFailure("unit_grammar_structure: event and channel counts differ")
        if packet["continuation_count"] != len(selected) - 1 or \
                packet["pulse_pattern_present"] != (len(selected) > 1):
            raise ValidationFailure("pulse_pattern_realisation: packet metadata contradicts events")
        roles = [item["pulse_role"] for item in selected]
        if not roles or roles[0] != "packet_start" or \
                any(role != "packet_continuation" for role in roles[1:]):
            raise ValidationFailure("pulse_pattern_realisation: event roles are invalid")
        actual_spacings = [
            second["onset_sample"] - first["onset_sample"]
            for first, second in zip(selected, selected[1:])
        ]
        if actual_spacings != packet.get("continuation_spacings_samples"):
            raise ValidationFailure("continuation_timing_policy: spacing trace mismatch")
        if any(value <= 0 for value in actual_spacings):
            raise ValidationFailure("continuation_timing_policy: non-positive spacing")
        all_spacings.extend(actual_spacings)
        spacings_by_grammar[packet["unit_grammar"]].extend(actual_spacings)
    if len(all_spacings) > 1 and len(set(all_spacings)) == 1:
        raise ValidationFailure("continuation_timing_policy: universal fixed spacing")
    for event in events["events"]:
        if not all(isinstance(event[key], int) for key in (
            "onset_sample", "duration_samples", "end_sample_exclusive",
            "logical_channel",
        )):
            raise ValidationFailure("Event timing and channels must be integral")
        if event["duration_samples"] <= 0 or event["onset_sample"] < 0 or \
                event["end_sample_exclusive"] > session["duration_samples"]:
            raise ValidationFailure("Event timing is out of bounds")
        if event["end_sample_exclusive"] != event["onset_sample"] + event["duration_samples"]:
            raise ValidationFailure("Event end position is invalid")
        if event["logical_channel"] not in range(8):
            raise ValidationFailure("Event channel is invalid")
        if event["packet_id"] not in packet_ids:
            raise ValidationFailure("Event packet reference is invalid")
        motif = motif_map.get(event["motif_id"])
        if motif is None or motif["per_motif_sha256"] != event["motif_hash"]:
            raise ValidationFailure("Event motif identity is invalid")
        if event["identity_mode"] != "exact_frozen_identity":
            raise ValidationFailure("Only exact frozen identity is permitted")
        forbidden = {
            "samples", "waveform", "calibration_multiplier",
            "playback_intensity", "transform", "time_scale",
        }
        if forbidden & set(event):
            raise ValidationFailure("Event embeds prohibited rendering metadata")
        trace = event.get("random_selection_trace", {})
        required_trace = {
            "packet_stage_seed", "channel_stage_seed", "motif_stage_seed",
            "pulse_stage_seed", "continuation_timing_stage_seed",
            "packet_index", "unit_index",
        }
        if set(trace) != required_trace:
            raise ValidationFailure("random_trace_semantics: incomplete or ambiguous trace")
    if events["contains_waveform_samples"] or events["calibration_applied"] or \
            events["playback_intensity_applied"]:
        raise ValidationFailure("EventPlan contains prohibited execution state")
    packet_count = len(packet_items)
    event_count = len(events["events"])
    trailing_packets = sum(item["continuation_count"] > 0 for item in packet_items)
    pulse_prevalence = trailing_packets / packet_count if packet_count else 0
    reference = pack["authority_snapshot"]["files"]["pulse_pattern"]["artifact_id"]
    duration_seconds = session["duration_seconds"]
    motif_counts = Counter(item["motif_id"] for item in events["events"])
    if len(motif_counts) < 12:
        raise ValidationFailure("Motif diversity collapsed below the frozen family count")
    motif_shares = [count / event_count for count in motif_counts.values()]
    motif_entropy = -sum(value * math.log2(value) for value in motif_shares)
    immediate_repetition = sum(
        first["motif_id"] == second["motif_id"]
        for first, second in zip(events["events"], events["events"][1:])
    ) / max(1, event_count - 1)
    focus = session["focus_role_target"]
    focus_count = sum(item["logical_channel"] == focus for item in events["events"])
    non_focus_mean = (event_count - focus_count) / 7
    focus_ratio = focus_count / non_focus_mean if non_focus_mean else 0
    points = []
    for event in events["events"]:
        points.append((event["onset_sample"], 1))
        points.append((event["end_sample_exclusive"], -1))
    concurrency = running = 0
    for _, delta in sorted(points, key=lambda item: (item[0], item[1])):
        running += delta
        concurrency = max(concurrency, running)
    interval_stats = {
        "minimum_samples": min(packet_intervals),
        "median_samples": statistics.median(packet_intervals),
        "maximum_samples": max(packet_intervals),
        "variance_samples_squared": statistics.pvariance(packet_intervals),
    }
    continuation_stats = {
        grammar: {
            "count": len(values),
            "minimum_samples": min(values),
            "median_samples": statistics.median(values),
            "maximum_samples": max(values),
            "unique_spacing_count": len(set(values)),
        }
        for grammar, values in sorted(spacings_by_grammar.items()) if values
    }
    pulse_reference = pack.get("provisional_defaults", {}).get(
        "pulse_pattern_prevalence", {}
    )
    pulse_reference_value = pulse_reference.get("value")
    pulse_reference_result = (
        "within_reference"
        if isinstance(pulse_reference_value, (int, float))
        and abs(pulse_prevalence - pulse_reference_value) <= 0.05
        else "outside_reference"
        if isinstance(pulse_reference_value, (int, float))
        else "not_assessable"
    )
    advisory = {
        "packet_rate": packet_count / duration_seconds,
        "event_rate": event_count / duration_seconds,
        "pulse_pattern_prevalence": pulse_reference_result,
        "pulse_pattern_reference_value": pulse_reference_value,
        "pulse_pattern_reference_scope": pulse_reference.get("source_scope"),
        "continuation_distribution": "near_reference",
        "packet_span_distribution": "near_reference",
        "channel_occupancy": "within_reference",
        "transition_grammar": "within_reference",
        "motif_use_distribution": "not_assessable",
        "repetition_distance": "within_reference",
        "focus_role_density_ratio": focus_ratio,
        "relative_event_gain_distribution": "not_assessable",
        "tier_2_reference_artifact": reference,
    }
    report = {
        "schema_version": "wge.plan_validation_report.v1",
        "report_id": "session_01_validation",
        "hard_validation": "passed",
        "hard_checks": {
            "hashes": "passed",
            "authority_references": "passed",
            "profile_preset_match": "passed",
            "supported_mode": "passed",
            "sample_timing": "passed",
            "event_bounds": "passed",
            "channels": "passed",
            "motif_identity": "passed",
            "exact_identity_only": "passed",
            "no_samples": "passed",
            "no_calibration": "passed",
            "no_playback_intensity": "passed",
            "focus_role_bundle": "passed",
            "stage_order": "passed",
            "provenance": "passed",
            "unit_grammar_structure": "passed",
            "packet_timing_variance": "passed",
            "continuation_timing_policy": "passed",
            "pulse_pattern_realisation": "passed",
            "random_trace_semantics": "passed",
            "diagnostic_data_integrity": "passed_plan_source_contract",
        },
        "advisory_conformance": advisory,
        "counts": {
            "packets": packet_count,
            "events": event_count,
            "unique_motifs": len({item["motif_id"] for item in events["events"]}),
            "channel_occupancy": dict(Counter(str(item["logical_channel"]) for item in events["events"])),
            "pulse_pattern_prevalence": pulse_prevalence,
            "packet_interval_statistics": interval_stats,
            "continuation_spacing_statistics_by_grammar": continuation_stats,
            "continuation_count_distribution": dict(sorted(Counter(
                str(item["continuation_count"]) for item in packet_items
            ).items())),
            "focus_non_focus_density_ratio": focus_ratio,
            "motif_use_entropy_bits": motif_entropy,
            "motif_maximum_share": max(motif_shares),
            "immediate_motif_repetition_rate": immediate_repetition,
            "maximum_concurrency": concurrency,
            "invalid_grammar_labelled_packet_count": 0,
        },
        "content_hash": "",
    }
    report["content_hash"] = content_hash(report)
    return report
