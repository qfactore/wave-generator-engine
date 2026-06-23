import gc
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from jsonschema import Draft202012Validator

from wave_generator_engine import __version__
from wave_generator_engine.config import ENGINE_ROOT
from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.interchange.discovery import discover_interchange
from wave_generator_engine.profiles.hashing import content_hash, validate_content_hash
from wave_generator_engine.qualification.service import (
    BaselineQualificationService, CORE_FILES,
)
from wave_generator_engine.rendering.measurement import canonical_array_hash
from wave_generator_engine.rendering.service import RenderAuditService
from .quantization import PCM16_MAX_ERROR, PCM16_MAX_INPUT
from .readback import DiagnosticPcm16ReadbackValidator, parse_pcm16_wav
from .service import DiagnosticExportContractService
from .writer import DiagnosticPcm16WavWriter


OUTPUT_FILES = (
    "export_manifest.json",
    "export_validation.json",
    "export_authority_snapshot.json",
    "quantization_metrics.json",
    "readback_validation.json",
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationFailure(f"Diagnostic export input is invalid: {path.name}")
    return value


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root)
        if ".DS_Store" in relative.parts or "__pycache__" in relative.parts or \
                path.suffix == ".pyc":
            continue
        encoded = relative.as_posix().encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _hashed(value: dict[str, Any]) -> dict[str, Any]:
    value["content_hash"] = ""
    value["content_hash"] = content_hash(value)
    return value


def _validate_schema(document: dict[str, Any], schema_name: str) -> None:
    schema = _load(ENGINE_ROOT / "schemas" / schema_name)
    Draft202012Validator(schema).validate(document)


def _independent_codes(values: np.ndarray) -> np.ndarray:
    if values.dtype != np.float64 or values.ndim != 1:
        raise ValidationFailure("Export reference requires one-dimensional float64")
    if not np.all(np.isfinite(values)) or np.any(values < -1.0) or \
            np.any(values > PCM16_MAX_INPUT):
        raise ValidationFailure("Export reference contains invalid PCM16 values")
    return np.rint(values * 32768.0).astype("<i2")


def _decoded_metrics(codes: np.ndarray) -> dict[str, float | int]:
    values = codes.astype(np.float64) / 32768.0
    return {
        "sample_peak": float(np.max(np.abs(values))),
        "rms": float(np.sqrt(np.mean(values ** 2))),
        "dc_offset": float(np.mean(values)),
        "nonzero_fraction": float(np.count_nonzero(codes) / len(codes)),
        "minimum_pcm_code": int(np.min(codes)),
        "maximum_pcm_code": int(np.max(codes)),
        "zero_code_count": int(np.count_nonzero(codes == 0)),
        "nonzero_code_count": int(np.count_nonzero(codes)),
    }


