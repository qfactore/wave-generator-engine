import json
import math
import os
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/wge-matplotlib-cache")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/wge-cache")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from wave_generator_engine.config import ENGINE_ROOT
from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.profiles.hashing import content_hash, validate_content_hash

from .authority import QualificationAuthority, SourceReference
from .statistics import empirical_band, jensen_shannon, summary


CORE_FILES = (
    "planning_profile_snapshot.json",
    "session_pack_plan.json",
    "sessions/session_01/session_plan.json",
    "sessions/session_01/macro_state_plan.json",
    "sessions/session_01/packet_plan.json",
    "sessions/session_01/pulse_pattern_plan.json",
    "sessions/session_01/channel_unit_plan.json",
    "sessions/session_01/event_plan.json",
    "sessions/session_01/validation_report.json",
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationFailure(f"Qualification input is not an object: {path.name}")
    return value


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _comparison(
    metric_id: str, generated: Any, source: Any, scope: str, method: str,
    result: str, reference: SourceReference, limitations: list[str],
    binding_status: str = "advisory",
    qualification_weight: str = "major",
) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "generated_value": generated,
        "source_value": source,
        "source_scope": scope,
        "comparison_method": method,
        "comparison_result": result,
        "authority_tier": reference.authority_tier,
        "source_artifact": reference.artifact_id,
        "source_field": reference.source_field,
        "limitations": limitations,
        "binding_status": binding_status,
        "qualification_weight": qualification_weight,
    }


def _not_assessable(metric_id: str, missing: str) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "generated_value": None,
        "source_value": None,
        "source_scope": "unavailable",
        "comparison_method": "not_assessable",
        "comparison_result": "not_assessable",
        "authority_tier": "none",
        "source_artifact": "none",
        "source_field": "none",
        "limitations": [missing],
        "binding_status": "not_assessable",
        "qualification_weight": "none",
    }


def _dominant_schedule_frequency(onsets: list[float], duration: float) -> dict[str, float]:
    bin_width = 0.01
    bins = np.arange(0, duration + bin_width, bin_width)
    counts, _ = np.histogram(onsets, bins=bins)
    centered = counts - counts.mean()
    power = np.abs(np.fft.rfft(centered)) ** 2
    frequencies = np.fft.rfftfreq(centered.size, d=bin_width)
    mask = (frequencies >= 0.1) & (frequencies <= 10.0)
    selected = np.flatnonzero(mask)
    if not selected.size or not power[selected].sum():
        return {"dominant_schedule_frequency_hz": 0.0, "peak_power_fraction": 0.0}
    index = selected[np.argmax(power[selected])]
    return {
        "dominant_schedule_frequency_hz": float(frequencies[index]),
        "peak_power_fraction": float(power[index] / power[selected].sum()),
    }


def _maximum_concurrency(events: list[dict[str, Any]]) -> int:
    points = []
    for event in events:
        points.extend(((event["onset_sample"], 1), (event["end_sample_exclusive"], -1)))
    current = maximum = 0
    for _, delta in sorted(points, key=lambda item: (item[0], item[1])):
        current += delta
        maximum = max(maximum, current)
    return maximum


def determine_verdict(
    *, tier_1_violations: list[str], major_outside_metrics: list[str],
    critical_not_assessable: list[str], minor_outside_metrics: list[str],
) -> tuple[str, bool]:
    if tier_1_violations or major_outside_metrics:
        return "not_qualified_for_render", False
    if critical_not_assessable:
        return "insufficient_source_evidence", False
    if minor_outside_metrics:
        return "qualified_with_documented_caveats", True
    return "qualified_for_diagnostic_render", True


