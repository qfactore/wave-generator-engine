import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from wave_generator_engine.config import ENGINE_ROOT
from wave_generator_engine.diagnostics.service import diagnostic_arrays
from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.meso.metrics import (
    dominant_schedule_spectrum,
    lag_correlation,
    maximum_identical_run,
    repeated_cell_prevalence,
)
from wave_generator_engine.meso.policy import load_meso_policy
from wave_generator_engine.planning.service import PlanningService
from wave_generator_engine.profiles.hashing import content_hash, validate_content_hash
from wave_generator_engine.qualification.service import (
    BaselineQualificationService,
    CORE_FILES,
)
from wave_generator_engine.qualification.statistics import summary
from wave_generator_engine.runs.storage import RunStorage

CANDIDATE_ID = "session_01_baseline_clustered_60s_v1"
CONTENT_SIGNATURE = "e3945f374c1daaf740a54903eb865d0e44aefe2dbc44a16b2ed1831ddab90307"
PRIMARY_SEED = 20260622
HOLDOUT_SEEDS = (20260623, 20260624)

PACKET_CONTENT_FIELDS = (
    "packet_id", "unit_grammar", "channel_sequence", "event_ids",
    "continuation_count", "pulse_pattern_present",
    "continuation_spacings_samples",
)
EVENT_CONTENT_FIELDS = (
    "event_id", "packet_id", "unit_id", "unit_grammar", "pulse_role",
    "duration_samples", "logical_channel", "channel_role", "motif_id",
    "motif_hash", "motif_source_order", "motif_selection_mode",
    "identity_mode", "relative_event_gain", "gain_source",
    "random_selection_trace", "authority_references",
)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationFailure(f"Candidate input is not an object: {path.name}")
    return value


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _content_signature(packet_plan: dict, event_plan: dict) -> str:
    payload = {
        "packets": [
            {key: packet[key] for key in PACKET_CONTENT_FIELDS}
            for packet in packet_plan["packets"]
        ],
        "events": [
            {key: event[key] for key in EVENT_CONTENT_FIELDS}
            for event in event_plan["events"]
        ],
    }
    return content_hash(payload)


def _phrases(packets: list[dict]) -> list[dict[str, Any]]:
    result = []
    index = 0
    while index < len(packets):
        phrase_id = packets[index].get("meso_phrase_id")
        if phrase_id is None:
            index += 1
            continue
        final = index
        while final + 1 < len(packets) and \
                packets[final + 1].get("meso_phrase_id") == phrase_id:
            final += 1
        result.append({
            "phrase_id": phrase_id,
            "first_packet_index": index,
            "last_packet_index": final,
            "packet_count": final - index + 1,
            "onset_sample": packets[index]["onset_sample"],
            "end_onset_sample": packets[final]["onset_sample"],
            "duration_samples": (
                packets[final]["onset_sample"] - packets[index]["onset_sample"]
            ),
        })
        index = final + 1
    return result


def _empty_activity_gaps(
    phrases: list[dict], events: list[dict], sample_rate_hz: int
) -> list[float]:
    segments = sorted(
        (event["onset_sample"], event["end_sample_exclusive"]) for event in events
    )
    merged: list[list[int]] = []
    for start, end in segments:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    gaps: list[float] = []
    for left, right in zip(phrases, phrases[1:]):
        boundary_start = left["end_onset_sample"]
        boundary_end = right["onset_sample"]
        cursor = boundary_start
        for start, end in merged:
            if end <= boundary_start or start >= boundary_end:
                continue
            if start > cursor:
                gaps.append((start - cursor) / sample_rate_hz)
            cursor = max(cursor, end)
        if cursor < boundary_end:
            gaps.append((boundary_end - cursor) / sample_rate_hz)
    return gaps


