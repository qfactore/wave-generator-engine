import inspect
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.motifs.loader import FrozenMotifBank
from wave_generator_engine.rendering.measurement import (
    canonical_array_hash, channel_metrics, estimate_true_peak,
)
from wave_generator_engine.rendering.service import (
    RenderAuditService, accumulate_event, evaluate_headroom,
)
from wave_generator_engine.qualification.service import BaselineQualificationService

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/latest"


def test_exact_float64_placement_overlap_and_channel_independence() -> None:
    buses = [np.zeros(8, dtype=np.float64) for _ in range(2)]
    occupancy = [np.zeros(8, dtype=np.uint16) for _ in range(2)]
    accumulate_event(buses, occupancy, 0, 2, np.array([1.0, 2.0], dtype=np.float64))
    accumulate_event(buses, occupancy, 0, 3, np.array([3.0, 4.0], dtype=np.float64))
    accumulate_event(buses, occupancy, 1, 3, np.array([9.0], dtype=np.float64))
    assert buses[0].tolist() == [0, 0, 1, 5, 4, 0, 0, 0]
    assert buses[1].tolist() == [0, 0, 0, 9, 0, 0, 0, 0]
    assert occupancy[0].tolist() == [0, 0, 1, 2, 1, 0, 0, 0]
    with pytest.raises(ValidationFailure, match="bounds"):
        accumulate_event(
            buses, occupancy, 0, 7, np.array([1.0, 2.0], dtype=np.float64)
        )


def test_sample_rms_dc_overlap_and_nonfinite_fixtures() -> None:
    values = np.array([0.0, 16384.0, -16384.0, 0.0], dtype=np.float64)
    occupancy = np.array([0, 1, 2, 0], dtype=np.uint16)
    metrics = channel_metrics(0, values, occupancy, 2)
    assert metrics["sample_peak_linear"] == 0.5
    assert metrics["rms"] == pytest.approx(np.sqrt(0.125))
    assert metrics["dc_offset"] == 0.0
    assert metrics["overlap_sample_count"] == 1
    assert metrics["maximum_same_channel_concurrency"] == 2
    bad = values.copy()
    bad[0] = np.nan
    assert channel_metrics(0, bad, occupancy, 2)["non_finite_sample_count"] == 1


def test_headroom_pass_and_fail_fixtures() -> None:
    passing = [{
        "non_finite_sample_count": 0,
        "clipped_full_scale_sample_count": 0,
        "estimated_true_peak_linear": 0.5,
    }]
    assert evaluate_headroom(passing, -3.0, 1, 1)
    failing = [dict(passing[0], estimated_true_peak_linear=0.9)]
    assert not evaluate_headroom(failing, -3.0, 1, 1)
    assert not evaluate_headroom(passing, -3.0, 0, 1)


def test_authoritative_true_peak_and_boundary_fixtures_are_deterministic() -> None:
    impulse = np.zeros(33, dtype=np.float64)
    impulse[0] = 0.5
    assert estimate_true_peak(impulse) == pytest.approx(0.5)
    fixture = np.array([0.0, 0.9, -0.9, 0.0], dtype=np.float64)
    first = estimate_true_peak(fixture)
    assert first == pytest.approx(0.97317937542744)
    assert estimate_true_peak(fixture) == first


def test_canonical_array_hash_binds_channel_dtype_shape_and_bytes() -> None:
    values = np.array([1.0, 2.0], dtype=np.float64)
    assert canonical_array_hash(0, values) == canonical_array_hash(0, values.copy())
    assert canonical_array_hash(0, values) != canonical_array_hash(1, values)
    changed = values.copy()
    changed[1] = 3.0
    assert canonical_array_hash(0, values) != canonical_array_hash(0, changed)


@pytest.fixture(scope="module")
def render_result():
    return RenderAuditService().render(RUN)


