import inspect
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.planning.modes.baseline import BaselinePlanner
from wave_generator_engine.planning.profile_resolver import (
    PlanningProfileResolver, validate_session_overlay,
)
from wave_generator_engine.planning.service import PlanningService
from wave_generator_engine.planning.validation import validate_channel_grammar
from wave_generator_engine.profiles.hashing import validate_content_hash
from wave_generator_engine.qualification.service import BaselineQualificationService

ROOT = Path(__file__).resolve().parents[1]
REQUEST = json.loads(
    (ROOT / "examples/run_requests/x_alpha_session1_diagnostic_60s.json").read_text()
)


@pytest.fixture(scope="module")
def seeded_results():
    service = PlanningService()
    output = {}
    for seed in (20260622, 20260623, 20260624):
        request = dict(REQUEST)
        request["root_seed"] = seed
        request["request_id"] = f"session1_source_alignment_{seed}"
        output[seed] = service.build(request)
    return output


def test_metric_semantics_audit_documents_equivalence_and_mismatches() -> None:
    audit = json.loads((ROOT / "reports/wge3s_metric_semantics_audit.json").read_text())
    findings = audit["findings"]
    assert findings["source_packet"]["engine_equivalent"]
    assert findings["source_event"]["engine_equivalent"]
    assert findings["clean_plus_one_sweep"]["canonical_engine_event_count"] == 8
    assert not findings["schedule_spectrum"]["engine_equivalent"]
    assert not findings["grammar_categories"]["one_to_one_mapping"]
    assert findings["immediate_motif_repetition"]["scope"] == \
        "global_adjacent_events_within_run"


def test_session1_planning_profile_validates_and_is_locked() -> None:
    path = ROOT / "profiles/planning_profiles/x_alpha_session_01_baseline_v1.json"
    document = json.loads(path.read_text())
    schema = json.loads((ROOT / "schemas/session_planning_profile.schema.json").read_text())
    Draft202012Validator(schema).validate(document)
    assert validate_content_hash(document)
    assert document["source_profile_hash"] == \
        "41eeb636c411de429f316f0b84cbcd1ff0e4598400f4ee2d1e310582f44e0578"
    assert document["user_editable"] is False


def test_session_profile_selection_is_data_driven_and_not_in_planner_branch() -> None:
    resolver = PlanningProfileResolver()
    _, _, session_one, _ = resolver.resolve(
        "x_alpha_standard_v1", "diagnostic_60s_v1", 1
    )
    assert session_one["session_planning_profile"]["planning_profile_id"] == \
        "x_alpha_session_01_baseline_v1"
    for session_id in (2, 3, 4):
        _, _, other, _ = resolver.resolve(
            "x_alpha_standard_v1", "diagnostic_60s_v1", session_id
        )
        assert other["session_planning_profile"] is None
    source = inspect.getsource(BaselinePlanner)
    assert "session_id == 1" not in source
    assert "if session_id" not in source


def test_canonical_clean_plus_one_is_exact_eight_event_traversal() -> None:
    validate_channel_grammar({
        "unit_grammar": "clean_plus_one_sweep",
        "channel_sequence": [3, 4, 5, 6, 7, 0, 1, 2],
    })
    for invalid in (
        [3, 4, 5, 6, 7, 0, 1],
        [3, 4, 5, 6, 7, 0, 1, 2, 3],
    ):
        with pytest.raises(ValidationFailure, match="unit_grammar_structure"):
            validate_channel_grammar({
                "unit_grammar": "clean_plus_one_sweep",
                "channel_sequence": invalid,
            })


def test_profile_drives_grammar_without_post_generation_quota() -> None:
    profile = json.loads(
        (ROOT / "profiles/planning_profiles/x_alpha_session_01_baseline_v1.json").read_text()
    )
    weights = profile["parameters"]["grammar_weights"]["value"]
    assert weights["scattered_packet"] > weights["partial_sweep"] > \
        weights["clean_plus_one_sweep"]
    source = inspect.getsource(BaselinePlanner.plan)
    assert "_weighted_choice" in source
    assert "target_count" not in source
    assert "grammar_quota" not in source