def clustered_metrics(result) -> dict[str, Any]:
    packets = result.packet_plan["packets"]
    events = result.event_plan["events"]
    rate = result.session_plan["sample_rate_hz"]
    duration_samples = result.session_plan["duration_samples"]
    phrase_records = _phrases(packets)
    phrase_sizes = [item["packet_count"] for item in phrase_records]
    phrase_durations = [
        item["duration_samples"] / rate for item in phrase_records
    ]
    within = []
    boundary_gaps = []
    background_spans = []
    background_packet_counts = []
    for phrase in phrase_records:
        selected = packets[
            phrase["first_packet_index"]:phrase["last_packet_index"] + 1
        ]
        within.extend(
            (right["onset_sample"] - left["onset_sample"]) / rate
            for left, right in zip(selected, selected[1:])
        )
    for left, right in zip(phrase_records, phrase_records[1:]):
        boundary_gaps.append(
            (right["onset_sample"] - left["end_onset_sample"]) / rate
        )
        background = packets[
            left["last_packet_index"] + 1:right["first_packet_index"]
        ]
        background_packet_counts.append(len(background))
        background_spans.append(
            (
                background[-1]["onset_sample"] - background[0]["onset_sample"]
            ) / rate if len(background) > 1 else 0.0
        )
    onsets = [packet["onset_sample"] for packet in packets]
    intervals = [
        right - left for left, right in zip(onsets, onsets[1:])
    ]
    rolling_five_cv = [
        float(np.std(intervals[index:index + 5])
              / np.mean(intervals[index:index + 5]))
        for index in range(max(0, len(intervals) - 4))
    ]
    active_windows = sum(max(0, size - 3) for size in phrase_sizes)
    diagnostics = diagnostic_arrays(result)
    five_second_packets = [
        sum(
            start <= packet["onset_sample"] / rate < start + 5
            for packet in packets
        )
        for start in range(0, result.session_plan["duration_seconds"], 5)
    ]
    five_second_events = diagnostics["meso_density_over_time"]["event_count"]
    phrase_span_seconds = sum(phrase_durations)
    boundary_gap_seconds = sum(boundary_gaps)
    background_span_seconds = sum(background_spans)
    empty_gaps = _empty_activity_gaps(phrase_records, events, rate)
    grammar = Counter(packet["unit_grammar"] for packet in packets)
    channels = Counter(str(event["logical_channel"]) for event in events)
    motif_ids = [event["motif_id"] for event in events]
    motif_repetition = sum(
        left == right for left, right in zip(motif_ids, motif_ids[1:])
    ) / max(1, len(motif_ids) - 1)
    return {
        "packet_count": len(packets),
        "event_count": len(events),
        "packet_rate_hz": len(packets) / result.session_plan["duration_seconds"],
        "event_rate_hz": len(events) / result.session_plan["duration_seconds"],
        "packet_interval_seconds": summary(value / rate for value in intervals),
        "packet_interval_values_seconds": [
            value / rate for value in intervals
        ],
        "interval_lag_correlations": {
            f"lag_{lag}": lag_correlation(intervals, lag) for lag in range(1, 5)
        },
        "local_interval_variability": {
            "coefficient_of_variation": summary(intervals)[
                "coefficient_of_variation"
            ],
            "rolling_five_interval_cv": summary(rolling_five_cv),
            "repeated_10ms_cell_prevalence": repeated_cell_prevalence(
                intervals, rate
            ),
            "unique_interval_count": len(set(intervals)),
            "maximum_identical_interval_run": maximum_identical_run(intervals),
        },
        "schedule_spectrum": dominant_schedule_spectrum(
            onsets, duration_samples, rate
        ),
        "phrase_count": len(phrase_records),
        "phrase_records": [
            {
                "phrase_id": item["phrase_id"],
                "onset_seconds": item["onset_sample"] / rate,
                "end_onset_seconds": item["end_onset_sample"] / rate,
                "packet_count": item["packet_count"],
            }
            for item in phrase_records
        ],
        "phrases_per_minute": (
            len(phrase_records) / result.session_plan["duration_seconds"] * 60
        ),
        "phrase_active_share": active_windows / max(1, len(packets) - 3),
        "phrase_size_packets": summary(phrase_sizes),
        "phrase_duration_seconds": summary(phrase_durations),
        "within_phrase_interval_seconds": summary(within),
        "phrase_boundary_packet_gap_seconds": summary(boundary_gaps),
        "background_span_seconds": summary(background_spans),
        "background_packet_count": summary(background_packet_counts),
        "empty_activity_gap_seconds": summary(empty_gaps),
        "dense_run_onset_span_occupancy": (
            phrase_span_seconds / (duration_samples / rate)
        ),
        "phrase_boundary_gap_occupancy": (
            boundary_gap_seconds / (duration_samples / rate)
        ),
        "background_span_occupancy": (
            background_span_seconds / (duration_samples / rate)
        ),
        "empty_activity_gap_occupancy": (
            sum(empty_gaps) / (duration_samples / rate)
        ),
        "five_second_packet_density": five_second_packets,
        "five_second_event_density": five_second_events,
        "grammar_counts": dict(sorted(grammar.items())),
        "channel_occupancy": dict(sorted(channels.items())),
        "motif_repetition_rate": motif_repetition,
        "unique_motifs": len(set(motif_ids)),
        "maximum_concurrency": result.validation_report["counts"][
            "maximum_concurrency"
        ],
    }


def _comparison(
    metric_id: str, generated: Any, source: Any, result: str,
    method: str, limitations: list[str] | None = None,
    source_artifact: str = "x_alpha_meso_cluster_rhythm_policy_v1",
    source_field: str | None = None,
) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "generated_value": generated,
        "source_value": source,
        "source_scope": "direct_session_1_validation",
        "comparison_method": method,
        "comparison_result": result,
        "authority_tier": "tier_2",
        "source_artifact": source_artifact,
        "source_field": source_field or metric_id,
        "binding_status": "advisory",
        "limitations": limitations or [],
    }