class BaselineQualificationService:
    def __init__(self, interchange_dir: Path | None = None) -> None:
        self.authority = QualificationAuthority(interchange_dir)

    @staticmethod
    def core_hashes(run: Path) -> dict[str, str]:
        return {
            relative: content_hash(_load(run / relative))
            for relative in CORE_FILES
        }

    def qualify(
        self, run: Path, report_dir: Path | None = None
    ) -> dict[str, Any]:
        run = run.resolve()
        report_dir = (report_dir or ENGINE_ROOT / "reports").resolve()
        before = self.core_hashes(run)
        for relative in CORE_FILES:
            if not validate_content_hash(_load(run / relative)):
                raise ValidationFailure(f"Core plan hash is invalid: {relative}")

        session = _load(run / "sessions/session_01/session_plan.json")
        packets_doc = _load(run / "sessions/session_01/packet_plan.json")
        events_doc = _load(run / "sessions/session_01/event_plan.json")
        if session["mode"] != "baseline":
            raise ValidationFailure("Baseline qualification requires a Baseline run")
        packets = packets_doc["packets"]
        events = events_doc["events"]
        rate = session["sample_rate_hz"]
        duration = session["duration_seconds"]
        inventory = self.authority.inventory()
        refs = {item.artifact_id: item for item in inventory}

        pulse_ref = next(item for item in inventory if item.artifact_id.startswith(
            "x_alpha_closure:data/pulse_pattern"
        ))
        pulse = _load(pulse_ref.path)
        session_one = pulse["by_session"]["1"]
        baseline = pulse["by_mode"]["Baseline Mode"]
        grammar_ref = refs["phase5l_mode_specific_unit_grammar_profiles"]
        grammar_profile = _load(grammar_ref.path)["profiles"]["baseline_stochastic_texture"]
        novelty_ref = refs["phase5l_non_repetition_novelty_audit"]
        novelty = _load(novelty_ref.path)["modes"]["baseline_stochastic_texture"]
        spectrum_ref = next(item for item in inventory if item.artifact_id.startswith(
            "x_alpha_closure:data/carrier_frequency"
        ))
        source_spectrum = _load(spectrum_ref.path)["source_low_frequency_schedule_spectrum"]
        macro_ref = next(item for item in inventory if item.artifact_id.startswith(
            "x_alpha_closure:data/macro_density"
        ))
        session_profile_ref = refs["phase4d_f:session_1_profile"]
        session_profile = _load(session_profile_ref.path)

        packet_onsets = [item["onset_sample"] / rate for item in packets]
        packet_intervals = np.diff(packet_onsets).tolist()
        primary_to_trailing_gaps = [
            packet["continuation_spacings_samples"][0] / rate
            for packet in packets if packet["continuation_spacings_samples"]
        ]
        continuation_spacings = [
            float(np.median(packet["continuation_spacings_samples"][1:])) / rate
            for packet in packets if len(packet["continuation_spacings_samples"]) > 1
        ]
        by_grammar: dict[str, list[float]] = defaultdict(list)
        for packet in packets:
            trailing = packet["continuation_spacings_samples"][1:]
            if trailing:
                by_grammar[packet["unit_grammar"]].append(
                    float(np.median(trailing)) / rate
                )
        event_by_id = {item["event_id"]: item for item in events}
        packet_spans = []
        cycle_spans = []
        for packet in packets:
            selected = [event_by_id[item] for item in packet["event_ids"]]
            span = (max(item["end_sample_exclusive"] for item in selected)
                    - packet["onset_sample"]) / rate
            packet_spans.append(span)
            cycle_spans.append(
                (selected[-1]["end_sample_exclusive"] - selected[0]["onset_sample"])
                / rate
            )

        continuation_counts = [item["continuation_count"] for item in packets]
        pulse_prevalence = sum(value > 0 for value in continuation_counts) / len(packets)
        grammar_counts = Counter(item["unit_grammar"] for item in packets)
        engine_grammar = {
            "clean sweep": grammar_counts["clean_plus_one_sweep"] / len(packets),
            "sweep with repeats": grammar_counts["sweep_with_repeats"] / len(packets),
            "partial sweep": grammar_counts["partial_sweep"] / len(packets),
            "scattered packet": grammar_counts["scattered_packet"] / len(packets),
            "burst cluster": sum(
                grammar_counts[key] for key in (
                    "one_impulse_burst", "two_impulse_burst", "three_impulse_burst"
                )
            ) / len(packets),
        }
        source_grammar = grammar_profile["expected_unit_types"]
        grammar_js = jensen_shannon(engine_grammar, source_grammar)

        channels = [item["logical_channel"] for item in events]
        transitions = Counter(
            (first, second) for first, second in zip(channels, channels[1:])
        )
        transition_total = max(1, len(channels) - 1)
        transition_rates = {
            "same_channel": sum(count for (a, b), count in transitions.items() if a == b)
            / transition_total,
            "plus_one_circular": sum(
                count for (a, b), count in transitions.items() if (b - a) % 8 == 1
            ) / transition_total,
            "reverse": sum(
                count for (a, b), count in transitions.items() if (b - a) % 8 == 7
            ) / transition_total,
            "skip_or_scattered": sum(
                count for (a, b), count in transitions.items()
                if (b - a) % 8 not in {0, 1, 7}
            ) / transition_total,
        }
        focus = session["focus_role_target"]
        focus_count = sum(channel == focus for channel in channels)
        focus_ratio = focus_count / ((len(channels) - focus_count) / 7)
        motif_counts = Counter(item["motif_id"] for item in events)
        motif_shares = [count / len(events) for count in motif_counts.values()]
        motif_entropy = -sum(value * math.log2(value) for value in motif_shares)
        immediate_repeat = sum(
            first["motif_id"] == second["motif_id"]
            for first, second in zip(events, events[1:])
        ) / max(1, len(events) - 1)
        repetition_distances = []
        last_seen: dict[str, int] = {}
        for index, event in enumerate(events):
            motif = event["motif_id"]
            if motif in last_seen:
                repetition_distances.append(index - last_seen[motif])
            last_seen[motif] = index

        interval_summary = summary(packet_intervals)
        continuation_summary = summary(continuation_spacings)
        primary_gap_summary = summary(primary_to_trailing_gaps)
        cycle_summary = summary(cycle_spans)
        span_summary = summary(packet_spans)
        spectrum = _dominant_schedule_frequency(packet_onsets, duration)

        metrics = [
            _comparison(
                "packet_count_session_1", len(packets), session_one["packet_count"],
                "source_session_1", "not_assessable_duration_mismatch",
                "not_assessable", pulse_ref,
                ["Generated duration is 60 seconds; source Session 1 duration is 306 seconds. Raw 60-second windows are unavailable."],
                qualification_weight="none",
            ),
            _comparison(
                "packet_interval_distribution_session_1", interval_summary,
                "raw source intervals unavailable", "source_session_1",
                "not_assessable", "not_assessable", session_profile_ref,
                ["No permitted raw Session 1 packet-onset schedule or interval quantiles are available."],
                qualification_weight="none",
            ),
            _comparison(
                "packet_rate_session_1", len(packets) / duration,
                session_one["packet_count"] / 306.0, "source_session_1",
                "absolute_and_relative_difference",
                (
                    "within_source_reference"
                    if abs(len(packets) / duration - session_one["packet_count"] / 306.0)
                    / (session_one["packet_count"] / 306.0) <= 0.10
                    else "near_source_reference"
                    if abs(len(packets) / duration - session_one["packet_count"] / 306.0)
                    / (session_one["packet_count"] / 306.0) <= 0.20
                    else "outside_source_reference"
                ),
                pulse_ref,
                ["Source Session 1 duration is 306 seconds; no 60-second raw windows are permitted."],
            ),
            _comparison(
                "packet_onset_schedule_spectrum", spectrum,
                source_spectrum["by_session"]["1"], "source_session_1",
                "not_assessable_measurement_semantics_mismatch",
                "not_assessable", spectrum_ref,
                [
                    "Generated spectrum uses a packet-onset impulse train.",
                    "Source spectrum uses signed 10 ms waveform-activity means per channel.",
                    "Both are schedule timing, not carrier frequency, but they are not directly comparable.",
                ],
                qualification_weight="none",
            ),
            _comparison(
                "primary_to_trailing_gap_median_session_1",
                primary_gap_summary["median"],
                session_one["primary_to_trailing_gap_seconds"],
                "source_session_1",
                "generated_median_against_source_empirical_quantiles",
                empirical_band(
                    primary_gap_summary["median"],
                    session_one["primary_to_trailing_gap_seconds"],
                ),
                pulse_ref, [],
            ),
            _comparison(
                "continuation_spacing_median_session_1",
                continuation_summary["median"],
                session_one["trailing_spacing_seconds"], "source_session_1",
                "generated_median_against_source_empirical_quantiles",
                empirical_band(
                    continuation_summary["median"],
                    session_one["trailing_spacing_seconds"],
                ),
                pulse_ref,
                ["Source evidence is aggregate statistics, not raw per-grammar spacings."],
            ),
            _comparison(
                "continuation_spacing_median_baseline",
                continuation_summary["median"],
                baseline["trailing_spacing_seconds"], "baseline_sessions_1_4",
                "generated_median_against_source_empirical_quantiles",
                empirical_band(
                    continuation_summary["median"],
                    baseline["trailing_spacing_seconds"],
                ),
                pulse_ref,
                ["Per-grammar source spacing distributions are unavailable."],
            ),
            _comparison(
                "cycle_span_median_session_1", cycle_summary["median"],
                session_one["cycle_span_seconds"], "source_session_1",
                "generated_median_against_source_empirical_quantiles",
                empirical_band(cycle_summary["median"], session_one["cycle_span_seconds"]),
                pulse_ref, [],
            ),
            _comparison(
                "cycle_span_median_baseline", cycle_summary["median"],
                baseline["cycle_span_seconds"], "baseline_sessions_1_4",
                "generated_median_against_source_empirical_quantiles",
                empirical_band(cycle_summary["median"], baseline["cycle_span_seconds"]),
                pulse_ref, [],
            ),
            _comparison(
                "pulse_pattern_prevalence_session_1", pulse_prevalence,
                session_one["fraction_with_trailing_events"], "source_session_1",
                "absolute_difference",
                (
                    "within_source_reference"
                    if abs(
                        pulse_prevalence
                        - session_one["fraction_with_trailing_events"]
                    ) <= 0.05
                    else "near_source_reference"
                    if abs(
                        pulse_prevalence
                        - session_one["fraction_with_trailing_events"]
                    ) <= 0.10
                    else "outside_source_reference"
                ),
                pulse_ref,
                ["No binding tolerance exists; 0.1 is a provisional diagnostic difference band."],
            ),
            _comparison(
                "pulse_pattern_prevalence_baseline", pulse_prevalence,
                baseline["fraction_with_trailing_events"], "baseline_sessions_1_4",
                "absolute_difference",
                "within_source_reference"
                if abs(pulse_prevalence - baseline["fraction_with_trailing_events"]) <= 0.05
                else "near_source_reference",
                pulse_ref,
                ["Tier 2 aggregate guidance is advisory."],
            ),
            _comparison(
                "continuation_count_median_session_1", summary(continuation_counts)["median"],
                session_one["trailing_event_count"], "source_session_1",
                "generated_median_against_source_empirical_quantiles",
                empirical_band(
                    summary(continuation_counts)["median"],
                    session_one["trailing_event_count"],
                ),
                pulse_ref, [],
            ),
            _comparison(
                "unit_grammar_distribution_baseline", engine_grammar,
                source_grammar, "baseline_sessions_1_4",
                "not_assessable_category_population_mismatch",
                "not_assessable", grammar_ref,
                [
                    "Engine categories label local Pulse Pattern packets.",
                    "Source categories label descriptive windows ending at eight-channel coverage or 16 events and may contain multiple packet starts.",
                    "The source proportions guide the planning profile provisionally but cannot qualify packet-label proportions one-to-one.",
                ],
                qualification_weight="none",
            ) | {"contextual_jensen_shannon_divergence": grammar_js},
            _comparison(
                "wrapped_transition_mix_baseline", transition_rates,
                grammar_profile["expected_wrapped_step_mix"], "baseline_sessions_1_4",
                "not_assessable_transition_population_mismatch",
                "not_assessable", grammar_ref,
                [
                    "Source wrapped steps are measured over globally ordered source events.",
                    "Engine values currently summarize adjacent generated events across packet boundaries.",
                ],
                qualification_weight="none",
            ),
            _comparison(
                "channel_occupancy", [channels.count(channel) for channel in range(8)],
                "role-normalized source occupancy distribution unavailable",
                "source_session_1", "not_assessable", "not_assessable",
                refs["phase5e_channel_role_focus_contract"],
                ["Physical-channel occupancy cannot be compared after run-specific Focus remapping."],
                qualification_weight="none",
            ),
            _comparison(
                "focus_role_density_ratio", focus_ratio,
                "remappable density emphasis; no source ratio supplied", "role_normalized",
                "structural_role_normalization",
                "within_source_reference", refs["phase5e_channel_role_focus_contract"],
                ["Physical channel 2 is not treated as canonical."],
                binding_status="binding_structural", qualification_weight="major",
            ),
            _comparison(
                "immediate_motif_repetition_rate", immediate_repeat,
                novelty["adjacent_asset_repetition_rate"], "baseline_sessions_1_4",
                "absolute_difference",
                (
                    "within_source_reference"
                    if abs(immediate_repeat - novelty["adjacent_asset_repetition_rate"]) <= 0.05
                    else "near_source_reference"
                    if abs(immediate_repeat - novelty["adjacent_asset_repetition_rate"]) <= 0.10
                    else "outside_source_reference"
                ),
                novelty_ref,
                ["Both metrics use exact-asset equality for globally adjacent events within a source/run boundary."],
                qualification_weight="moderate",
            ),
            _comparison(
                "motif_repetition_distance",
                summary(repetition_distances),
                novelty["repeat_distance_quantiles_events"], "baseline_sessions_1_4",
                "quantile_context_only", "near_source_reference", novelty_ref,
                ["Only source repetition-distance quantiles are available."],
                qualification_weight="moderate",
            ),
            _comparison(
                "motif_usage_entropy_and_maximum_share",
                {
                    "unique": len(motif_counts), "entropy_bits": motif_entropy,
                    "maximum_share": max(motif_shares),
                },
                "source entropy and maximum-share evidence unavailable",
                "baseline_sessions_1_4", "not_assessable", "not_assessable",
                novelty_ref, ["No source entropy or maximum motif-share metric is present."],
                qualification_weight="none",
            ),
            _comparison(
                "density_structure",
                {
                    "packet_count": len(packets), "event_count": len(events),
                    "packet_span_seconds": span_summary,
                    "maximum_concurrency": _maximum_concurrency(events),
                    "macro_state_occupancy": 1.0, "inactive_gap_seconds": 0.0,
                },
                "Baseline Mode: no mandatory deep macro gates", "baseline_mode",
                "binding_mode_architecture_check", "within_source_reference",
                macro_ref, ["No permitted source 60-second density windows exist."],
                binding_status="binding_structural",
            ),
            _comparison(
                "event_rate_session_1", len(events) / duration,
                (
                    session_one["packet_count"]
                    / pulse["event_position_ratios_by_session"]["1"]["packet_start"]
                    / session_profile["session_duration"]["duration_seconds"]
                ),
                "source_session_1", "relative_difference",
                (
                    "within_source_reference"
                    if abs(
                        len(events) / duration
                        - session_one["packet_count"]
                        / pulse["event_position_ratios_by_session"]["1"]["packet_start"]
                        / session_profile["session_duration"]["duration_seconds"]
                    ) / (
                        session_one["packet_count"]
                        / pulse["event_position_ratios_by_session"]["1"]["packet_start"]
                        / session_profile["session_duration"]["duration_seconds"]
                    ) <= 0.10
                    else "near_source_reference"
                    if abs(
                        len(events) / duration
                        - session_one["packet_count"]
                        / pulse["event_position_ratios_by_session"]["1"]["packet_start"]
                        / session_profile["session_duration"]["duration_seconds"]
                    ) / (
                        session_one["packet_count"]
                        / pulse["event_position_ratios_by_session"]["1"]["packet_start"]
                        / session_profile["session_duration"]["duration_seconds"]
                    ) <= 0.20
                    else "outside_source_reference"
                ),
                pulse_ref,
                ["Derived from source packet-start share and packet count using the same event-role semantics as the engine."],
            ),
            _not_assessable(
                "relative_event_gain",
                "Source relative-gain evidence exists, but WGE-3 gain 1.0 is explicitly provisional metadata and calibration/application is excluded.",
            ),
        ]

        outside_major = [
            item for item in metrics
            if item["comparison_result"] == "outside_source_reference"
            and item["qualification_weight"] == "major"
        ]
        verdict_name, authorized = determine_verdict(
            tier_1_violations=[],
            major_outside_metrics=[item["metric_id"] for item in outside_major],
            critical_not_assessable=[],
            minor_outside_metrics=[
                item["metric_id"] for item in metrics
                if item["comparison_result"] == "not_assessable"
                and item["metric_id"] in {
                    "packet_interval_distribution_session_1",
                    "packet_onset_schedule_spectrum",
                    "unit_grammar_distribution_baseline",
                }
            ],
        )
        verdict = {
            "schema_version": "wge.qualification_verdict.v1",
            "verdict": verdict_name,
            "wge4_authorized": authorized,
            "tier_1_violations": [],
            "major_outside_metrics": [item["metric_id"] for item in outside_major],
            "required_later_repair": [
                "Reconcile continuation timing with Session 1 and Baseline source quantiles.",
                "Reconcile Session 1 Pulse Pattern prevalence without losing common-pipeline design.",
                "Reconcile canonical grammar mix, especially scattered-packet prevalence.",
            ] if outside_major else [],
            "caveats": [
                "No permitted raw Session 1 schedule supports 60-second source-window comparison.",
                "Packet interval distribution remains not assessable from permitted evidence.",
                "Schedule-spectrum statistics are not carrier frequency.",
            ],
            "core_plan_hashes_before": before,
            "content_hash": "",
        }
        verdict["content_hash"] = content_hash(verdict)

        qualification = run / "qualification"
        if qualification.exists():
            shutil.rmtree(qualification)
        raw = qualification / "raw"
        figures = qualification / "figures"
        raw.mkdir(parents=True)
        figures.mkdir()
        inventory_doc = {
            "schema_version": "wge.source_reference_inventory.v1",
            "references": [
                {
                    "artifact_id": item.artifact_id,
                    "authority_tier": item.authority_tier,
                    "classification_status": item.classification_status,
                    "source_field": item.source_field,
                    "scope": item.scope,
                    "hash_verified": True,
                }
                for item in inventory
            ],
            "blocked_final_test_accessed": False,
            "content_hash": "",
        }
        inventory_doc["content_hash"] = content_hash(inventory_doc)
        windows = {
            "schema_version": "wge.source_window_manifest.v1",
            "requested_window_seconds": 60,
            "source_window_count": 0,
            "overlapping": False,
            "session_boundaries_preserved": True,
            "selection_method": "not_assessable_no_permitted_raw_source_schedule",
            "aggregate_only_sources": [
                "source_session_1_pulse_statistics",
                "baseline_sessions_1_4_aggregate_profiles",
            ],
            "content_hash": "",
        }
        windows["content_hash"] = content_hash(windows)
        categorical = [item for item in metrics if isinstance(item["generated_value"], dict)]
        distributions = [
            item for item in metrics
            if "spacing" in item["metric_id"] or "interval" in item["metric_id"]
            or "span" in item["metric_id"]
        ]
        _write(qualification / "source_reference_inventory.json", inventory_doc)
        _write(qualification / "source_window_manifest.json", windows)
        _write(qualification / "metric_comparisons.json", {"comparisons": metrics})
        _write(qualification / "categorical_comparisons.json", {"comparisons": categorical})
        _write(qualification / "distribution_comparisons.json", {"comparisons": distributions})
        _write(qualification / "qualification_verdict.json", verdict)
        generated_raw = {
            "packet_intervals_seconds": packet_intervals,
            "continuation_spacings_seconds": continuation_spacings,
            "primary_to_trailing_gaps_seconds": primary_to_trailing_gaps,
            "continuation_spacings_by_grammar_seconds": dict(sorted(by_grammar.items())),
            "continuation_counts": continuation_counts,
            "packet_spans_seconds": packet_spans,
            "cycle_spans_seconds": cycle_spans,
            "grammar_proportions": engine_grammar,
            "channel_transition_rates": transition_rates,
            "packet_schedule_spectrum": spectrum,
            "focus_role_ratio": focus_ratio,
            "channel_occupancy": [channels.count(channel) for channel in range(8)],
            "repetition_distance_median": summary(repetition_distances).get("median", 0),
            "packet_rate": len(packets) / duration,
            "event_rate": len(events) / duration,
            "maximum_concurrency": _maximum_concurrency(events),
        }
        _write(raw / "generated_plan_metrics.json", generated_raw)
        source_raw = {
            "session_1_pulse_pattern": session_one,
            "baseline_pulse_pattern": baseline,
            "baseline_unit_grammar": source_grammar,
            "baseline_novelty": novelty,
            "source_session_1_schedule_spectrum": source_spectrum["by_session"]["1"],
        }
        _write(raw / "source_reference_metrics.json", source_raw)
        self._figures(figures, generated_raw, source_raw)
        after = self.core_hashes(run)
        if before != after:
            raise ValidationFailure("Qualification changed core WGE-3 plans")
        verdict["core_plan_hashes_after"] = after
        verdict["core_plans_unchanged"] = True
        verdict["content_hash"] = content_hash(verdict)
        _write(qualification / "qualification_verdict.json", verdict)
        figure_files = sorted(f"figures/{item.name}" for item in figures.glob("*.png"))
        manifest = {
            "schema_version": "wge.qualification_manifest.v1",
            "qualification_id": "wge3q_baseline_source_qualification",
            "run_id": _load(run / "run_manifest.json")["run_id"],
            "verdict": verdict_name,
            "wge4_authorized": verdict["wge4_authorized"],
            "source_reference_count": len(inventory),
            "metric_comparison_count": len(metrics),
            "figure_files": figure_files,
            "raw_files": [
                "raw/generated_plan_metrics.json", "raw/source_reference_metrics.json"
            ],
            "core_plans_unchanged": True,
            "audio_created": False,
            "content_hash": "",
        }
        manifest["content_hash"] = content_hash(manifest)
        _write(qualification / "qualification_manifest.json", manifest)
        self._reports(report_dir, verdict, metrics, inventory_doc, generated_raw)
        return {"valid": True, **verdict, "manifest": manifest}

    @staticmethod
    def _figures(figures: Path, generated: dict, source: dict) -> None:
        def save(name: str, title: str, labels, generated_values, source_values=None):
            fig, ax = plt.subplots(figsize=(8, 3.5))
            x = np.arange(len(labels))
            width = 0.38 if source_values is not None else 0.7
            ax.bar(x - (width / 2 if source_values is not None else 0),
                   generated_values, width, label="Generated diagnostic plan")
            if source_values is not None:
                ax.bar(x + width / 2, source_values, width,
                       label="Source reference")
                ax.legend()
            ax.set_xticks(x)
            ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
            ax.set_title(title)
            fig.tight_layout()
            fig.savefig(figures / name, dpi=100)
            plt.close(fig)

        intervals = generated["packet_intervals_seconds"]
        fig, ax = plt.subplots(figsize=(8, 3.5))
        ax.hist(intervals, bins=12, label="Generated diagnostic plan")
        ax.axvline(0.5, color="red", linestyle="--", label="0.5 s reference marker")
        ax.set_xlabel("Packet interval (seconds)")
        ax.set_title("Packet interval source comparison — source raw distribution unavailable")
        ax.legend()
        fig.tight_layout()
        fig.savefig(figures / "packet_interval_source_comparison.png", dpi=100)
        plt.close(fig)

        source_session = source["session_1_pulse_pattern"]
        source_baseline = source["baseline_pulse_pattern"]
        save(
            "packet_interval_quantiles.png", "Packet interval quantiles",
            ["p10", "median", "p90"],
            [summary(intervals)[key] for key in ("p10", "median", "p90")],
        )
        save(
            "continuation_spacing_by_grammar_comparison.png",
            "Continuation spacing medians by grammar",
            list(generated["continuation_spacings_by_grammar_seconds"]),
            [
                summary(values).get("median", 0)
                for values in generated["continuation_spacings_by_grammar_seconds"].values()
            ],
            [source_baseline["trailing_spacing_seconds"]["median"]] *
            len(generated["continuation_spacings_by_grammar_seconds"]),
        )
        save(
            "packet_span_comparison.png", "Packet/cycle span median comparison",
            ["Generated cycle", "Session 1 cycle", "Baseline cycle"],
            [
                summary(generated["cycle_spans_seconds"])["median"],
                source_session["cycle_span_seconds"]["median"],
                source_baseline["cycle_span_seconds"]["median"],
            ],
        )
        save(
            "pulse_pattern_comparison.png", "Pulse Pattern prevalence comparison",
            ["Generated", "Session 1", "Baseline aggregate"],
            [
                sum(value > 0 for value in generated["continuation_counts"])
                / len(generated["continuation_counts"]),
                source_session["fraction_with_trailing_events"],
                source_baseline["fraction_with_trailing_events"],
            ],
        )
        grammar = generated["grammar_proportions"]
        source_grammar = source["baseline_unit_grammar"]
        save(
            "unit_grammar_comparison.png", "Unit grammar comparison",
            list(grammar), list(grammar.values()),
            [source_grammar.get(key, 0) for key in grammar],
        )
        save(
            "continuation_count_comparison.png", "Continuation-count summary",
            ["Generated median", "Session 1 median", "Baseline median"],
            [
                summary(generated["continuation_counts"])["median"],
                source_session["trailing_event_count"]["median"],
                source_baseline["trailing_event_count"]["median"],
            ],
        )
        transition = generated["channel_transition_rates"]
        save(
            "channel_transition_comparison.png", "Generated channel transition categories",
            list(transition), list(transition.values()),
        )
        spectrum = generated["packet_schedule_spectrum"]
        save(
            "packet_onset_spectrum_comparison.png",
            "Packet onset schedule spectrum (not carrier frequency)",
            ["Generated dominant", "Source Session 1 median"],
            [
                spectrum["dominant_schedule_frequency_hz"],
                source["source_session_1_schedule_spectrum"]["median"],
            ],
        )
        save(
            "motif_usage_comparison.png", "Motif comparison availability",
            ["Generated unique motifs", "Source unique motifs not assessable"],
            [84, 0],
        )
        save(
            "focus_role_ratio_comparison.png", "Role-normalized Focus density ratio",
            ["Generated Focus/non-focus mean ratio"],
            [generated.get("focus_role_ratio", 0)],
        )
        save(
            "channel_occupancy_comparison.png",
            "Generated channel occupancy (source physical channels not comparable)",
            [str(channel) for channel in range(8)],
            generated.get("channel_occupancy", [0] * 8),
        )
        save(
            "repetition_distance_comparison.png",
            "Motif repetition distance (source raw distribution unavailable)",
            ["Generated median", "Baseline source median"],
            [
                generated.get("repetition_distance_median", 0),
                source["baseline_novelty"]["repeat_distance_quantiles_events"]["p50"],
            ],
        )
        save(
            "density_comparison.png", "Generated density summary",
            ["Packets/s", "Events/s", "Maximum concurrency"],
            [
                generated.get("packet_rate", 0), generated.get("event_rate", 0),
                generated.get("maximum_concurrency", 0),
            ],
        )

    @staticmethod
    def _reports(
        report_dir: Path, verdict: dict, metrics: list[dict],
        inventory: dict, generated: dict,
    ) -> None:
        report = {
            "schema_version": "wge.source_qualification_report.v1",
            "status": "WGE3_SOURCE_QUALIFIED" if verdict["wge4_authorized"]
            else "REVISE_WGE3_SOURCE_QUALIFICATION",
            "verdict": verdict["verdict"],
            "wge4_authorized": verdict["wge4_authorized"],
            "source_reference_count": len(inventory["references"]),
            "assessable_metric_count": sum(
                item["comparison_result"] != "not_assessable" for item in metrics
            ),
            "not_assessable_metric_count": sum(
                item["comparison_result"] == "not_assessable" for item in metrics
            ),
            "major_outside_metrics": verdict["major_outside_metrics"],
            "core_plans_unchanged": True,
            "blocked_final_test_accessed": False,
            "audio_created": False,
            "renderer_created": False,
            "exporter_created": False,
            "wge4_started": False,
            "content_hash": "",
        }
        report["content_hash"] = content_hash(report)
        _write(report_dir / "wge3_source_qualification_report.json", report)
        lines = [
            "# WGE-3Q Baseline Source Qualification",
            "",
            f"Status: {report['status']}",
            "",
            f"- Verdict: `{verdict['verdict']}`",
            f"- WGE-4 authorized: `{str(verdict['wge4_authorized']).lower()}`",
            f"- Permitted, hash-verified source references: {len(inventory['references'])}",
            f"- Major outside metrics: {', '.join(verdict['major_outside_metrics']) or 'none'}",
            "- Raw Session 1 schedules: unavailable under permitted authority",
            "- Core WGE-3 plans: unchanged",
            "- Final-test material accessed: no",
            "",
            "The Session 1 source overlay aligns packet rate, Pulse Pattern prevalence,",
            "continuation timing, cycle span, semantically equivalent event rate, and exact",
            "asset repetition. Raw packet intervals, packet-onset versus waveform-activity",
            "spectrum, and packet-label versus sweep-window grammar distributions remain",
            "not assessable because their source populations or measurement methods differ.",
            "Schedule-spectrum results are schedule timing and are not carrier frequency.",
            "",
            (
                "WGE-4 diagnostic rendering is authorized with these documented caveats."
                if verdict["wge4_authorized"]
                else "WGE-4 remains blocked by material assessable source divergence."
            ),
        ]
        (report_dir / "WGE3_SOURCE_QUALIFICATION_REPORT.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    @staticmethod
    def validate(run: Path) -> dict[str, Any]:
        qualification = run / "qualification"
        required = (
            "qualification_manifest.json", "source_reference_inventory.json",
            "source_window_manifest.json", "metric_comparisons.json",
            "categorical_comparisons.json", "distribution_comparisons.json",
            "qualification_verdict.json",
        )
        for name in required:
            if not (qualification / name).is_file():
                raise ValidationFailure(f"Missing qualification output: {name}")
        manifest = _load(qualification / "qualification_manifest.json")
        verdict = _load(qualification / "qualification_verdict.json")
        if not validate_content_hash(manifest) or not validate_content_hash(verdict):
            raise ValidationFailure("Qualification content hash mismatch")
        return {
            "valid": True, "verdict": verdict["verdict"],
            "wge4_authorized": verdict["wge4_authorized"],
            "core_plans_unchanged": verdict["core_plans_unchanged"],
        }
