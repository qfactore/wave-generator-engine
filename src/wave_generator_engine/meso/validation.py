from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.meso.models import MesoScheduleRequest, MesoScheduleResult
from wave_generator_engine.meso.policy import MesoPolicy
from wave_generator_engine.profiles.hashing import validate_content_hash


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationFailure(message)


def validate_meso_schedule(
    request: MesoScheduleRequest,
    result: MesoScheduleResult,
    policy: MesoPolicy,
) -> dict:
    document = result.to_dict()
    _require(validate_content_hash(document), "Meso result content hash mismatch")
    _require(result.provenance["policy_id"] == policy.policy_id,
             "Meso result policy identity mismatch")
    _require(result.provenance["policy_hash"] == policy.content_hash,
             "Meso result policy hash mismatch")
    _require(result.provenance["source_scope"] == request.source_scope,
             "Meso source scope mismatch")
    _require(not result.provenance["source_sequence_dependency"],
             "Meso schedule depends on a protected source sequence")
    _require(not result.provenance["exact_source_interval_tuples_embedded"],
             "Meso schedule embeds protected source interval tuples")

    onsets = result.onset_samples
    expected_count = request.resolved_packet_count()
    _require(len(onsets) == expected_count, "Meso packet count was not preserved")
    _require(len(result.inter_packet_intervals) == expected_count - 1,
             "Meso interval count is invalid")
    _require(all(isinstance(value, int) for value in onsets),
             "Meso onsets must be integer samples")
    _require(all(left < right for left, right in zip(onsets, onsets[1:])),
             "Meso onsets must be strictly increasing")
    _require(onsets[0] >= 0 and onsets[-1] < request.duration_samples,
             "Meso onsets are outside the requested duration")
    _require(
        tuple(right - left for left, right in zip(onsets, onsets[1:]))
        == result.inter_packet_intervals,
        "Meso interval record does not match onsets",
    )
    _require(
        len(result.phrase_states) == len(result.packet_phrase_ids) == expected_count,
        "Meso phrase membership length mismatch",
    )

    phrase_ids = {item.phrase_id for item in result.phrases}
    _require(None in result.packet_phrase_ids, "Background state is absent")
    _require(set(item for item in result.packet_phrase_ids if item) == phrase_ids,
             "Meso phrase membership is incomplete")
    size_maximum = policy.parameters["session_1_cluster_size"]["value"]["maximum"]
    duration_maximum = round(
        policy.parameters["session_1_cluster_duration"]["value"]["maximum"]
        * request.sample_rate_hz
    )
    duration_minimum = round(
        policy.parameters["session_1_cluster_duration"]["value"]["minimum"]
        * request.sample_rate_hz
    )
    for phrase in result.phrases:
        _require(phrase.packet_count >= 4, "Meso phrase is shorter than four packets")
        _require(phrase.packet_count <= size_maximum, "Meso phrase exceeds size bound")
        _require(phrase.duration_samples >= duration_minimum,
                 "Meso phrase is below the duration bound")
        _require(phrase.duration_samples <= duration_maximum,
                 "Meso phrase exceeds duration bound")
        indices = [
            index for index, phrase_id in enumerate(result.packet_phrase_ids)
            if phrase_id == phrase.phrase_id
        ]
        _require(indices == list(range(phrase.first_packet_index,
                                      phrase.last_packet_index + 1)),
                 "Meso phrase membership is not contiguous")
        _require(
            all(result.phrase_states[index] == "phrase_active" for index in indices),
            "Meso active state and phrase membership disagree",
        )
    for index, phrase_id in enumerate(result.packet_phrase_ids):
        if phrase_id is None:
            _require(result.phrase_states[index] == "background",
                     "Meso background state and membership disagree")
    for left, right in zip(result.phrases, result.phrases[1:]):
        _require(right.first_packet_index > left.last_packet_index + 1,
                 "Meso phrases must be separated by background state")
        _require(left.state_exit == right.state_entry == "background",
                 "Meso phrase transition metadata is invalid")

    metrics = result.metrics
    active_band = policy.parameters[
        "session_1_validation_block_phrase_active_band"
    ]["value"]
    rate_band = policy.parameters[
        "session_1_validation_block_cluster_rate_band"
    ]["value"]
    _require(
        active_band["minimum"] <= metrics["phrase_active_window_share"]
        <= active_band["maximum"],
        "Meso phrase-active share is outside the empirical band",
    )
    _require(
        rate_band["minimum"] <= metrics["phrases_per_minute"]
        <= rate_band["maximum"],
        "Meso phrase rate is outside the empirical band",
    )
    for metric_id, parameter_id in (
        ("phrase_size_packets", "session_1_cluster_size"),
        ("phrase_duration_seconds", "session_1_cluster_duration"),
        ("within_phrase_interval_seconds", "session_1_within_cluster_interval"),
        ("between_phrase_gap_seconds", "session_1_between_cluster_gap"),
    ):
        reference = policy.parameters[parameter_id]["value"]
        _require(
            reference["minimum"] <= metrics[metric_id]["median"]
            <= reference["maximum"],
            f"{metric_id} median is outside the policy envelope",
        )
    _require(metrics["unique_interval_count"] >= max(8, expected_count // 10),
             "Meso interval diversity is inadequate")
    _require(metrics["interval_coefficient_of_variation"] > 0.05,
             "Meso schedule collapsed into a fixed lattice")
    _require(metrics["maximum_identical_interval_run"] <= 2,
             "Meso schedule contains a repeating fixed interval run")
    _require(metrics["schedule_spectrum"]["peak_power_fraction"] < 0.2,
             "Meso schedule contains a narrow global cadence")
    _require(metrics["local_phrase_recurrence_present"],
             "Meso schedule lacks local recurrent interval relationships")
    _require(
        metrics["final_boundary_margin_samples"]
        >= request.duration_samples // expected_count // 2,
        "Meso schedule is unnaturally compressed against the end boundary",
    )
    return {
        "valid": True,
        "checks": [
            "policy_identity",
            "strict_onset_ordering",
            "duration_bounds",
            "exact_packet_count",
            "phrase_membership",
            "state_transitions",
            "source_empirical_bands",
            "anti_replay",
            "anti_lattice",
        ],
        "content_hash": result.content_hash,
    }
