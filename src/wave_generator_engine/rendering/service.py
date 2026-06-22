import hashlib
import json
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/wge-matplotlib-cache")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/wge-cache")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from wave_generator_engine.calibration.policy import load_calibration_policy
from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.motifs.identity import ExactIdentityAccess
from wave_generator_engine.motifs.loader import FrozenMotifBank
from wave_generator_engine.profiles.hashing import content_hash, validate_content_hash
from wave_generator_engine.qualification.authority import QualificationAuthority
from wave_generator_engine.qualification.service import (
    BaselineQualificationService, CORE_FILES,
)
from .measurement import (
    PCM16_FULL_SCALE, canonical_array_hash, channel_metrics, dbfs,
    true_peak_method_record,
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationFailure(f"Render input is not an object: {path.name}")
    return value


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hashed(document: dict[str, Any]) -> dict[str, Any]:
    document["content_hash"] = ""
    document["content_hash"] = content_hash(document)
    return document


def accumulate_event(
    buses: list[np.ndarray], occupancy: list[np.ndarray], channel: int,
    onset: int, samples: np.ndarray,
) -> None:
    if samples.dtype != np.float64:
        raise ValidationFailure("Render accumulation requires float64 samples")
    end = onset + len(samples)
    if channel not in range(len(buses)) or onset < 0 or end > len(buses[channel]):
        raise ValidationFailure("Event exceeds render bounds")
    buses[channel][onset:end] += samples
    occupancy[channel][onset:end] += 1


def evaluate_headroom(
    metrics: list[dict[str, Any]], ceiling_dbfs: float,
    events_rendered: int, events_planned: int,
) -> bool:
    ceiling_linear = float(10 ** (ceiling_dbfs / 20))
    return (
        all(item["non_finite_sample_count"] == 0 for item in metrics)
        and all(item["clipped_full_scale_sample_count"] == 0 for item in metrics)
        and max(item["estimated_true_peak_linear"] for item in metrics) <= ceiling_linear
        and events_rendered == events_planned
    )


@dataclass
class RenderAuditResult:
    uncalibrated_buses: tuple[np.ndarray, ...]
    calibrated_buses: tuple[np.ndarray, ...]
    occupancy: tuple[np.ndarray, ...]
    documents: dict[str, Any]


class RenderAuditService:
    def __init__(self, interchange_dir: Path | None = None) -> None:
        self.bank = FrozenMotifBank.load(interchange_dir)
        self.exact = ExactIdentityAccess(self.bank)
        self.calibration = load_calibration_policy(interchange_dir)
        self.references = QualificationAuthority(interchange_dir)

    @staticmethod
    def _validate_run(run: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        qualification = _load(run / "qualification/qualification_verdict.json")
        if qualification.get("wge4_authorized") is not True or qualification.get(
            "verdict"
        ) not in {"qualified_for_diagnostic_render", "qualified_with_documented_caveats"}:
            raise ValidationFailure("Render audit requires a qualified authorized run")
        if not BaselineQualificationService.validate(run)["valid"]:
            raise ValidationFailure("Qualification validation failed")
        current = BaselineQualificationService.core_hashes(run)
        if current != qualification.get("core_plan_hashes_after"):
            raise ValidationFailure("Qualified core-plan hashes changed")
        for relative in CORE_FILES:
            if not validate_content_hash(_load(run / relative)):
                raise ValidationFailure(f"Core plan content hash failed: {relative}")
        return qualification, current

    def render(self, run: Path) -> RenderAuditResult:
        run = run.resolve()
        qualification, core_before = self._validate_run(run)
        session = _load(run / "sessions/session_01/session_plan.json")
        event_plan = _load(run / "sessions/session_01/event_plan.json")
        validation = _load(run / "sessions/session_01/validation_report.json")
        if session.get("mode") != "baseline" or validation.get("hard_validation") != "passed":
            raise ValidationFailure("Unsupported or invalid plan")
        if event_plan.get("contains_waveform_samples") or event_plan.get(
            "calibration_applied"
        ) or event_plan.get("playback_intensity_applied"):
            raise ValidationFailure("EventPlan contains unauthorized processing")
        duration = int(session["duration_samples"])
        buses = [np.zeros(duration, dtype=np.float64) for _ in range(8)]
        calibrated = [np.zeros(duration, dtype=np.float64) for _ in range(8)]
        occupancy = [np.zeros(duration, dtype=np.uint16) for _ in range(8)]
        traces: list[dict[str, Any]] = []
        event_counts: Counter[int] = Counter()
        total_motif_samples = 0
        for event in event_plan["events"]:
            if event.get("identity_mode") != "exact_frozen_identity":
                raise ValidationFailure("Event is not exact frozen identity")
            record, receipt = self.exact.access(event["motif_id"])
            metadata = record.metadata
            if metadata.source_hash != event["motif_hash"] or \
                    metadata.source_order != event["motif_source_order"] or \
                    metadata.archive_hash != self.bank.pre_access_hash or \
                    metadata.shape != tuple(record.samples.shape) or \
                    metadata.dtype != str(record.samples.dtype) or \
                    metadata.sample_count != event["duration_samples"] or \
                    not receipt.bitwise_equal or receipt.transform_path_entered:
                raise ValidationFailure(f"Event identity mismatch: {event['event_id']}")
            channel = int(event["logical_channel"])
            onset = int(event["onset_sample"])
            end = onset + metadata.sample_count
            if end != event["end_sample_exclusive"] or onset < 0 or end > duration:
                raise ValidationFailure(f"Event exceeds render bounds: {event['event_id']}")
            gain = float(event["relative_event_gain"])
            native = record.samples.astype(np.float64, copy=True)
            uncalibrated = native * gain
            event_calibrated = uncalibrated * self.calibration.reference_multiplier
            accumulate_event(buses, occupancy, channel, onset, uncalibrated)
            calibrated[channel][onset:end] += event_calibrated
            event_counts[channel] += 1
            total_motif_samples += metadata.sample_count
            traces.append({
                "event_id": event["event_id"],
                "logical_channel": channel,
                "onset_sample": onset,
                "end_sample_exclusive": end,
                "motif_id": metadata.motif_id,
                "motif_hash": metadata.source_hash,
                "source_order": metadata.source_order,
                "relative_event_gain": gain,
                "calibration_id": self.calibration.artifact_id,
                "calibration_multiplier": self.calibration.reference_multiplier,
                "exact_identity_verified": True,
                "rendered_once": True,
            })
        if len(traces) != len(event_plan["events"]) or len({
            item["event_id"] for item in traces
        }) != len(traces):
            raise ValidationFailure("Not every planned event rendered exactly once")
        uncalibrated_metrics = [
            channel_metrics(index, buses[index], occupancy[index], event_counts[index])
            for index in range(8)
        ]
        calibrated_metrics = [
            channel_metrics(index, calibrated[index], occupancy[index], event_counts[index])
            for index in range(8)
        ]
        active_channels = np.stack([item > 0 for item in occupancy])
        global_channel_concurrency = int(np.max(np.sum(active_channels, axis=0)))
        total_overlap_additions = int(sum(
            np.sum(np.maximum(item.astype(np.int64) - 1, 0)) for item in occupancy
        ))
        max_metric = max(calibrated_metrics, key=lambda item: item["sample_peak_linear"])
        max_true = max(
            calibrated_metrics, key=lambda item: item["estimated_true_peak_linear"]
        )
        finite = all(item["non_finite_sample_count"] == 0 for item in calibrated_metrics)
        unclipped = all(
            item["clipped_full_scale_sample_count"] == 0 for item in calibrated_metrics
        )
        headroom_pass = evaluate_headroom(
            calibrated_metrics, self.calibration.true_peak_ceiling_dbfs,
            len(traces), session["event_count"],
        )
        method_ref = self.references.closure_reference(
            "methods/measurement_methods.md", "Calibration.true_peak",
            "reproducibility_method", "tier_1",
        )
        implementation_ref = self.references.closure_reference(
            "scripts/run_x_alpha_closure.py", "estimate_true_peak",
            "reproducibility_implementation", "tier_1",
        )
        renderer_ref = self.references.direct(
            "frozen_morphology_renderer_contract", "stored_asset_form",
            "exact_rendering_contract",
        )
        asset_ref = self.references.direct(
            "frozen_morphology_asset_manifest", "assets", "frozen_identity",
        )
        freeze_ref = self.references.direct(
            "frozen_morphology_freeze_manifest", "immutable_fields",
            "frozen_identity",
        )
        method = true_peak_method_record(_sha256(method_ref.path))
        method["source_implementation_hash"] = _sha256(implementation_ref.path)
        method = _hashed(method)
        array_hashes = {
            str(index): canonical_array_hash(index, calibrated[index])
            for index in range(8)
        }
        receipt = _hashed({
            "schema_version": "wge.render_receipt.v1",
            "run_id": _load(run / "run_manifest.json")["run_id"],
            "session_id": session["session_id"],
            "sample_rate_hz": session["sample_rate_hz"],
            "duration_samples": duration,
            "logical_channel_count": 8,
            "render_dtype": "float64",
            "events_planned": session["event_count"],
            "events_rendered": len(traces),
            "total_motif_samples_placed": total_motif_samples,
            "calibration_id": self.calibration.artifact_id,
            "calibration_multiplier": self.calibration.reference_multiplier,
            "playback_intensity_applied": False,
            "normalization_applied": False,
            "limiter_applied": False,
            "transform_path_entered": False,
            "array_hashes": array_hashes,
            "array_hash_canonical_representation": {
                "dtype": "little_endian_float64",
                "shape_included": True,
                "logical_channel_index_included": True,
                "sample_byte_order": "C_contiguous",
                "algorithm": "sha256",
            },
            "core_plan_hashes": core_before,
            "archive_hash": self.bank.post_access_hash,
            "content_hash": "",
        })
        event_trace = _hashed({
            "schema_version": "wge.event_render_trace.v1",
            "event_count": len(traces), "events": traces, "content_hash": "",
        })
        metrics = _hashed({
            "schema_version": "wge.channel_render_metrics.v1",
            "full_scale_denominator": PCM16_FULL_SCALE,
            "uncalibrated": uncalibrated_metrics,
            "calibrated": calibrated_metrics,
            "content_hash": "",
        })
        overlap = _hashed({
            "schema_version": "wge.overlap_metrics.v1",
            "per_channel": [{
                "logical_channel": index,
                "maximum_same_channel_concurrency": calibrated_metrics[index][
                    "maximum_same_channel_concurrency"
                ],
                "overlap_sample_count": calibrated_metrics[index]["overlap_sample_count"],
                "overlap_fraction": calibrated_metrics[index]["overlap_fraction"],
            } for index in range(8)],
            "total_overlap_additions": total_overlap_additions,
            "maximum_global_logical_channel_concurrency": global_channel_concurrency,
            "global_channel_concurrency_one_second_bins": [
                int(np.max(np.sum(active_channels[:, start:start + session["sample_rate_hz"]],
                                  axis=0)))
                for start in range(0, duration, session["sample_rate_hz"])
            ],
            "channels_are_not_summed": True,
            "content_hash": "",
        })
        verdict = _hashed({
            "schema_version": "wge.headroom_verdict.v1",
            "verdict": "headroom_pass" if headroom_pass else "headroom_fail",
            "ceiling_dbfs": self.calibration.true_peak_ceiling_dbfs,
            "global_maximum_sample_peak_linear": max_metric["sample_peak_linear"],
            "global_maximum_sample_peak_dbfs": max_metric["sample_peak_dbfs"],
            "sample_peak_channel": max_metric["logical_channel"],
            "sample_peak_index": max_metric["sample_peak_index"],
            "global_maximum_true_peak_linear": max_true["estimated_true_peak_linear"],
            "global_maximum_true_peak_dbfs": max_true["estimated_true_peak_dbfs"],
            "true_peak_channel": max_true["logical_channel"],
            "margin_to_zero_db": -max_true["estimated_true_peak_dbfs"],
            "margin_to_ceiling_db":
                self.calibration.true_peak_ceiling_dbfs
                - max_true["estimated_true_peak_dbfs"],
            "all_channels_finite": finite,
            "no_sample_clipping": unclipped,
            "all_events_rendered_once": len(traces) == session["event_count"],
            "identity_verification": "passed",
            "unauthorized_processing": False,
            "wge4b_authorized": headroom_pass,
            "content_hash": "",
        })
        authority = _hashed({
            "schema_version": "wge.render_authority_snapshot.v1",
            "archive_hash": self.bank.post_access_hash,
            "archive_authority_tier": self.bank.authority.authority_tier,
            "renderer_contract": {
                "artifact_id": renderer_ref.artifact_id,
                "sha256": _sha256(renderer_ref.path),
            },
            "asset_manifest": {
                "artifact_id": asset_ref.artifact_id,
                "sha256": _sha256(asset_ref.path),
            },
            "freeze_manifest": {
                "artifact_id": freeze_ref.artifact_id,
                "sha256": _sha256(freeze_ref.path),
            },
            "calibration_id": self.calibration.artifact_id,
            "true_peak_method_artifact": method_ref.artifact_id,
            "qualified_plan_verdict_hash": qualification["content_hash"],
            "content_hash": "",
        })
        core_after = BaselineQualificationService.core_hashes(run)
        if core_after != core_before or self.bank.post_access_hash != self.bank.pre_access_hash:
            raise ValidationFailure("Rendering changed authoritative inputs")
        manifest = _hashed({
            "schema_version": "wge.render_audit_manifest.v1",
            "audit_id": "wge4a_exact_diagnostic_render_audit",
            "run_id": receipt["run_id"],
            "headroom_verdict": verdict["verdict"],
            "wge4b_authorized": verdict["wge4b_authorized"],
            "events_rendered": len(traces),
            "logical_channel_count": 8,
            "persistent_waveform_arrays": False,
            "audio_created": False,
            "document_hashes": {
                "render_receipt": receipt["content_hash"],
                "event_render_trace": event_trace["content_hash"],
                "per_channel_metrics": metrics["content_hash"],
                "overlap_metrics": overlap["content_hash"],
                "true_peak_method": method["content_hash"],
                "headroom_verdict": verdict["content_hash"],
                "authority_snapshot": authority["content_hash"],
            },
            "content_hash": "",
        })
        for values in (*buses, *calibrated):
            values.setflags(write=False)
        return RenderAuditResult(
            tuple(buses), tuple(calibrated), tuple(occupancy), {
                "render_audit_manifest.json": manifest,
                "render_receipt.json": receipt,
                "event_render_trace.json": event_trace,
                "per_channel_metrics.json": metrics,
                "overlap_metrics.json": overlap,
                "true_peak_method.json": method,
                "headroom_verdict.json": verdict,
                "authority_snapshot.json": authority,
            },
        )

    def audit(self, run: Path) -> dict[str, Any]:
        result = self.render(run)
        target = run.resolve() / "render_audit"
        target.mkdir(parents=True, exist_ok=True)
        for name, document in result.documents.items():
            _write(target / name, document)
        self._figures(target / "figures", result.documents)
        return result.documents["render_audit_manifest.json"]

    @staticmethod
    def _figures(target: Path, documents: dict[str, Any]) -> None:
        target.mkdir(parents=True, exist_ok=True)
        metrics = documents["per_channel_metrics.json"]
        calibrated = metrics["calibrated"]
        uncalibrated = metrics["uncalibrated"]
        channels = list(range(8))
        plots = {
            "per_channel_sample_peak.png": (
                [item["sample_peak_dbfs"] for item in calibrated], "Sample peak (dBFS)"
            ),
            "per_channel_true_peak.png": (
                [item["estimated_true_peak_dbfs"] for item in calibrated],
                "Estimated true peak (dBFS)",
            ),
            "per_channel_rms.png": (
                [item["rms"] for item in calibrated], "RMS (linear full scale)"
            ),
            "overlap_by_channel.png": (
                [item["overlap_fraction"] for item in calibrated], "Overlap fraction"
            ),
            "headroom_margin.png": (
                [-3.0 - item["estimated_true_peak_dbfs"] for item in calibrated],
                "Margin to -3 dBFS (dB)",
            ),
        }
        for filename, (values, label) in plots.items():
            figure, axis = plt.subplots(figsize=(8, 4))
            axis.bar(channels, values)
            axis.set_xlabel("Logical channel")
            axis.set_ylabel(label)
            axis.set_title("WGE-4A diagnostic render audit; no audio file created")
            figure.tight_layout()
            figure.savefig(target / filename, dpi=120)
            plt.close(figure)
        figure, axis = plt.subplots(figsize=(8, 4))
        axis.plot(channels, [item["sample_peak_linear"] for item in uncalibrated],
                  marker="o", label="Before ×1.1")
        axis.plot(channels, [item["sample_peak_linear"] for item in calibrated],
                  marker="o", label="After ×1.1")
        axis.set_xlabel("Logical channel")
        axis.set_ylabel("Sample peak (linear full scale)")
        axis.legend()
        axis.set_title("Calibration audit; no playback intensity")
        figure.tight_layout()
        figure.savefig(target / "calibration_before_after.png", dpi=120)
        plt.close(figure)
        overlap = documents["overlap_metrics.json"]
        figure, axis = plt.subplots(figsize=(9, 4))
        values = overlap["global_channel_concurrency_one_second_bins"]
        axis.step(range(len(values)), values, where="post")
        axis.set_xlabel("Time bin (seconds)")
        axis.set_ylabel("Simultaneously active logical channels")
        axis.set_title("Logical-channel concurrency; channels are not summed")
        figure.tight_layout()
        figure.savefig(target / "concurrency_over_time.png", dpi=120)
        plt.close(figure)

    @staticmethod
    def validate(run: Path) -> dict[str, Any]:
        target = run.resolve() / "render_audit"
        manifest = _load(target / "render_audit_manifest.json")
        for filename, expected in manifest["document_hashes"].items():
            name = f"{filename}.json"
            document = _load(target / name)
            if document.get("content_hash") != expected or not validate_content_hash(document):
                raise ValidationFailure(f"Render audit document hash failed: {name}")
        if manifest["audio_created"] or manifest["persistent_waveform_arrays"]:
            raise ValidationFailure("Render audit crossed the persistence boundary")
        return {
            "valid": True,
            "headroom_verdict": manifest["headroom_verdict"],
            "wge4b_authorized": manifest["wge4b_authorized"],
        }
