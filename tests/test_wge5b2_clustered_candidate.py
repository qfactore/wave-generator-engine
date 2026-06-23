import hashlib
import inspect
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.planning.service import PlanningService
from wave_generator_engine.profiles.hashing import validate_content_hash
from wave_generator_engine.qualification.clustered import (
    CANDIDATE_ID,
    CONTENT_SIGNATURE,
    ClusteredCandidateQualificationService,
    _content_signature,
    _meso_comparisons,
    _tree_hash,
    clustered_metrics,
)
from wave_generator_engine.meso.policy import load_meso_policy

ROOT = Path(__file__).resolve().parents[1]
APPROVED = ROOT / "runs/latest"
REQUEST = json.loads(
    (ROOT / "examples/run_requests/x_alpha_session1_diagnostic_60s.json").read_text()
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def primary():
    return PlanningService().build(REQUEST)


@pytest.fixture(scope="module")
def generated_candidate(tmp_path_factory):
    root = tmp_path_factory.mktemp("wge5b2")
    target = root / CANDIDATE_ID
    reports = root / "reports"
    service = ClusteredCandidateQualificationService(
        approved_root=APPROVED, candidate_root=target
    )
    before = _tree_hash(APPROVED)
    report = service.generate(reports)
    return service, target, reports, report, before


def test_gap_semantics_are_separate_and_source_equivalence_is_explicit(primary) -> None:
    metrics = clustered_metrics(primary)
    assert metrics["phrase_boundary_packet_gap_seconds"]["median"] == \
        pytest.approx(1.8118854166666667)
    assert metrics["background_span_seconds"]["median"] != \
        metrics["phrase_boundary_packet_gap_seconds"]["median"]
    assert metrics["empty_activity_gap_seconds"]["count"] > \
        metrics["phrase_boundary_packet_gap_seconds"]["count"]
    comparisons = _meso_comparisons(
        metrics, load_meso_policy("direct_session_1").document
    )
    by_id = {item["metric_id"]: item for item in comparisons}
    assert by_id["phrase_boundary_packet_gap"]["comparison_result"] == \
        "near_source_reference"
    assert by_id["background_span_duration"]["comparison_result"] == \
        "not_assessable"
    assert by_id["empty_activity_gap"]["comparison_result"] == "not_assessable"
    assert by_id["phrase_recurrence"]["comparison_result"] == \
        "within_source_reference"
    assert by_id["interval_serial_dependence"]["comparison_result"] == \
        "near_source_reference"
    assert by_id["local_interval_variability"]["comparison_result"] == \
        "within_source_reference"


def test_primary_content_signature_matches_approved(primary) -> None:
    approved_packet = _json(APPROVED / "sessions/session_01/packet_plan.json")
    approved_event = _json(APPROVED / "sessions/session_01/event_plan.json")
    assert _content_signature(approved_packet, approved_event) == CONTENT_SIGNATURE
    assert _content_signature(primary.packet_plan, primary.event_plan) == \
        CONTENT_SIGNATURE
    assert len(primary.packet_plan["packets"]) == 149
    assert len(primary.event_plan["events"]) == 960


def test_candidate_is_promoted_separately_and_contains_required_artifacts(
    generated_candidate,
) -> None:
    service, target, _, report, _ = generated_candidate
    assert target.is_dir()
    assert target != APPROVED
    assert ClusteredCandidateQualificationService.validate(target)["valid"]
    for relative in (
        "authority_snapshot.json",
        "planning_profile_snapshot.json",
        "meso_policy_snapshot.json",
        "run_manifest.json",
        "session_pack_plan.json",
        "sessions/session_01/session_plan.json",
        "sessions/session_01/packet_plan.json",
        "sessions/session_01/event_plan.json",
        "sessions/session_01/events.csv",
        "qualification/qualification_manifest.json",
        "qualification/qualification_verdict.json",
        "qualification/generated_plan_metrics.json",
        "diagnostics/diagnostic_manifest.json",
    ):
        assert (target / relative).is_file()
    assert report["candidate_path"].endswith(CANDIDATE_ID)
    assert service.target == target


def test_candidate_verdict_and_manifests_validate(generated_candidate) -> None:
    _, target, reports, report, _ = generated_candidate
    verdict = _json(target / "qualification/qualification_verdict.json")
    manifest = _json(target / "run_manifest.json")
    Draft202012Validator(_json(
        ROOT / "schemas/clustered_qualification_verdict.schema.json"
    )).validate(verdict)
    Draft202012Validator(_json(
        ROOT / "schemas/clustered_candidate_manifest.schema.json"
    )).validate(manifest)
    assert validate_content_hash(verdict)
    assert validate_content_hash(manifest)
    assert verdict["verdict"] == "qualified_with_documented_caveats"
    assert verdict["wge5c_clustered_render_authorized"]
    assert report["wge5c_clustered_render_authorized"]
    assert (reports / "WGE5B2_CLUSTERED_SESSION1_QUALIFICATION.md").is_file()


def test_existing_source_qualification_and_non_meso_guardrails_pass(
    generated_candidate,
) -> None:
    _, target, _, _, _ = generated_candidate
    verdict = _json(target / "qualification/qualification_verdict.json")
    validation = _json(target / "sessions/session_01/validation_report.json")
    assert verdict["existing_source_qualification"]["authorized"]
    assert not verdict["existing_source_qualification"]["major_outside_metrics"]
    assert validation["counts"]["packets"] == 149
    assert validation["counts"]["events"] == 960
    assert validation["counts"]["pulse_pattern_prevalence"] >= 0.95
    assert validation["counts"]["unique_motifs"] >= 50
    assert validation["counts"]["maximum_concurrency"] <= 4


def test_holdouts_and_primary_determinism_pass(generated_candidate) -> None:
    _, target, _, report, _ = generated_candidate
    verdict = _json(target / "qualification/qualification_verdict.json")
    assert verdict["determinism"]["independent_reruns_match"]
    assert report["determinism"]["qualification_metrics_match"]
    assert all(
        item["valid"] and item["deterministic_rerun"]
        for item in verdict["holdout_qualification"]
    )
    assert len({
        item["packet_plan_hash"] for item in verdict["holdout_qualification"]
    }) == 2


def test_candidate_has_diagnostics_but_no_audio_render_or_export(
    generated_candidate,
) -> None:
    _, target, _, _, _ = generated_candidate
    figures = list((target / "qualification/figures").glob("*.png"))
    assert len(figures) >= 8
    assert all(path.stat().st_size > 1000 for path in figures)
    assert not list(target.rglob("*.wav"))
    assert not (target / "render_audit").exists()
    assert not (target / "diagnostic_export").exists()
    assert not list(target.rglob("*playback*.json"))
    assert not list(target.rglob("*upload*.json"))


def test_approved_run_is_byte_identical_after_generation(generated_candidate) -> None:
    _, _, _, _, before = generated_candidate
    assert _tree_hash(APPROVED) == before
    export = _json(APPROVED / "diagnostic_export/export_manifest.json")
    assert export["pack_hash"] == \
        "67209fbe2e18fb070647b1f0d94e533bace77489155d900cd2e7211b57bd6d9d"


def test_failed_generation_leaves_no_partial_candidate(tmp_path: Path) -> None:
    class FailingService(ClusteredCandidateQualificationService):
        def _stage(self, target, result, holdouts, approved_metrics):
            super()._stage(target, result, holdouts, approved_metrics)
            raise ValidationFailure("synthetic qualification failure")

    target = tmp_path / CANDIDATE_ID
    service = FailingService(approved_root=APPROVED, candidate_root=target)
    with pytest.raises(ValidationFailure, match="synthetic qualification failure"):
        service.generate(tmp_path / "reports")
    assert not target.exists()
    assert not list(tmp_path.glob(f".{CANDIDATE_ID}-*"))


def test_qualification_uses_no_waveform_source_tuple_carrier_or_other_sessions() -> None:
    source = inspect.getsource(ClusteredCandidateQualificationService)
    module = inspect.getsource(clustered_metrics)
    assert "FrozenMotifBank" not in source + module
    assert "np.load" not in source + module
    assert "gain_event_table" not in source + module
    assert "carrier_frequency" not in source + module
    assert "session_id == 1" not in source + module


def test_official_candidate_and_report_are_valid_after_promotion() -> None:
    candidate = ROOT / "runs/candidates" / CANDIDATE_ID
    report = _json(ROOT / "reports/wge5b2_clustered_session1_qualification.json")
    assert ClusteredCandidateQualificationService.validate(candidate)["valid"]
    assert validate_content_hash(report)
    assert report["test_results"] == {
        "complete_test_count": 375,
        "status": "passed",
    }
    assert report["wge5c_clustered_render_authorized"]