def test_qualified_run_renders_exactly_once_to_eight_ephemeral_buses(render_result) -> None:
    receipt = render_result.documents["render_receipt.json"]
    trace = render_result.documents["event_render_trace.json"]
    assert receipt["events_planned"] == receipt["events_rendered"] == 960
    assert trace["event_count"] == 960
    assert len(render_result.calibrated_buses) == 8
    assert all(item.dtype == np.float64 and item.shape == (2_880_000,)
               for item in render_result.calibrated_buses)
    assert all(not item.flags.writeable for item in render_result.calibrated_buses)
    assert all(item["exact_identity_verified"] and item["rendered_once"]
               for item in trace["events"])
    assert receipt["calibration_multiplier"] == 1.1
    assert receipt["playback_intensity_applied"] is False
    assert receipt["normalization_applied"] is False
    assert receipt["limiter_applied"] is False
    for before, after in zip(
        render_result.uncalibrated_buses, render_result.calibrated_buses
    ):
        assert np.allclose(after, before * 1.1, rtol=0.0, atol=2e-12)


def test_render_headroom_identity_and_determinism(render_result) -> None:
    second = RenderAuditService().render(RUN)
    assert render_result.documents == second.documents
    assert render_result.documents["render_receipt.json"]["array_hashes"] == \
        second.documents["render_receipt.json"]["array_hashes"]
    verdict = render_result.documents["headroom_verdict.json"]
    assert verdict["verdict"] == "headroom_pass"
    assert verdict["wge4b_authorized"]
    assert verdict["global_maximum_true_peak_dbfs"] <= -3.0
    bank = FrozenMotifBank.load()
    assert bank.pre_access_hash == bank.post_access_hash
    assert all(not item.samples.flags.writeable for item in bank.records())


def test_independent_workspace_audits_and_core_plan_hashes_match(tmp_path: Path) -> None:
    service = RenderAuditService()
    runs = []
    for name in ("first", "second"):
        target = tmp_path / name
        shutil.copytree(RUN, target, ignore=shutil.ignore_patterns("render_audit"))
        before = BaselineQualificationService.core_hashes(target)
        service.audit(target)
        assert BaselineQualificationService.core_hashes(target) == before
        runs.append(target)
    for left in sorted((runs[0] / "render_audit").rglob("*.json")):
        right = runs[1] / "render_audit" / left.relative_to(runs[0] / "render_audit")
        assert left.read_bytes() == right.read_bytes()


def test_modified_or_unauthorized_run_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "modified"
    shutil.copytree(RUN, target, ignore=shutil.ignore_patterns("render_audit"))
    event_path = target / "sessions/session_01/event_plan.json"
    event_plan = json.loads(event_path.read_text())
    event_plan["events"][0]["relative_event_gain"] = 0.5
    event_path.write_text(json.dumps(event_plan))
    with pytest.raises(ValidationFailure, match="hash|changed"):
        RenderAuditService().render(target)


def test_render_documents_validate_against_schemas(render_result) -> None:
    pairs = {
        "render_audit_manifest.json": "render_audit_manifest.schema.json",
        "render_receipt.json": "render_receipt.schema.json",
        "event_render_trace.json": "event_render_trace.schema.json",
        "per_channel_metrics.json": "channel_render_metrics.schema.json",
        "overlap_metrics.json": "overlap_metrics.schema.json",
        "true_peak_method.json": "true_peak_method.schema.json",
        "headroom_verdict.json": "headroom_verdict.schema.json",
    }
    for document_name, schema_name in pairs.items():
        schema = json.loads((ROOT / "schemas" / schema_name).read_text())
        Draft202012Validator(schema).validate(render_result.documents[document_name])


def test_renderer_has_no_random_transform_export_or_audio_path() -> None:
    source = inspect.getsource(RenderAuditService)
    forbidden = ("random.", "normalize(", "resample(", "wave.open", "soundfile")
    assert not any(item in source.casefold() for item in forbidden)
    assert {
        path.relative_to(ROOT) for path in (ROOT / "runs").rglob("*.wav")
    } == {
        Path(f"runs/latest/diagnostic_export/files/"
             f"x_alpha_session_01_baseline_branch_{index:02d}.wav")
        for index in range(1, 5)
    }
    for root in (ROOT / "runs", ROOT / "reports"):
        assert not list(root.rglob("*.npy"))
        assert not list(root.rglob("*.npz"))
