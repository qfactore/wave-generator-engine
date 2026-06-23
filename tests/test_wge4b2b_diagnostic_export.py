import json
import shutil
import struct
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.export_contract.diagnostic import (
    DiagnosticSessionExportService,
)
from wave_generator_engine.export_contract.readback import parse_pcm16_wav
from wave_generator_engine.export_contract.service import (
    DiagnosticExportContractService,
)
from wave_generator_engine.profiles.hashing import content_hash, validate_content_hash
from wave_generator_engine.rendering.service import RenderAuditService

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/latest"


def _json(path: Path) -> dict:
    return json.loads(path.read_text())


def _write_hashed(path: Path, value: dict) -> None:
    value["content_hash"] = ""
    value["content_hash"] = content_hash(value)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _copy_run(tmp_path: Path) -> Path:
    target = tmp_path / "run"
    shutil.copytree(
        RUN, target,
        ignore=shutil.ignore_patterns("diagnostic_export", "figures", "*.png", "*.csv"),
    )
    return target


def test_committed_pack_validates_and_contains_exact_four_files() -> None:
    result = DiagnosticSessionExportService.validate(RUN)
    assert result["valid"] and result["wge4c_authorized"]
    manifest = DiagnosticSessionExportService.show(RUN)
    assert manifest["engine_version"] == "0.5.1"
    assert manifest["frame_count"] == 2_880_000
    assert manifest["event_count"] == 960
    assert manifest["packet_count"] == 149
    assert manifest["deterministic_duplicate_export"] == "passed_byte_identical"
    assert len(manifest["files"]) == 4
    assert [item["file_size_bytes"] for item in manifest["files"]] == \
        [11_520_044] * 4
    assert all(item["readback_status"] == "passed" for item in manifest["files"])


def test_committed_manifest_and_validation_schemas() -> None:
    pairs = (
        ("export_manifest.json", "diagnostic_export_pack_manifest.schema.json"),
        ("export_validation.json", "diagnostic_export_validation.schema.json"),
        ("quantization_metrics.json", "diagnostic_quantization_metrics.schema.json"),
        ("readback_validation.json", "diagnostic_pack_readback.schema.json"),
    )
    for document_name, schema_name in pairs:
        document = _json(RUN / "diagnostic_export" / document_name)
        schema = _json(ROOT / "schemas" / schema_name)
        Draft202012Validator(schema).validate(document)
        assert validate_content_hash(document)


def test_files_have_exact_contract_structure_and_mapping() -> None:
    contract = DiagnosticExportContractService().load()
    manifest = DiagnosticSessionExportService.show(RUN)
    seen = []
    for record, mapping in zip(manifest["files"], contract["branch_mappings"]):
        payload = (
            RUN / "diagnostic_export/files" / record["filename"]
        ).read_bytes()
        parsed = parse_pcm16_wav(payload, contract)
        assert payload[12:16] == b"fmt " and payload[36:40] == b"data"
        assert struct.unpack_from("<HHIIHH", payload, 20) == (
            1, 2, 48000, 192000, 4, 16
        )
        assert parsed["frame_count"] == 2_880_000
        assert record["left_logical_channel"] == mapping["left_logical_channel"]
        assert record["right_logical_channel"] == mapping["right_logical_channel"]
        seen.extend((record["left_logical_channel"], record["right_logical_channel"]))
    assert sorted(seen) == list(range(8))


def test_quantization_and_readback_are_exact_and_bounded() -> None:
    quantization = _json(RUN / "diagnostic_export/quantization_metrics.json")
    readback = _json(RUN / "diagnostic_export/readback_validation.json")
    assert quantization["global_maximum_quantization_error"] <= 1 / 65536
    assert quantization["global_mean_absolute_quantization_error"] < 1 / 65536
    assert readback["all_files_passed"]
    assert readback["exact_pcm_code_equality"]
    assert all(item["exact_pcm_code_equality"] for item in readback["files"])