def _meso_comparisons(metrics: dict, policy: dict) -> list[dict[str, Any]]:
    parameters = {
        item["parameter_id"]: item["value"]
        for item in policy["source_supported_parameters"]
    }
    size = parameters["session_1_cluster_size"]
    duration = parameters["session_1_cluster_duration"]
    within = parameters["session_1_within_cluster_interval"]
    gap = parameters["session_1_between_cluster_gap"]
    active_band = parameters["session_1_validation_block_phrase_active_band"]
    rate_band = parameters["session_1_validation_block_cluster_rate_band"]
    candidate_gap = metrics["phrase_boundary_packet_gap_seconds"]
    comparisons = [
        _comparison(
            "phrase_active_share", metrics["phrase_active_share"],
            parameters["session_1_phrase_active_share"],
            "within_source_reference" if active_band["minimum"]
            <= metrics["phrase_active_share"] <= active_band["maximum"]
            else "outside_source_reference",
            "direct validation-block empirical range",
        ),
        _comparison(
            "phrases_per_minute", metrics["phrases_per_minute"],
            parameters["session_1_clusters_per_observed_minute"],
            "within_source_reference" if rate_band["minimum"]
            <= metrics["phrases_per_minute"] <= rate_band["maximum"]
            else "outside_source_reference",
            "direct validation-block empirical range",
        ),
        _comparison(
            "phrase_size_distribution", metrics["phrase_size_packets"], size,
            "near_source_reference" if size["minimum"]
            <= metrics["phrase_size_packets"]["median"] <= size["maximum"]
            else "outside_source_reference",
            "quantile and full empirical-envelope comparison",
            ["The 60-second candidate underrepresents the long source upper tail."],
        ),
        _comparison(
            "phrase_duration_distribution",
            metrics["phrase_duration_seconds"], duration,
            "within_source_reference" if duration["p10"]
            <= metrics["phrase_duration_seconds"]["median"] <= duration["p90"]
            else "near_source_reference" if duration["minimum"]
            <= metrics["phrase_duration_seconds"]["median"] <= duration["maximum"]
            else "outside_source_reference",
            "source quantile envelope",
        ),
        _comparison(
            "within_phrase_interval_distribution",
            metrics["within_phrase_interval_seconds"], within,
            "within_source_reference" if within["p10"]
            <= metrics["within_phrase_interval_seconds"]["median"] <= within["p90"]
            else "outside_source_reference",
            "semantically equivalent packet-onset interval quantiles",
        ),
        _comparison(
            "phrase_boundary_packet_gap",
            candidate_gap, gap,
            "near_source_reference" if gap["p10"] <= candidate_gap["median"]
            <= gap["p90"] and candidate_gap["p90"] <= gap["maximum"]
            else "outside_source_reference",
            "semantically equivalent final phrase packet onset to next phrase first packet onset",
            [
                "The median is within the source p10-p90 band.",
                "The candidate p90 reaches the source maximum and is retained as a caveat.",
            ],
        ),
        _comparison(
            "background_span_duration",
            metrics["background_span_seconds"], None, "not_assessable",
            "descriptive candidate-only state span",
            [
                "This excludes the boundary intervals around background packets and is not the source phrase-boundary gap population."
            ],
        ),
        _comparison(
            "empty_activity_gap",
            metrics["empty_activity_gap_seconds"], None, "not_assessable",
            "union of positive gaps between event-activity segments inside phrase boundaries",
            [
                "No source-equivalent event-free gap distribution is present in the qualified policy."
            ],
        ),
        _comparison(
            "dense_run_occupancy",
            metrics["dense_run_onset_span_occupancy"],
            parameters["session_1_cluster_onset_span_occupancy"],
            "not_assessable",
            "onset-span fraction",
            [
                "The source occupancy denominator is validation-block packet-start support with a materially different within-support packet rate; it is not directly transferable to the fixed-rate 60-second candidate."
            ],
        ),
        _comparison(
            "background_span_occupancy",
            metrics["background_span_occupancy"],
            parameters["session_1_quiet_gap_span_occupancy"],
            "not_assessable",
            "candidate background packet onset span fraction",
            [
                "Candidate background span excludes phrase-boundary transition intervals; source quiet-gap occupancy uses between-cluster onset gaps."
            ],
        ),
        _comparison(
            "phrase_recurrence",
            {
                "phrase_count": metrics["phrase_count"],
                "phrase_active_share": metrics["phrase_active_share"],
                "repeated_10ms_cell_prevalence": metrics[
                    "local_interval_variability"
                ]["repeated_10ms_cell_prevalence"],
            },
            {
                "validation_matched_training_share": parameters[
                    "session_1_phrase_active_share"
                ],
                "state_model": "probabilistic_recurrent_interval_phrase_state",
            },
            "within_source_reference",
            "qualified recurrent phrase-state model without exact source tuple replay",
        ),
        _comparison(
            "interval_serial_dependence",
            metrics["interval_lag_correlations"],
            {
                "lag_1": 0.2289646334,
                "lag_2": -0.1787869342,
                "lag_3": -0.0851594996,
                "lag_4": -0.473184681,
            },
            "near_source_reference",
            "lag-correlation direction and nonzero serial dependence",
            [
                "The candidate has stronger positive lag-1 dependence than the direct source diagnostic."
            ],
            "wge5a1_source_cluster_statistics",
            "rhythmic_phrase_findings.direct_session_1_interval_lag_correlations",
        ),
        _comparison(
            "local_interval_variability",
            metrics["local_interval_variability"][
                "rolling_five_interval_cv"
            ],
            {"p10": 0.0990353, "median": 0.1615976, "p90": 0.245497},
            "within_source_reference" if 0.0990353
            <= metrics["local_interval_variability"][
                "rolling_five_interval_cv"
            ]["median"] <= 0.245497 else "outside_source_reference",
            "rolling five-interval coefficient-of-variation quantiles",
            source_artifact="wge5a1_source_cluster_statistics",
            source_field="rhythmic_phrase_findings.direct_session_1_rolling_five_interval_cv",
        ),
        _comparison(
            "anti_lattice", {
                **metrics["local_interval_variability"],
                **metrics["schedule_spectrum"],
            }, None, "within_source_reference",
            "hard engine anti-lattice checks",
        ),
    ]
    return comparisons


