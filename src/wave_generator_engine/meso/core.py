import hashlib
import random
from dataclasses import asdict
from typing import Any

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.meso.metrics import schedule_metrics
from wave_generator_engine.meso.models import (
    MesoPhraseRecord,
    MesoPhraseState,
    MesoScheduleRequest,
    MesoScheduleResult,
)
from wave_generator_engine.meso.policy import MesoPolicy, load_meso_policy
from wave_generator_engine.profiles.hashing import content_hash


def _derive_seed(root_seed: int, *labels: str) -> int:
    payload = ":".join((str(root_seed), *labels)).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _piecewise_quantile(rng: random.Random, values: dict[str, float]) -> float:
    points = [
        (0.0, values["minimum"]),
        (0.1, values["p10"]),
        (0.5, values["median"]),
        (0.9, values["p90"]),
        (1.0, values["maximum"]),
    ]
    draw = rng.random()
    for (left_q, left), (right_q, right) in zip(points, points[1:]):
        if draw <= right_q:
            fraction = (draw - left_q) / (right_q - left_q)
            return left + fraction * (right - left)
    return values["maximum"]


def _bounded_sum(
    values: list[int],
    target: int,
    minimum: int,
    maximum: int,
    rng: random.Random,
) -> list[int]:
    result = [min(max(value, minimum), maximum) for value in values]
    delta = target - sum(result)
    while delta:
        eligible = [
            index for index, value in enumerate(result)
            if (delta > 0 and value < maximum) or (delta < 0 and value > minimum)
        ]
        if not eligible:
            raise ValidationFailure("Meso duration reconciliation is infeasible")
        rng.shuffle(eligible)
        for index in eligible:
            room = maximum - result[index] if delta > 0 else result[index] - minimum
            change = min(abs(delta), max(1, room))
            result[index] += change if delta > 0 else -change
            delta += -change if delta > 0 else change
            if not delta:
                break
    return result


def _partition(total: int, count: int, rng: random.Random) -> list[int]:
    if count == 1:
        return [total]
    weights = [rng.uniform(0.75, 1.25) for _ in range(count)]
    raw = [max(1, round(total * weight / sum(weights))) for weight in weights]
    return _bounded_sum(raw, total, 1, total, rng)


def _distribute(
    total: int,
    buckets: int,
    base: int,
    cap: int,
    persistence: float,
    rng: random.Random,
) -> list[int]:
    values = [base] * buckets
    for _ in range(total - base * buckets):
        eligible = [index for index, value in enumerate(values) if value < cap]
        if not eligible:
            raise ValidationFailure("Meso phrase-size reconciliation is infeasible")
        weights = [persistence ** max(0, values[index] - base) for index in eligible]
        selected = rng.choices(eligible, weights=weights, k=1)[0]
        values[selected] += 1
    return values


