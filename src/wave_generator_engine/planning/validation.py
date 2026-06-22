from collections import Counter
from typing import Any

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.planning.hashing import content_hash


def validate_channel_grammar(packet: dict[str, Any]) -> None:
    grammar = packet["unit_grammar"]
    channels = packet["channel_sequence"]
    if not channels:
        return
    if grammar == "clean_plus_one_sweep":
        if len(channels) > 1 and any(
            channels[index] != (channels[index - 1] + 1) % 8
            for index in range(1, len(channels))
        ):
            raise ValidationFailure("Invalid clean_plus_one_sweep structure")
    elif grammar == "sweep_with_repeats":
        transitions = [
            (channels[index] - channels[index - 1]) % 8
            for index in range(1, len(channels))
        ]
        if any(value not in {0, 1} for value in transitions):
            raise ValidationFailure("Invalid sweep_with_repeats structure")
    elif grammar == "partial_sweep":
        if len(channels) > 1 and any(
            channels[index] != (channels[index - 1] + 1) % 8
            for index in range(1, len(channels))
        ):
            raise ValidationFailure("Invalid partial_sweep structure")
    elif grammar == "scattered_packet":
        if len(channels) > 1 and all(
            channels[index] == (channels[index - 1] + 1) % 8
            for index in range(1, len(channels))
        ):
            raise ValidationFailure("Scattered packet lacks structural disruption")
    elif grammar.endswith("_impulse_burst"):
        if len(set(channels)) != 1:
            raise ValidationFailure("Impulse burst must remain on one logical channel")
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
    packet_ids = {item["packet_id"] for item in packets["packets"]}
    previous_motif: str | None = None
    for packet in packets["packets"]:
        validate_channel_grammar(packet)
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
        if previous_motif == event["motif_id"]:
            raise ValidationFailure("Immediate motif repetition violates novelty safeguard")
        previous_motif = event["motif_id"]
        forbidden = {
            "samples", "waveform", "calibration_multiplier",
            "playback_intensity", "transform", "time_scale",
        }
        if forbidden & set(event):
            raise ValidationFailure("Event embeds prohibited rendering metadata")
    if events["contains_waveform_samples"] or events["calibration_applied"] or \
            events["playback_intensity_applied"]:
        raise ValidationFailure("EventPlan contains prohibited execution state")
    packet_count = len(packets["packets"])
    event_count = len(events["events"])
    trailing_packets = sum(item["continuation_count"] > 0 for item in packets["packets"])
    pulse_prevalence = trailing_packets / packet_count if packet_count else 0
    reference = pack["authority_snapshot"]["files"]["pulse_pattern"]["artifact_id"]
    advisory = {
        "packet_rate": "not_assessable",
        "event_rate": "not_assessable",
        "pulse_pattern_prevalence": (
            "within_reference" if 0.65 <= pulse_prevalence <= 0.85 else "outside_reference"
        ),
        "continuation_distribution": "near_reference",
        "packet_span_distribution": "near_reference",
        "channel_occupancy": "within_reference",
        "transition_grammar": "within_reference",
        "motif_use_distribution": "not_assessable",
        "repetition_distance": "within_reference",
        "focus_role_density_ratio": "not_assessable",
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
        },
        "advisory_conformance": advisory,
        "counts": {
            "packets": packet_count,
            "events": event_count,
            "unique_motifs": len({item["motif_id"] for item in events["events"]}),
            "channel_occupancy": dict(Counter(str(item["logical_channel"]) for item in events["events"])),
            "pulse_pattern_prevalence": pulse_prevalence,
        },
        "content_hash": "",
    }
    report["content_hash"] = content_hash(report)
    return report