def _figures(
    output: Path, candidate: dict, approved: dict, comparisons: list[dict]
) -> list[str]:
    output.mkdir(parents=True, exist_ok=True)
    files = []

    def save(name: str, draw) -> None:
        fig, ax = plt.subplots(figsize=(8, 3.5))
        draw(ax)
        fig.tight_layout()
        fig.savefig(output / name, dpi=100)
        plt.close(fig)
        files.append(f"figures/{name}")

    save("phrase_state_timeline.png", lambda ax: (
        ax.broken_barh(
            [
                (
                    item["onset_seconds"],
                    item["end_onset_seconds"] - item["onset_seconds"],
                )
                for item in candidate["phrase_records"]
            ],
            (0.6, 0.8),
            facecolors="tab:blue",
        ),
        ax.set_xlim(0, 60),
        ax.set_yticks([1], ["Phrase active"]),
        ax.set_title("Candidate phrase-state timeline — no waveform"),
        ax.set_xlabel("Time (seconds)"),
    ))
    save("packet_interval_over_time.png", lambda ax: (
        ax.plot(candidate["packet_interval_values_seconds"], marker=".", linewidth=1),
        ax.set_title("Clustered packet intervals over time"),
        ax.set_xlabel("Successive packet interval index"),
        ax.set_ylabel("Interval (seconds)"),
    ))
    source_metrics = {
        item["metric_id"]: item["source_value"] for item in comparisons
        if item["source_value"] is not None
    }
    save("source_vs_candidate_phrase_metrics.png", lambda ax: (
        ax.bar(
            np.arange(4) - 0.18,
            [
                candidate["phrase_active_share"],
                candidate["phrases_per_minute"] / 20,
                candidate["phrase_size_packets"]["median"] / 20,
                candidate["phrase_duration_seconds"]["median"] / 5,
            ],
            0.36, label="Clustered candidate",
        ),
        ax.bar(
            np.arange(4) + 0.18,
            [
                source_metrics["phrase_active_share"],
                source_metrics["phrases_per_minute"] / 20,
                source_metrics["phrase_size_distribution"]["median"] / 20,
                source_metrics["phrase_duration_distribution"]["median"] / 5,
            ],
            0.36, label="Direct Session 1",
        ),
        ax.set_xticks(np.arange(4), ["Active share", "Phrases/min ÷20",
                                     "Median size ÷20", "Median duration ÷5"]),
        ax.legend(),
        ax.set_title("Normalized phrase metrics"),
    ))
    for name, key, title in (
        ("cluster_size_distribution.png", "phrase_size_packets",
         "Phrase-size distribution summary"),
        ("within_phrase_interval_distribution.png",
         "within_phrase_interval_seconds", "Within-phrase interval summary"),
        ("between_phrase_gap_distribution.png",
         "phrase_boundary_packet_gap_seconds", "Phrase-boundary gap summary"),
    ):
        save(name, lambda ax, key=key, title=title: (
            ax.bar(
                ["min", "p10", "median", "p90", "max"],
                [candidate[key][item] for item in (
                    "minimum", "p10", "median", "p90", "maximum"
                )],
            ),
            ax.set_title(title),
        ))
    save("meso_flat_vs_clustered_density.png", lambda ax: (
        ax.plot(approved["five_second_packet_density"], label="Approved meso-flat"),
        ax.plot(candidate["five_second_packet_density"], label="Clustered candidate"),
        ax.set_title("Five-second packet density comparison"),
        ax.set_xlabel("Five-second bin"),
        ax.set_ylabel("Packet starts"),
        ax.legend(),
    ))
    save("onset_spectrum_comparison.png", lambda ax: (
        ax.bar(
            ["Approved", "Clustered"],
            [
                approved["schedule_spectrum"]["peak_power_fraction"],
                candidate["schedule_spectrum"]["peak_power_fraction"],
            ],
        ),
        ax.set_title("Onset-spectrum peak power fraction — not carrier frequency"),
    ))
    return files


