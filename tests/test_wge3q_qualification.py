import json
import shutil
from pathlib import Path

from jsonschema import Draft202012Validator

from wave_generator_engine.qualification.service import (
    BaselineQualificationService, CORE_FILES, determine_verdict,
)

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/latest"


def _copy_run(tmp_path: Path) -> Path:
    target = tmp_path / "run"
    shutil.copytree(RUN, target, ignore=shutil.ignore_patterns("qualification"))
    return target


def test_qualification_is_deterministic_and_core_plans_stay_unchanged(tmp_path: Path) -> None:
    service = BaselineQualificationService()
    first = _copy_run(tmp_path / "first")
    second = _copy_run(tmp_path / "second")
    before = service.core_hashes(first)
    one = service.qualify(first, tmp_path / "reports-one")
    two = service.qualify(second, tmp_path / "reports-two")
    assert one["verdict"] == two["verdict"] == "qualified_with_documented_caveats"
    assert service.core_hashes(first) == before
    for relative in CORE_FILES:
        assert (first / relative).read_bytes() == (second / relative).read_bytes()
    for left in sorted((first / "qualification").rglob("*.json")):
        right = second / "qualification" / left.relative_to(first / "qualification")
        assert left.read_bytes() == right.read_bytes()


def test_source_windows_remain_aggregate_only(tmp_path: Path) -> None:
    run = _copy_run(tmp_path)
    BaselineQualificationService().qualify(run, tmp_path / "reports")
    windows = json.loads((run / "qualification/source_window_manifest.json").read_text())
    assert windows["source_window_count"] == 0
    assert windows["session_boundaries_preserved"]
    assert windows["selection_method"].startswith("not_assessable")


def test_role_normalization_and_absent_calibration(tmp_path: Path) -> None:
    run = _copy_run(tmp_path)
    BaselineQualificationService().qualify(run, tmp_path / "reports")
    comparisons = json.loads(
        (run / "qualification/metric_comparisons.json").read_text()
    )["comparisons"]
    focus = next(item for item in comparisons if item["metric_id"] == "focus_role_density_ratio")
    assert focus["source_scope"] == "role_normalized"
    assert "Physical channel 2 is not treated as canonical." in focus["limitations"]
    text = json.dumps(comparisons)
    assert "calibration_applied" not in text
    assert "playback_intensity_applied" not in text


def test_aligned_committed_run_authorizes_wge4_and_schema_validates(tmp_path: Path) -> None:
    run = _copy_run(tmp_path)
    result = BaselineQualificationService().qualify(run, tmp_path / "reports")
    assert result["wge4_authorized"]
    assert not result["major_outside_metrics"]
    verdict = json.loads((run / "qualification/qualification_verdict.json").read_text())
    schema = json.loads((ROOT / "schemas/qualification_verdict.schema.json").read_text())
    Draft202012Validator(schema).validate(verdict)


def test_missing_source_metrics_are_not_assessable(tmp_path: Path) -> None:
    run = _copy_run(tmp_path)
    BaselineQualificationService().qualify(run, tmp_path / "reports")
    comparisons = json.loads(
        (run / "qualification/metric_comparisons.json").read_text()
    )["comparisons"]
    packet = next(
        item for item in comparisons
        if item["metric_id"] == "packet_interval_distribution_session_1"
    )
    assert packet["comparison_result"] == "not_assessable"
    assert packet["limitations"]


def test_qualification_outputs_validate_and_contain_no_audio(tmp_path: Path) -> None:
    run = _copy_run(tmp_path)
    BaselineQualificationService().qualify(run, tmp_path / "reports")
    assert BaselineQualificationService.validate(run)["valid"]
    manifest = json.loads((run / "qualification/qualification_manifest.json").read_text())
    schema = json.loads((ROOT / "schemas/qualification_manifest.schema.json").read_text())
    Draft202012Validator(schema).validate(manifest)
    assert not list(run.rglob("*.wav"))
    assert not (run / "audio").exists()


def test_verdict_policy_covers_all_outcomes() -> None:
    assert determine_verdict(
        tier_1_violations=[], major_outside_metrics=[],
        critical_not_assessable=[], minor_outside_metrics=[],
    ) == ("qualified_for_diagnostic_render", True)
    assert determine_verdict(
        tier_1_violations=[], major_outside_metrics=[],
        critical_not_assessable=[], minor_outside_metrics=["minor"],
    ) == ("qualified_with_documented_caveats", True)
    assert determine_verdict(
        tier_1_violations=[], major_outside_metrics=[],
        critical_not_assessable=["timing"], minor_outside_metrics=[],
    ) == ("insufficient_source_evidence", False)
    assert determine_verdict(
        tier_1_violations=[], major_outside_metrics=["timing"],
        critical_not_assessable=[], minor_outside_metrics=[],
    ) == ("not_qualified_for_render", False)