class MesoPhraseScheduler:
    rng_algorithm = "python_random_mt19937_local"
    seed_derivation = "sha256_first_64_bits"

    def schedule(
        self,
        request: MesoScheduleRequest,
        *,
        policy: MesoPolicy | None = None,
    ) -> MesoScheduleResult:
        packet_count = request.resolved_packet_count()
        policy = policy or load_meso_policy(request.source_scope)
        if request.policy_id != policy.policy_id:
            raise ValidationFailure("Meso request policy identity mismatch")
        seed = _derive_seed(
            request.root_seed,
            "meso_phrase_scheduler",
            policy.content_hash,
            request.source_scope,
        )
        rng = random.Random(seed)
        sample_rate = request.sample_rate_hz
        duration_seconds = request.duration_samples / sample_rate
        parameter = lambda name: policy.parameters[name]["value"]

        cluster_rate = float(parameter("session_1_clusters_per_observed_minute"))
        phrase_count = max(1, round(cluster_rate * duration_seconds / 60))
        phrase_count = min(phrase_count, packet_count // 4)
        active_share = float(parameter("session_1_phrase_active_share"))
        active_windows = round(active_share * max(1, packet_count - 3))
        phrase_packet_total = min(
            packet_count - max(0, phrase_count - 1),
            active_windows + 3 * phrase_count,
        )
        phrase_packet_total = max(4 * phrase_count, phrase_packet_total)
        size_reference = parameter("session_1_cluster_size")
        continuation = float(
            parameter("session_1_phrase_continuation_probability")
        )
        phrase_sizes = _distribute(
            phrase_packet_total,
            phrase_count,
            4,
            max(4, min(int(size_reference["maximum"]), round(size_reference["p90"]))),
            continuation,
            rng,
        )

        background_count = packet_count - sum(phrase_sizes)
        gap_count = max(0, phrase_count - 1)
        background_by_gap = [1] * gap_count
        if gap_count:
            initiation = float(
                parameter("session_1_phrase_initiation_probability")
            )
            for _ in range(background_count - gap_count):
                weights = [
                    (1 - initiation) ** count for count in background_by_gap
                ]
                index = rng.choices(range(gap_count), weights=weights, k=1)[0]
                background_by_gap[index] += 1
        elif background_count:
            raise ValidationFailure("Packet count cannot be reconciled into one phrase")

        within_reference = parameter("session_1_within_cluster_interval")
        duration_reference = parameter("session_1_cluster_duration")
        phrase_intervals: list[list[int]] = []
        for size in phrase_sizes:
            anchor = _piecewise_quantile(rng, within_reference)
            values = [
                round(
                    (
                        0.62 * anchor
                        + 0.38 * _piecewise_quantile(rng, within_reference)
                    ) * sample_rate
                )
                for _ in range(size - 1)
            ]
            minimum_duration = round(duration_reference["minimum"] * sample_rate)
            maximum_duration = round(duration_reference["maximum"] * sample_rate)
            target = min(max(sum(values), minimum_duration), maximum_duration)
            values = _bounded_sum(
                values,
                target,
                round(within_reference["minimum"] * sample_rate),
                round(within_reference["maximum"] * sample_rate),
                rng,
            )
            phrase_intervals.append(values)

        gap_reference = parameter("session_1_between_cluster_gap")
        raw_gap_totals = [
            round(_piecewise_quantile(rng, gap_reference) * sample_rate)
            for _ in range(gap_count)
        ]
        phrase_total = sum(sum(values) for values in phrase_intervals)
        average_packet_interval = request.duration_samples // packet_count
        desired_last_onset = request.duration_samples - average_packet_interval
        target_gap_total = desired_last_onset - phrase_total
        gap_minimum = round(gap_reference["minimum"] * sample_rate)
        gap_maximum = round(gap_reference["maximum"] * sample_rate)
        target_gap_total = min(
            max(target_gap_total, gap_count * gap_minimum),
            gap_count * gap_maximum,
        )
        gap_totals = (
            _bounded_sum(
                raw_gap_totals, target_gap_total, gap_minimum, gap_maximum, rng
            )
            if gap_count else []
        )

        onsets = [0]
        states: list[str] = []
        memberships: list[str | None] = []
        phrases: list[MesoPhraseRecord] = []
        all_intervals: list[int] = []
        within_intervals: list[int] = []
        packet_index = 0
        for phrase_index, (size, intervals) in enumerate(
            zip(phrase_sizes, phrase_intervals)
        ):
            phrase_id = f"phrase_{phrase_index:04d}"
            first_index = packet_index
            phrase_onset = onsets[-1]
            for local_index in range(size):
                states.append(MesoPhraseState.PHRASE_ACTIVE.value)
                memberships.append(phrase_id)
                if local_index < size - 1:
                    interval = intervals[local_index]
                    all_intervals.append(interval)
                    within_intervals.append(interval)
                    onsets.append(onsets[-1] + interval)
                packet_index += 1
            phrases.append(MesoPhraseRecord(
                phrase_id=phrase_id,
                first_packet_index=first_index,
                last_packet_index=packet_index - 1,
                packet_count=size,
                onset_sample=phrase_onset,
                end_onset_sample=onsets[-1],
                duration_samples=onsets[-1] - phrase_onset,
                state_entry=(
                    "session_boundary"
                    if phrase_index == 0 else MesoPhraseState.BACKGROUND.value
                ),
                state_exit=(
                    "session_boundary"
                    if phrase_index == phrase_count - 1
                    else MesoPhraseState.BACKGROUND.value
                ),
            ))
            if phrase_index < gap_count:
                parts = _partition(
                    gap_totals[phrase_index],
                    background_by_gap[phrase_index] + 1,
                    rng,
                )
                for interval in parts[:-1]:
                    all_intervals.append(interval)
                    onsets.append(onsets[-1] + interval)
                    states.append(MesoPhraseState.BACKGROUND.value)
                    memberships.append(None)
                    packet_index += 1
                all_intervals.append(parts[-1])
                onsets.append(onsets[-1] + parts[-1])

        if len(onsets) != packet_count or len(states) != packet_count:
            raise ValidationFailure("Meso packet-count reconciliation failed")
        metrics = schedule_metrics(
            onsets=onsets,
            phrase_sizes=phrase_sizes,
            phrase_durations=[item.duration_samples for item in phrases],
            within_intervals=within_intervals,
            between_gaps=gap_totals,
            sample_rate_hz=sample_rate,
            duration_samples=request.duration_samples,
        )
        document: dict[str, Any] = {
            "schema_version": "wge.meso_schedule_result.v1",
            "request": asdict(request),
            "onset_samples": onsets,
            "inter_packet_intervals": all_intervals,
            "phrase_states": states,
            "packet_phrase_ids": memberships,
            "phrases": [asdict(item) for item in phrases],
            "metrics": metrics,
            "provenance": {
                "policy_id": policy.policy_id,
                "policy_hash": policy.content_hash,
                "source_scope": request.source_scope,
                "rng_algorithm": self.rng_algorithm,
                "root_seed": request.root_seed,
                "scheduler_seed": seed,
                "seed_derivation": self.seed_derivation,
                "source_sequence_dependency": False,
                "exact_source_interval_tuples_embedded": False,
                "parameter_provenance": [
                    {
                        "parameter_id": item["parameter_id"],
                        "authority_tier": item["authority_tier"],
                        "binding_status": item["binding_status"],
                        "source_scope": item["source_scope"],
                        "source_artifact": item["source_artifact"],
                        "source_field": item["source_field"],
                        "provisional": item["provisional"],
                    }
                    for item in policy.document["source_supported_parameters"]
                    if item["parameter_id"] in {
                        "session_1_phrase_active_share",
                        "session_1_phrase_initiation_probability",
                        "session_1_phrase_continuation_probability",
                        "session_1_clusters_per_observed_minute",
                        "session_1_cluster_size",
                        "session_1_cluster_duration",
                        "session_1_within_cluster_interval",
                        "session_1_between_cluster_gap",
                        "session_1_validation_block_phrase_active_band",
                        "session_1_validation_block_cluster_rate_band",
                    }
                ],
                "rate_reconciliation": (
                    "exact packet count; bounded phrase intervals and gap-only "
                    "water-filling; no global interval stretch"
                ),
            },
            "content_hash": "",
        }
        document["content_hash"] = content_hash(document)
        return MesoScheduleResult(
            schema_version=document["schema_version"],
            request=document["request"],
            onset_samples=tuple(onsets),
            inter_packet_intervals=tuple(all_intervals),
            phrase_states=tuple(states),
            packet_phrase_ids=tuple(memberships),
            phrases=tuple(phrases),
            metrics=metrics,
            provenance=document["provenance"],
            content_hash=document["content_hash"],
        )