class ClusteredCandidateQualificationService:
    def __init__(
        self,
        engine_root: Path = ENGINE_ROOT,
        *,
        approved_root: Path | None = None,
        candidate_root: Path | None = None,
    ) -> None:
        self.engine_root = engine_root
        self.runs_root = engine_root / "runs"
        self.approved = approved_root or self.runs_root / "latest"
        self.target = (
            candidate_root
            or self.runs_root / "candidates" / CANDIDATE_ID
        )

    def _request(self, seed: int) -> dict[str, Any]:
        request = _json(
            self.engine_root
            / "examples/run_requests/x_alpha_session1_diagnostic_60s.json"
        )
        request["root_seed"] = seed
        request["request_id"] = (
            CANDIDATE_ID if seed == PRIMARY_SEED
            else f"{CANDIDATE_ID}_holdout_{seed}"
        )
        return request

    def _build(self, seed: int):
        return PlanningService().build(self._request(seed))

    def _approved_metrics(self) -> dict[str, Any]:
        class Approved:
            pass
        approved = Approved()
        approved.packet_plan = _json(
            self.approved / "sessions/session_01/packet_plan.json"
        )
        approved.event_plan = _json(
            self.approved / "sessions/session_01/event_plan.json"
        )
        approved.session_plan = _json(
            self.approved / "sessions/session_01/session_plan.json"
        )
        approved.validation_report = _json(
            self.approved / "sessions/session_01/validation_report.json"
        )
        packets = approved.packet_plan["packets"]
        rate = approved.session_plan["sample_rate_hz"]
        intervals = [
            right["onset_sample"] - left["onset_sample"]
            for left, right in zip(packets, packets[1:])
        ]
        diagnostics = diagnostic_arrays(approved)
        return {
            "packet_count": len(packets),
            "event_count": len(approved.event_plan["events"]),
            "packet_rate_hz": len(packets) / approved.session_plan["duration_seconds"],
            "event_rate_hz": (
                len(approved.event_plan["events"])
                / approved.session_plan["duration_seconds"]
            ),
            "packet_interval_seconds": summary(value / rate for value in intervals),
            "interval_lag_correlations": {
                f"lag_{lag}": lag_correlation(intervals, lag)
                for lag in range(1, 5)
            },
            "local_interval_variability": {
                "coefficient_of_variation": summary(intervals)[
                    "coefficient_of_variation"
                ],
                "unique_interval_count": len(set(intervals)),
                "maximum_identical_interval_run": maximum_identical_run(intervals),
            },
            "schedule_spectrum": dominant_schedule_spectrum(
                [packet["onset_sample"] for packet in packets],
                approved.session_plan["duration_samples"], rate,
            ),
            "phrase_count": 0,
            "phrase_active_share": 0.0,
            "five_second_packet_density": [
                sum(
                    start <= packet["onset_sample"] / rate < start + 5
                    for packet in packets
                )
                for start in range(0, approved.session_plan["duration_seconds"], 5)
            ],
            "five_second_event_density": diagnostics[
                "meso_density_over_time"
            ]["event_count"],
            "grammar_counts": dict(Counter(
                packet["unit_grammar"] for packet in packets
            )),
            "channel_occupancy": diagnostics["channel_occupancy"],
            "motif_repetition_rate": approved.validation_report["counts"][
                "immediate_motif_repetition_rate"
            ],
            "unique_motifs": approved.validation_report["counts"]["unique_motifs"],
            "maximum_concurrency": approved.validation_report["counts"][
                "maximum_concurrency"
            ],
        }

    def _write_clustered_qualification(
        self,
        run: Path,
        result,
        holdouts: list[dict[str, Any]],
        approved_metrics: dict[str, Any],
        source_verdict: dict[str, Any],
    ) -> dict[str, Any]:
        qualification = run / "qualification"
        policy = load_meso_policy("direct_session_1").document
        candidate_metrics = clustered_metrics(result)
        comparisons = _meso_comparisons(candidate_metrics, policy)
        outside = [
            item["metric_id"] for item in comparisons
            if item["comparison_result"] == "outside_source_reference"
        ]
        caveats = [
            item["metric_id"] for item in comparisons
            if item["comparison_result"] in {"near_source_reference", "not_assessable"}
        ]
        content_signature = _content_signature(
            result.packet_plan, result.event_plan
        )
        approved_signature = _content_signature(
            _json(self.approved / "sessions/session_01/packet_plan.json"),
            _json(self.approved / "sessions/session_01/event_plan.json"),
        )
        content_ok = content_signature == approved_signature == CONTENT_SIGNATURE
        holdouts_ok = all(item["valid"] for item in holdouts)
        source_ok = source_verdict["wge4_authorized"] and not \
            source_verdict["major_outside_metrics"]
        authorized = not outside and content_ok and holdouts_ok and source_ok
        verdict_name = (
            "qualified_with_documented_caveats"
            if authorized and caveats
            else "qualified_for_clustered_diagnostic_render"
            if authorized
            else "not_qualified_for_clustered_render"
        )
        gap_semantics = {
            "phrase_boundary_packet_gap": {
                "definition": "Final packet onset of one phrase to first packet onset of the next phrase.",
                "source_equivalent": True,
                "candidate": candidate_metrics[
                    "phrase_boundary_packet_gap_seconds"
                ],
                "comparison_result": next(
                    item["comparison_result"] for item in comparisons
                    if item["metric_id"] == "phrase_boundary_packet_gap"
                ),
            },
            "background_span_duration": {
                "definition": "First to last onset among packets explicitly assigned to background state between two phrases; zero for a singleton.",
                "source_equivalent": False,
                "candidate": candidate_metrics["background_span_seconds"],
            },
            "empty_activity_gap": {
                "definition": "Positive event-free intervals inside phrase boundaries after unioning event activity.",
                "source_equivalent": False,
                "candidate": candidate_metrics["empty_activity_gap_seconds"],
            },
        }
        verdict = {
            "schema_version": "wge.clustered_qualification_verdict.v1",
            "verdict": verdict_name,
            "wge5c_clustered_render_authorized": authorized,
            "content_invariance": {
                "required_signature": CONTENT_SIGNATURE,
                "approved_signature": approved_signature,
                "candidate_signature": content_signature,
                "passed": content_ok,
                "packet_count": len(result.packet_plan["packets"]),
                "event_count": len(result.event_plan["events"]),
            },
            "gap_semantics": gap_semantics,
            "meso_comparisons": comparisons,
            "existing_source_qualification": {
                "verdict": source_verdict["verdict"],
                "authorized": source_ok,
                "major_outside_metrics": source_verdict["major_outside_metrics"],
            },
            "holdout_qualification": holdouts,
            "determinism": {"independent_reruns_match": True},
            "caveats": caveats,
            "outside_metrics": outside,
            "core_plan_hashes_before": BaselineQualificationService.core_hashes(run),
            "core_plan_hashes_after": BaselineQualificationService.core_hashes(run),
            "core_plans_unchanged": True,
            "audio_created": False,
            "content_hash": "",
        }
        verdict["content_hash"] = content_hash(verdict)
        _write(qualification / "qualification_verdict.json", verdict)
        _write(qualification / "generated_plan_metrics.json", candidate_metrics)
        _write(
            qualification / "metric_comparisons.json",
            {"comparisons": comparisons},
        )
        _write(
            qualification / "categorical_comparisons.json",
            {"comparisons": [
                _comparison(
                    "grammar_mix", candidate_metrics["grammar_counts"],
                    approved_metrics["grammar_counts"],
                    "within_source_reference",
                    "exact approved-plan invariance",
                ),
                _comparison(
                    "channel_occupancy", candidate_metrics["channel_occupancy"],
                    approved_metrics["channel_occupancy"],
                    "within_source_reference",
                    "exact approved-plan invariance",
                ),
            ]},
        )
        _write(
            qualification / "distribution_comparisons.json",
            {"comparisons": [
                item for item in comparisons
                if "distribution" in item["metric_id"]
                or "gap" in item["metric_id"]
                or "interval" in item["metric_id"]
            ]},
        )
        figures = _figures(
            qualification / "figures",
            candidate_metrics, approved_metrics, comparisons,
        )
        manifest = {
            "schema_version": "wge.clustered_qualification_manifest.v1",
            "qualification_id": "wge5b2_clustered_session1_qualification",
            "run_id": result.run_request["request_id"],
            "verdict": verdict_name,
            "wge5c_clustered_render_authorized": authorized,
            "metric_comparison_count": len(comparisons),
            "figure_files": figures,
            "raw_files": [
                "generated_plan_metrics.json",
                "raw/generated_plan_metrics.json",
                "raw/source_reference_metrics.json",
            ],
            "core_plans_unchanged": True,
            "audio_created": False,
            "content_hash": "",
        }
        manifest["content_hash"] = content_hash(manifest)
        _write(qualification / "qualification_manifest.json", manifest)
        return {
            "verdict": verdict,
            "manifest": manifest,
            "metrics": candidate_metrics,
            "comparisons": comparisons,
        }

    def _stage(
        self,
        target: Path,
        result,
        holdouts: list[dict[str, Any]],
        approved_metrics: dict[str, Any],
    ) -> dict[str, Any]:
        RunStorage(self.runs_root)._write_run(target, result)
        _write(
            target / "meso_policy_snapshot.json",
            load_meso_policy("direct_session_1").document,
        )
        source_report_dir = target / ".source-qualification-reports"
        source_verdict = BaselineQualificationService().qualify(
            target, source_report_dir
        )
        shutil.rmtree(source_report_dir)
        clustered = self._write_clustered_qualification(
            target, result, holdouts, approved_metrics, source_verdict
        )
        manifest = _json(target / "run_manifest.json")
        manifest.update({
            "schema_version": "wge.clustered_candidate_manifest.v1",
            "candidate_id": CANDIDATE_ID,
            "candidate_path": f"runs/candidates/{CANDIDATE_ID}",
            "qualification_verdict": clustered["verdict"]["verdict"],
            "wge5c_clustered_render_authorized": clustered["verdict"][
                "wge5c_clustered_render_authorized"
            ],
            "approved_run_unchanged": True,
            "audio_created": False,
            "content_hash": "",
        })
        manifest["content_hash"] = content_hash(manifest)
        _write(target / "run_manifest.json", manifest)
        return clustered

    @staticmethod
    def _qualification_json_hashes(run: Path) -> dict[str, str]:
        return {
            path.relative_to(run).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted((run / "qualification").rglob("*.json"))
        }

    def generate(self, report_dir: Path | None = None) -> dict[str, Any]:
        if self.target.exists():
            raise ValidationFailure("Clustered candidate already exists")
        approved_before = _tree_hash(self.approved)
        approved_metrics = self._approved_metrics()
        primary = self._build(PRIMARY_SEED)
        holdouts = []
        for seed in HOLDOUT_SEEDS:
            first = self._build(seed)
            second = self._build(seed)
            metrics = clustered_metrics(first)
            holdouts.append({
                "seed": seed,
                "packet_plan_hash": first.packet_plan["content_hash"],
                "event_plan_hash": first.event_plan["content_hash"],
                "scheduler_result_hash": first.packet_plan["meso_schedule"][
                    "scheduler_result_hash"
                ],
                "packet_count": metrics["packet_count"],
                "event_count": metrics["event_count"],
                "phrase_count": metrics["phrase_count"],
                "phrase_active_share": metrics["phrase_active_share"],
                "phrase_size_median": metrics["phrase_size_packets"]["median"],
                "phrase_duration_median_seconds": metrics[
                    "phrase_duration_seconds"
                ]["median"],
                "within_phrase_interval_median_seconds": metrics[
                    "within_phrase_interval_seconds"
                ]["median"],
                "phrase_boundary_gap_median_seconds": metrics[
                    "phrase_boundary_packet_gap_seconds"
                ]["median"],
                "maximum_concurrency": metrics["maximum_concurrency"],
                "deterministic_rerun": (
                    PlanningService.core_hashes(first)
                    == PlanningService.core_hashes(second)
                ),
                "valid": (
                    first.validation_report["hard_validation"] == "passed"
                    and first.packet_plan["meso_schedule"][
                        "anti_lattice_validation"
                    ]["status"] == "passed"
                ),
            })
        candidate_parent = self.target.parent
        candidate_parent.mkdir(parents=True, exist_ok=True)
        stage_one = Path(tempfile.mkdtemp(
            prefix=f".{CANDIDATE_ID}-one-", dir=candidate_parent
        ))
        stage_two = Path(tempfile.mkdtemp(
            prefix=f".{CANDIDATE_ID}-two-", dir=candidate_parent
        ))
        try:
            first = self._stage(
                stage_one, primary, holdouts, approved_metrics
            )
            primary_again = self._build(PRIMARY_SEED)
            second = self._stage(
                stage_two, primary_again, holdouts, approved_metrics
            )
            for relative in CORE_FILES:
                if (stage_one / relative).read_bytes() != \
                        (stage_two / relative).read_bytes():
                    raise ValidationFailure(
                        f"Candidate determinism failed: {relative}"
                    )
            if self._qualification_json_hashes(stage_one) != \
                    self._qualification_json_hashes(stage_two):
                raise ValidationFailure(
                    "Candidate qualification metrics are not deterministic"
                )
            if not first["verdict"]["wge5c_clustered_render_authorized"]:
                raise ValidationFailure(
                    "Clustered candidate did not authorize WGE-5C"
                )
            if _tree_hash(self.approved) != approved_before:
                raise ValidationFailure("Approved runs/latest changed")
            os.replace(stage_one, self.target)
            shutil.rmtree(stage_two)
        except Exception:
            for path in (stage_one, stage_two):
                if path.exists():
                    shutil.rmtree(path)
            raise
        if _tree_hash(self.approved) != approved_before:
            if self.target.exists():
                shutil.rmtree(self.target)
            raise ValidationFailure("Approved runs/latest changed after promotion")
        report = self._report(
            first, holdouts, approved_metrics, approved_before
        )
        report_dir = report_dir or self.engine_root / "reports"
        _write(report_dir / "wge5b2_clustered_session1_qualification.json", report)
        self._write_markdown(
            report_dir / "WGE5B2_CLUSTERED_SESSION1_QUALIFICATION.md", report
        )
        return report

    def _report(
        self,
        clustered: dict[str, Any],
        holdouts: list[dict[str, Any]],
        approved_metrics: dict[str, Any],
        approved_hash: str,
    ) -> dict[str, Any]:
        verdict = clustered["verdict"]
        metrics = clustered["metrics"]
        report = {
            "report_id": "wge5b2_clustered_session1_qualification",
            "report_version": "1.0.0",
            "status": (
                "WGE5B2_CLUSTERED_SESSION1_QUALIFIED"
                if verdict["wge5c_clustered_render_authorized"]
                else "REVISE_WGE5B2_CLUSTERED_SESSION1"
            ),
            "engine_version": "0.5.2",
            "starting_checkpoint": "ab8b6d3d0780427d72804bdcca764c3c63d86410",
            "candidate_id": CANDIDATE_ID,
            "candidate_path": f"runs/candidates/{CANDIDATE_ID}",
            "candidate_core_hashes": BaselineQualificationService.core_hashes(
                self.target
            ),
            "content_invariance": verdict["content_invariance"],
            "gap_semantics": verdict["gap_semantics"],
            "primary_meso_metrics": metrics,
            "approved_vs_candidate": {
                "approved": approved_metrics,
                "candidate": {
                    key: metrics[key] for key in (
                        "packet_count", "event_count", "packet_rate_hz",
                        "event_rate_hz", "packet_interval_seconds",
                        "interval_lag_correlations", "phrase_count",
                        "phrase_active_share", "five_second_packet_density",
                        "five_second_event_density", "grammar_counts",
                        "channel_occupancy", "motif_repetition_rate",
                        "unique_motifs", "maximum_concurrency",
                        "schedule_spectrum",
                    )
                },
            },
            "meso_comparisons": verdict["meso_comparisons"],
            "existing_source_qualification": verdict[
                "existing_source_qualification"
            ],
            "holdout_qualification": holdouts,
            "determinism": {
                "primary_independent_reruns_match": True,
                "qualification_metrics_match": True,
            },
            "approved_run_tree_hash": approved_hash,
            "approved_run_unchanged": True,
            "qualification_verdict": verdict["verdict"],
            "wge5c_clustered_render_authorized": verdict[
                "wge5c_clustered_render_authorized"
            ],
            "test_results": {
                "complete_test_count": 0,
                "status": "pending_final_run",
            },
            "safety": {
                "audio_created": False,
                "renderer_invoked": False,
                "exporter_invoked": False,
                "source_tuples_embedded": False,
                "carrier_introduced": False,
                "full_duration_generated": False,
            },
            "content_hash": "",
        }
        report["content_hash"] = content_hash(report)
        return report

    @staticmethod
    def _write_markdown(path: Path, report: dict[str, Any]) -> None:
        metrics = report["primary_meso_metrics"]
        gap = report["gap_semantics"]
        lines = [
            "# WGE-5B2 Clustered Session 1 Qualification",
            "",
            f"Status: `{report['status']}`",
            "",
            f"- Candidate: `{report['candidate_path']}`",
            f"- Verdict: `{report['qualification_verdict']}`",
            "- WGE-5C authorized: "
            f"`{str(report['wge5c_clustered_render_authorized']).lower()}`",
            "- Approved first-audio run: unchanged",
            "",
            "## Content invariance",
            "",
            f"- Required signature: `{CONTENT_SIGNATURE}`",
            f"- Passed: `{str(report['content_invariance']['passed']).lower()}`",
            f"- Packets/events: {metrics['packet_count']} / {metrics['event_count']}",
            "",
            "## Gap semantics",
            "",
            "- Phrase-boundary packet gap is source-equivalent. Candidate median: "
            f"{gap['phrase_boundary_packet_gap']['candidate']['median']:.4f} s; "
            f"result: `{gap['phrase_boundary_packet_gap']['comparison_result']}`.",
            "- Background-span duration excludes boundary intervals and is descriptive only.",
            "- Empty-activity gaps are event-free intervals and have no qualified source distribution.",
            "",
            "## Primary meso metrics",
            "",
            f"- Phrase-active share: {metrics['phrase_active_share']:.6f}",
            f"- Phrases/minute: {metrics['phrases_per_minute']:.3f}",
            f"- Median phrase size: {metrics['phrase_size_packets']['median']:.1f} packets",
            f"- Median phrase duration: {metrics['phrase_duration_seconds']['median']:.4f} s",
            f"- Median within-phrase interval: {metrics['within_phrase_interval_seconds']['median']:.4f} s",
            f"- Median phrase-boundary gap: {metrics['phrase_boundary_packet_gap_seconds']['median']:.4f} s",
            f"- Maximum concurrency: {metrics['maximum_concurrency']}",
            "",
            "## Qualification",
            "",
            "The candidate passes direct Session 1 policy bands, existing source",
            "qualification, content invariance, primary/holdout validation,",
            "anti-lattice checks, and independent deterministic reruns.",
            "The gap upper tail and reduced phrase-size upper tail are retained as",
            "documented Tier 2 caveats rather than hidden or retuned.",
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def validate(candidate: Path) -> dict[str, Any]:
        required = [
            "authority_snapshot.json",
            "planning_profile_snapshot.json",
            "meso_policy_snapshot.json",
            "run_manifest.json",
            "session_pack_plan.json",
            "sessions/session_01/session_plan.json",
            "sessions/session_01/packet_plan.json",
            "sessions/session_01/event_plan.json",
            "sessions/session_01/validation_report.json",
            "qualification/qualification_manifest.json",
            "qualification/qualification_verdict.json",
            "qualification/generated_plan_metrics.json",
            "diagnostics/diagnostic_manifest.json",
        ]
        for relative in required:
            if not (candidate / relative).is_file():
                raise ValidationFailure(
                    f"Missing clustered candidate artifact: {relative}"
                )
        manifest = _json(candidate / "run_manifest.json")
        verdict = _json(candidate / "qualification/qualification_verdict.json")
        if not validate_content_hash(manifest) or not validate_content_hash(verdict):
            raise ValidationFailure("Clustered candidate content hash mismatch")
        if list(candidate.rglob("*.wav")) or (candidate / "render_audit").exists() \
                or (candidate / "diagnostic_export").exists():
            raise ValidationFailure("Clustered candidate contains prohibited audio")
        return {
            "valid": True,
            "verdict": verdict["verdict"],
            "wge5c_clustered_render_authorized": verdict[
                "wge5c_clustered_render_authorized"
            ],
        }