def test_invalid_profile_grammar_mapping_fails_closed() -> None:
    profile = json.loads(
        (ROOT / "profiles/planning_profiles/x_alpha_session_01_baseline_v1.json").read_text()
    )
    profile["parameters"]["grammar_weights"]["value"]["ambiguous_source_category"] = 0.1
    with pytest.raises(ValidationFailure, match="grammar mapping"):
        validate_session_overlay(profile)


def test_primary_and_holdout_timing_rates_are_source_aligned(seeded_results) -> None:
    for result in seeded_results.values():
        counts = result.validation_report["counts"]
        advisory = result.validation_report["advisory_conformance"]
        packet_rate = counts["packets"] / 60
        event_rate = counts["events"] / 60
        assert 2.2 <= packet_rate <= 2.7
        assert 13.4 <= event_rate <= 16.4
        assert counts["packet_interval_statistics"]["variance_samples_squared"] > 0
        assert counts["pulse_pattern_prevalence"] >= 0.95
        assert advisory["pulse_pattern_prevalence"] == "within_reference"
        assert advisory["pulse_pattern_reference_scope"] == "direct_session_1"
        assert 0.40 <= counts["immediate_motif_repetition_rate"] <= 0.60
        assert counts["unique_motifs"] >= 50


def test_continuation_timing_uses_source_aligned_per_packet_semantics(
    seeded_results,
) -> None:
    for result in seeded_results.values():
        medians = []
        grammar_medians = {}
        for packet in result.packet_plan["packets"]:
            trailing = packet["continuation_spacings_samples"][1:]
            if trailing:
                medians.append(sorted(trailing)[len(trailing) // 2] / 48000)
                grammar_medians.setdefault(packet["unit_grammar"], []).extend(trailing)
        assert 0.028 <= sorted(medians)[len(medians) // 2] <= 0.067
        assert len({
            round(sum(values) / len(values))
            for values in grammar_medians.values()
        }) > 1


def test_source_supported_repetition_preserves_exact_identity(seeded_results) -> None:
    index = json.loads(
        (ROOT.parent / "wave-gen-interchange/bank/frozen_assets/"
         "frozen_motif_identity_index.json").read_text()
    )
    hashes = {item["motif_id"]: item["per_motif_sha256"] for item in index["motifs"]}
    for result in seeded_results.values():
        events = result.event_plan["events"]
        assert any(
            first["motif_id"] == second["motif_id"]
            for first, second in zip(events, events[1:])
        )
        assert all(hashes[event["motif_id"]] == event["motif_hash"] for event in events)


def test_same_seed_reproduces_and_different_seeds_differ(seeded_results) -> None:
    service = PlanningService()
    request = dict(REQUEST)
    request["request_id"] = "same_seed_recheck"
    first = service.build(request)
    second = service.build(request)
    assert service.core_hashes(first) == service.core_hashes(second)
    assert seeded_results[20260623].event_plan != seeded_results[20260624].event_plan


def test_corrected_qualification_semantics_are_not_falsely_compared(tmp_path: Path) -> None:
    from wave_generator_engine.runs.storage import RunStorage

    result = PlanningService().build(REQUEST)
    run = RunStorage(tmp_path / "runs").write_latest(result)
    qualification = BaselineQualificationService().qualify(
        run, tmp_path / "reports"
    )
    assert qualification["wge4_authorized"]
    comparisons = json.loads(
        (run / "qualification/metric_comparisons.json").read_text()
    )["comparisons"]
    by_id = {item["metric_id"]: item for item in comparisons}
    assert by_id["packet_onset_schedule_spectrum"]["comparison_result"] == \
        "not_assessable"
    assert by_id["unit_grammar_distribution_baseline"]["comparison_result"] == \
        "not_assessable"
    assert by_id["event_rate_session_1"]["comparison_result"] in {
        "within_source_reference", "near_source_reference"
    }
    assert by_id["continuation_spacing_median_session_1"]["comparison_result"] == \
        "within_source_reference"