class DiagnosticSessionExportService:
    def __init__(self, interchange_dir: Path | None = None) -> None:
        self.interchange_dir = interchange_dir
        self.contract_service = DiagnosticExportContractService()

    def _preflight(self, run: Path) -> dict[str, Any]:
        run = run.resolve()
        if run.is_symlink() or not run.is_dir():
            raise ValidationFailure("Diagnostic export run path is invalid")
        contract_validation = self.contract_service.validate(self.interchange_dir)
        contract = self.contract_service.load()
        qualification = _load(run / "qualification/qualification_verdict.json")
        headroom = _load(run / "render_audit/headroom_verdict.json")
        render_receipt = _load(run / "render_audit/render_receipt.json")
        writer_report = _load(ENGINE_ROOT / "reports/wge4b2a_writer_core_report.json")
        if qualification.get("wge4_authorized") is not True or \
                not BaselineQualificationService.validate(run)["valid"]:
            raise ValidationFailure("Qualified plan does not authorize diagnostic rendering")
        if headroom.get("verdict") != "headroom_pass" or \
                headroom.get("wge4b_authorized") is not True:
            raise ValidationFailure("WGE-4A headroom does not authorize export")
        if contract_validation.get("wge4b2_authorized") is not True or \
                writer_report.get("wge4b2b_authorized") is not True:
            raise ValidationFailure("WGE-4B contract or writer core is unauthorized")
        for relative in CORE_FILES:
            if not validate_content_hash(_load(run / relative)):
                raise ValidationFailure(f"Core plan hash failed: {relative}")
        core_hashes = BaselineQualificationService.core_hashes(run)
        if core_hashes != qualification.get("core_plan_hashes_after"):
            raise ValidationFailure("Qualified core plan hashes changed")
        for document in (qualification, headroom, render_receipt, contract):
            if not validate_content_hash(document):
                raise ValidationFailure("Prerequisite document hash failed")
        session = _load(run / "sessions/session_01/session_plan.json")
        request = _load(run / "request.json")
        interchange_root = discover_interchange(ENGINE_ROOT, self.interchange_dir)
        if session.get("session_id") != 1 or session.get("mode") != "baseline":
            raise ValidationFailure("Only contracted Session 1 Baseline export is supported")
        if session["sample_rate_hz"] != contract["sample_rate_hz"] or \
                session["duration_samples"] != contract["duration_policy"][
                    "current_qualified_frame_count"
                ]:
            raise ValidationFailure("Session duration or sample rate differs from contract")
        return {
            "run": run,
            "contract": contract,
            "qualification": qualification,
            "headroom": headroom,
            "render_receipt": render_receipt,
            "session": session,
            "request": request,
            "core_hashes": core_hashes,
            "interchange_root": interchange_root,
            "interchange_tree_hash": _tree_hash(interchange_root),
        }

    def _render_verified(self, context: dict[str, Any]):
        result = RenderAuditService(self.interchange_dir).render(context["run"])
        receipt = result.documents["render_receipt.json"]
        if receipt["array_hashes"] != context["render_receipt"]["array_hashes"]:
            raise ValidationFailure("Rerendered WGE-4A bus hashes differ")
        for index, bus in enumerate(result.calibrated_buses):
            if canonical_array_hash(index, bus) != receipt["array_hashes"][str(index)]:
                raise ValidationFailure("Rerendered bus canonical hash failed")
        if receipt["events_rendered"] != context["session"]["event_count"] or \
                receipt["calibration_multiplier"] != 1.1 or \
                receipt["playback_intensity_applied"]:
            raise ValidationFailure("Rerender processing semantics changed")
        return result

    def _build_pack(
        self, target: Path, context: dict[str, Any], render_result
    ) -> dict[str, Any]:
        target.mkdir(parents=True, exist_ok=False)
        files_dir = target / "files"
        files_dir.mkdir()
        writer = DiagnosticPcm16WavWriter()
        reader = DiagnosticPcm16ReadbackValidator()
        contract = context["contract"]
        file_records = []
        quantization_rows = []
        readback_rows = []
        calibrated_metrics = render_result.documents["per_channel_metrics.json"][
            "calibrated"
        ]
        full_scale_denominator = render_result.documents[
            "per_channel_metrics.json"
        ]["full_scale_denominator"]
        if full_scale_denominator != 32768.0:
            raise ValidationFailure("WGE-4A full-scale representation changed")
        for mapping in contract["branch_mappings"]:
            branch = mapping["source_order"]
            left_index = mapping["left_logical_channel"]
            right_index = mapping["right_logical_channel"]
            left = (
                render_result.calibrated_buses[left_index]
                / full_scale_denominator
            )
            right = (
                render_result.calibrated_buses[right_index]
                / full_scale_denominator
            )
            left_codes = _independent_codes(left)
            right_codes = _independent_codes(right)
            expected_interleaved = np.column_stack((left_codes, right_codes))
            reference_bytes = expected_interleaved.astype("<i2", copy=False).tobytes()
            filename = writer.branch_filename(branch)
            written = writer.write_synthetic(files_dir, filename, left, right)
            payload = written.path.read_bytes()
            parsed = parse_pcm16_wav(payload, contract)
            if parsed["frame_count"] != context["session"]["duration_samples"] or \
                    written.data_byte_count != context["session"]["duration_samples"] * 4 or \
                    written.path.stat().st_size != written.data_byte_count + 44:
                raise ValidationFailure("Exported WAV structural size mismatch")
            if parsed["data"] != reference_bytes:
                raise ValidationFailure("Writer data differs from independent PCM reference")
            readback = reader.validate_bytes(payload, left, right)
            decoded = parsed["codes"].astype(np.float64) / 32768.0
            expected = np.column_stack((left, right))
            errors = np.abs(decoded - expected)
            if float(np.max(errors)) > PCM16_MAX_ERROR:
                raise ValidationFailure("Quantization error exceeds contract")
            channel_rows = []
            for position, (channel_index, codes, source) in enumerate((
                (left_index, left_codes, left),
                (right_index, right_codes, right),
            )):
                metrics = _decoded_metrics(codes)
                source_metrics = calibrated_metrics[channel_index]
                metrics.update({
                    "logical_channel": channel_index,
                    "side": "left" if position == 0 else "right",
                    "pcm_stream_sha256": hashlib.sha256(
                        codes.astype("<i2", copy=False).tobytes()
                    ).hexdigest(),
                    "peak_difference": metrics["sample_peak"]
                        - source_metrics["sample_peak_linear"],
                    "rms_difference": metrics["rms"] - source_metrics["rms"],
                    "dc_offset_difference": metrics["dc_offset"]
                        - source_metrics["dc_offset"],
                    "maximum_quantization_error": float(np.max(
                        np.abs(codes.astype(np.float64) / 32768.0 - source)
                    )),
                    "mean_absolute_quantization_error": float(np.mean(
                        np.abs(codes.astype(np.float64) / 32768.0 - source)
                    )),
                })
                channel_rows.append(metrics)
            record = {
                "branch_number": branch,
                "left_logical_channel": left_index,
                "right_logical_channel": right_index,
                "filename": filename,
                "file_size_bytes": written.path.stat().st_size,
                "sample_rate_hz": contract["sample_rate_hz"],
                "frame_count": written.frame_count,
                "encoding": "signed_pcm16",
                "bit_depth": 16,
                "wav_sha256": written.wav_sha256,
                "data_chunk_sha256": written.data_chunk_sha256,
                "left_pcm_sha256": channel_rows[0]["pcm_stream_sha256"],
                "right_pcm_sha256": channel_rows[1]["pcm_stream_sha256"],
                "interleaved_pcm_sha256": hashlib.sha256(reference_bytes).hexdigest(),
                "readback_status": "passed",
                "maximum_quantization_error": float(np.max(errors)),
            }
            file_records.append(record)
            quantization_rows.append({
                "branch_number": branch,
                "left_logical_channel": left_index,
                "right_logical_channel": right_index,
                "frame_count": written.frame_count,
                "channels": channel_rows,
                "maximum_quantization_error": float(np.max(errors)),
                "mean_absolute_quantization_error": float(np.mean(errors)),
                "reference_pcm_sha256": hashlib.sha256(reference_bytes).hexdigest(),
                "interleaved_data_sha256": written.data_chunk_sha256,
            })
            readback_rows.append({
                "branch_number": branch,
                "filename": filename,
                **{key: value for key, value in readback.items()
                   if key != "content_hash"},
                "exact_pcm_code_equality": True,
                "left_right_order_verified": True,
            })
        pack_basis = {
            "contract_hash": contract["content_hash"],
            "render_receipt_hash": context["render_receipt"]["content_hash"],
            "source_bus_hashes": context["render_receipt"]["array_hashes"],
            "branch_mappings": contract["branch_mappings"],
            "file_names": [item["filename"] for item in file_records],
            "wav_hashes": [item["wav_sha256"] for item in file_records],
            "data_hashes": [item["data_chunk_sha256"] for item in file_records],
            "frame_count": context["session"]["duration_samples"],
            "sample_rate_hz": context["session"]["sample_rate_hz"],
            "encoding": "signed_pcm16",
            "content_hash": "",
        }
        pack_hash = content_hash(pack_basis)
        quantization = _hashed({
            "schema_version": "wge.diagnostic_quantization_metrics.v1",
            "maximum_allowed_error": PCM16_MAX_ERROR,
            "branches": quantization_rows,
            "global_maximum_quantization_error": max(
                item["maximum_quantization_error"] for item in quantization_rows
            ),
            "global_mean_absolute_quantization_error": float(np.mean([
                item["mean_absolute_quantization_error"]
                for item in quantization_rows
            ])),
            "content_hash": "",
        })
        readback_document = _hashed({
            "schema_version": "wge.diagnostic_pack_readback.v1",
            "all_files_passed": True,
            "exact_pcm_code_equality": True,
            "files": readback_rows,
            "content_hash": "",
        })
        authority = _hashed({
            "schema_version": "wge.diagnostic_export_authority.v1",
            "core_plan_hashes": context["core_hashes"],
            "qualification_verdict_hash": context["qualification"]["content_hash"],
            "render_receipt_hash": context["render_receipt"]["content_hash"],
            "contract_hash": contract["content_hash"],
            "archive_hash": render_result.documents["render_receipt.json"]["archive_hash"],
            "interchange_tree_hash": context["interchange_tree_hash"],
            "wge4a_authority_snapshot_hash": render_result.documents[
                "authority_snapshot.json"
            ]["content_hash"],
            "content_hash": "",
        })
        validation = _hashed({
            "schema_version": "wge.diagnostic_export_validation.v1",
            "valid": True,
            "file_count": len(file_records),
            "all_bus_hashes_matched": True,
            "all_readback_codes_matched": True,
            "all_quantization_errors_within_bound": True,
            "no_clipping_or_saturation": True,
            "no_dither": True,
            "calibration_reapplied": False,
            "representation_conversion":
                "native_pcm_code_units_divided_by_32768",
            "playback_intensity_applied": False,
            "normalization_applied": False,
            "limiter_applied": False,
            "pack_hash": pack_hash,
            "wge4c_authorized": True,
            "content_hash": "",
        })
        manifest = _hashed({
            "schema_version": "wge.diagnostic_export_manifest.v2",
            "manifest_id": "x_alpha_session_01_baseline_diagnostic_export_v1",
            "manifest_version": "1.0.0",
            "diagnostic_only": True,
            "engine_version": __version__,
            "source_profile_id": "x_alpha_standard_v1",
            "session_id": context["session"]["session_id"],
            "mode": context["session"]["mode"],
            "duration_seconds": context["session"]["duration_seconds"],
            "sample_rate_hz": context["session"]["sample_rate_hz"],
            "frame_count": context["session"]["duration_samples"],
            "event_count": context["session"]["event_count"],
            "packet_count": context["session"]["packet_count"],
            "focus_role_target": context["session"]["focus_role_target"],
            "root_seed": context["request"]["root_seed"],
            "qualification_verdict": context["qualification"]["verdict"],
            "qualification_hash": context["qualification"]["content_hash"],
            "render_receipt_hash": context["render_receipt"]["content_hash"],
            "source_bus_hashes": context["render_receipt"]["array_hashes"],
            "export_contract_id": contract["contract_id"],
            "export_contract_hash": contract["content_hash"],
            "calibration_already_applied": True,
            "calibration_multiplier_previously_applied": 1.1,
            "export_multiplier": 1.0,
            "representation_conversion":
                "native_pcm_code_units_divided_by_32768",
            "playback_intensity_applied": False,
            "dither": "none",
            "branch_mappings": contract["branch_mappings"],
            "files": file_records,
            "quantization_metrics_hash": quantization["content_hash"],
            "readback_validation_hash": readback_document["content_hash"],
            "authority_snapshot_hash": authority["content_hash"],
            "pack_hash": pack_hash,
            "deterministic_duplicate_export": "passed_byte_identical",
            "wge4c_authorized": True,
            "content_hash": "",
        })
        _write(target / "export_manifest.json", manifest)
        _write(target / "export_validation.json", validation)
        _write(target / "export_authority_snapshot.json", authority)
        _write(target / "quantization_metrics.json", quantization)
        _write(target / "readback_validation.json", readback_document)
        return {
            "manifest": manifest,
            "file_records": file_records,
            "pack_hash": pack_hash,
        }

    @staticmethod
    def _compare_packs(first: Path, second: Path) -> None:
        first_files = sorted(
            path.relative_to(first) for path in first.rglob("*") if path.is_file()
        )
        second_files = sorted(
            path.relative_to(second) for path in second.rglob("*") if path.is_file()
        )
        if first_files != second_files:
            raise ValidationFailure("Duplicate export file inventory differs")
        for relative in first_files:
            if (first / relative).read_bytes() != (second / relative).read_bytes():
                raise ValidationFailure(f"Duplicate export differs: {relative}")

    def export(self, run: Path, replace: bool = False) -> dict[str, Any]:
        finder_metadata = run.resolve() / "diagnostics/.DS_Store"
        if finder_metadata.is_file():
            finder_metadata.unlink()
        context = self._preflight(run)
        run = context["run"]
        target = run / "diagnostic_export"
        if target.exists() and not replace:
            raise ValidationFailure("Diagnostic export already exists")
        staging = Path(tempfile.mkdtemp(prefix=".diagnostic-export-", dir=run))
        duplicate_root = Path(tempfile.mkdtemp(prefix="wge-duplicate-export-"))
        duplicate = duplicate_root / "diagnostic_export"
        backup = run / ".diagnostic-export-backup"
        try:
            first_render = self._render_verified(context)
            first = self._build_pack(staging / "pack", context, first_render)
            del first_render
            gc.collect()
            second_render = self._render_verified(context)
            self._build_pack(duplicate, context, second_render)
            del second_render
            gc.collect()
            self._compare_packs(staging / "pack", duplicate)
            if _tree_hash(context["interchange_root"]) != \
                    context["interchange_tree_hash"]:
                raise ValidationFailure("Interchange changed during diagnostic export")
            _validate_schema(
                first["manifest"], "diagnostic_export_pack_manifest.schema.json"
            )
            _validate_schema(
                _load(staging / "pack/export_validation.json"),
                "diagnostic_export_validation.schema.json",
            )
            _validate_schema(
                _load(staging / "pack/quantization_metrics.json"),
                "diagnostic_quantization_metrics.schema.json",
            )
            _validate_schema(
                _load(staging / "pack/readback_validation.json"),
                "diagnostic_pack_readback.schema.json",
            )
            if backup.exists():
                shutil.rmtree(backup)
            if target.exists():
                os.replace(target, backup)
            os.replace(staging / "pack", target)
            if backup.exists():
                shutil.rmtree(backup)
            return first["manifest"]
        except Exception:
            if backup.exists() and not target.exists():
                os.replace(backup, target)
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            shutil.rmtree(duplicate_root, ignore_errors=True)

    @staticmethod
    def validate(run: Path) -> dict[str, Any]:
        target = run.resolve() / "diagnostic_export"
        manifest = _load(target / "export_manifest.json")
        validation = _load(target / "export_validation.json")
        quantization = _load(target / "quantization_metrics.json")
        readback_document = _load(target / "readback_validation.json")
        authority = _load(target / "export_authority_snapshot.json")
        for document, schema in (
            (manifest, "diagnostic_export_pack_manifest.schema.json"),
            (validation, "diagnostic_export_validation.schema.json"),
            (quantization, "diagnostic_quantization_metrics.schema.json"),
            (readback_document, "diagnostic_pack_readback.schema.json"),
        ):
            if not validate_content_hash(document):
                raise ValidationFailure("Diagnostic export metadata hash failed")
            _validate_schema(document, schema)
        if not validate_content_hash(authority):
            raise ValidationFailure("Diagnostic export authority hash failed")
        if not validation.get("valid") or not validation.get("wge4c_authorized"):
            raise ValidationFailure("Diagnostic export validation failed")
        contract = DiagnosticExportContractService().load()
        files = manifest.get("files", [])
        if len(files) != 4:
            raise ValidationFailure("Diagnostic export does not contain four files")
        reader = DiagnosticPcm16ReadbackValidator()
        for record, mapping in zip(files, contract["branch_mappings"]):
            path = target / "files" / record["filename"]
            if not path.is_file() or path.stat().st_size != record["file_size_bytes"]:
                raise ValidationFailure("Diagnostic WAV is missing or changed")
            parsed = parse_pcm16_wav(path.read_bytes(), contract)
            if parsed["wav_sha256"] != record["wav_sha256"] or \
                    parsed["data_chunk_sha256"] != record["data_chunk_sha256"] or \
                    parsed["frame_count"] != manifest["frame_count"]:
                raise ValidationFailure("Diagnostic WAV readback hash failed")
            if mapping["left_logical_channel"] != record["left_logical_channel"] or \
                    mapping["right_logical_channel"] != record["right_logical_channel"]:
                raise ValidationFailure("Diagnostic WAV mapping changed")
            if hashlib.sha256(
                parsed["codes"][:, 0].astype("<i2", copy=False).tobytes()
            ).hexdigest() != record["left_pcm_sha256"] or hashlib.sha256(
                parsed["codes"][:, 1].astype("<i2", copy=False).tobytes()
            ).hexdigest() != record["right_pcm_sha256"]:
                raise ValidationFailure("Diagnostic WAV PCM stream hash failed")
        pack_basis = {
            "contract_hash": manifest["export_contract_hash"],
            "render_receipt_hash": manifest["render_receipt_hash"],
            "source_bus_hashes": manifest["source_bus_hashes"],
            "branch_mappings": manifest["branch_mappings"],
            "file_names": [item["filename"] for item in files],
            "wav_hashes": [item["wav_sha256"] for item in files],
            "data_hashes": [item["data_chunk_sha256"] for item in files],
            "frame_count": manifest["frame_count"],
            "sample_rate_hz": manifest["sample_rate_hz"],
            "encoding": "signed_pcm16",
            "content_hash": "",
        }
        if content_hash(pack_basis) != manifest["pack_hash"] or \
                manifest["pack_hash"] != validation["pack_hash"]:
            raise ValidationFailure("Diagnostic export pack hash failed")
        return {
            "valid": True,
            "file_count": 4,
            "pack_hash": manifest["pack_hash"],
            "wge4c_authorized": True,
        }

    @staticmethod
    def show(run: Path) -> dict[str, Any]:
        return _load(run.resolve() / "diagnostic_export/export_manifest.json")