def test_bus_hash_calibration_and_processing_boundaries() -> None:
    manifest = DiagnosticSessionExportService.show(RUN)
    receipt = _json(RUN / "render_audit/render_receipt.json")
    validation = _json(RUN / "diagnostic_export/export_validation.json")
    assert manifest["source_bus_hashes"] == receipt["array_hashes"]
    assert manifest["calibration_multiplier_previously_applied"] == 1.1
    assert manifest["export_multiplier"] == 1.0
    assert manifest["representation_conversion"] == \
        "native_pcm_code_units_divided_by_32768"
    assert not manifest["playback_intensity_applied"]
    assert not validation["calibration_reapplied"]
    assert not validation["normalization_applied"]
    assert not validation["limiter_applied"]
    assert validation["no_dither"]


@pytest.mark.parametrize(("relative", "field", "value", "message"), [
    ("qualification/qualification_verdict.json", "wge4_authorized", False, "Qualified"),
    ("render_audit/headroom_verdict.json", "verdict", "headroom_fail", "headroom"),
    ("render_audit/headroom_verdict.json", "wge4b_authorized", False, "headroom"),
])
def test_unauthorized_prerequisites_are_rejected(
    tmp_path: Path, relative: str, field: str, value, message: str,
) -> None:
    run = _copy_run(tmp_path)
    path = run / relative
    document = _json(path)
    document[field] = value
    _write_hashed(path, document)
    with pytest.raises(ValidationFailure, match=message):
        DiagnosticSessionExportService()._preflight(run)


def test_changed_event_plan_hash_is_rejected(tmp_path: Path) -> None:
    run = _copy_run(tmp_path)
    path = run / "sessions/session_01/event_plan.json"
    document = _json(path)
    document["events"][0]["relative_event_gain"] = 0.5
    path.write_text(json.dumps(document))
    with pytest.raises(ValidationFailure, match="hash"):
        DiagnosticSessionExportService()._preflight(run)


def test_changed_render_receipt_bus_hash_is_rejected(tmp_path: Path) -> None:
    run = _copy_run(tmp_path)
    path = run / "render_audit/render_receipt.json"
    document = _json(path)
    document["array_hashes"]["0"] = "0" * 64
    _write_hashed(path, document)
    service = DiagnosticSessionExportService()
    context = service._preflight(run)
    with pytest.raises(ValidationFailure, match="bus hashes"):
        service._render_verified(context)


def test_existing_pack_is_not_silently_overwritten() -> None:
    with pytest.raises(ValidationFailure, match="already exists"):
        DiagnosticSessionExportService().export(RUN)


def test_atomic_failure_leaves_no_partial_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _copy_run(tmp_path)
    service = DiagnosticSessionExportService()
    monkeypatch.setattr(service, "_render_verified", lambda context: object())
    monkeypatch.setattr(
        service, "_build_pack",
        lambda target, context, rendered: (_ for _ in ()).throw(
            ValidationFailure("injected export failure")
        ),
    )
    with pytest.raises(ValidationFailure, match="injected"):
        service.export(run)
    assert not (run / "diagnostic_export").exists()
    assert not list(run.glob(".diagnostic-export-*"))


def test_archive_mismatch_failure_leaves_no_partial_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _copy_run(tmp_path)
    monkeypatch.setattr(
        RenderAuditService, "render",
        lambda self, path: (_ for _ in ()).throw(
            ValidationFailure("Frozen archive hash mismatch")
        ),
    )
    with pytest.raises(ValidationFailure, match="archive"):
        DiagnosticSessionExportService().export(run)
    assert not (run / "diagnostic_export").exists()


def test_cli_show_and_validate_are_read_only() -> None:
    before = _json(RUN / "diagnostic_export/export_manifest.json")["content_hash"]
    assert DiagnosticSessionExportService.validate(RUN)["valid"]
    assert DiagnosticSessionExportService.show(RUN)["content_hash"] == before
    assert _json(RUN / "diagnostic_export/export_manifest.json")["content_hash"] == before


def test_no_packaging_or_unsupported_encoding_artifacts() -> None:
    source = (
        ROOT / "src/wave_generator_engine/export_contract/diagnostic.py"
    ).read_text().casefold()
    assert "pcm24" not in source
    assert "encrypt" not in source
    assert not list((RUN / "diagnostic_export").rglob("*playback*.json"))
    assert not list((RUN / "diagnostic_export").rglob("*upload*.json"))
