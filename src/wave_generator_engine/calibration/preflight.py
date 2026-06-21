from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.motifs.loader import FrozenMotifBank
from .models import CalibrationPolicy
from .policy import load_calibration_policy

FINAL_HEADROOM_STATUS = "not_assessable_without_event_gain_and_overlap_plan"


def run_calibration_preflight(
    bank: FrozenMotifBank,
    policy: CalibrationPolicy | None = None,
    interchange_dir: Path | None = None,
) -> dict[str, Any]:
    resolved = policy or load_calibration_policy(interchange_dir)
    motifs: list[dict[str, Any]] = []
    source_before = {item.metadata.motif_id: item.samples.tobytes() for item in bank.records()}
    for record in bank.records():
        source = record.samples
        if not np.all(np.isfinite(source)):
            raise ValidationFailure("Calibration preflight requires finite motif samples")
        diagnostic = source.astype(np.float64, copy=True)
        raw_peak = float(np.max(np.abs(diagnostic)))
        raw_rms = float(np.sqrt(np.mean(np.square(diagnostic))))
        motifs.append({
            "motif_id": record.metadata.motif_id,
            "raw_sample_peak": raw_peak,
            "raw_rms": raw_rms,
            "projected_peak_at_reference_multiplier": raw_peak * resolved.reference_multiplier,
            "projected_rms_at_reference_multiplier": raw_rms * resolved.reference_multiplier,
            "diagnostic_dtype": "float64",
            "source_unchanged": True,
        })
    if any(item.samples.tobytes() != source_before[item.metadata.motif_id] for item in bank.records()):
        raise ValidationFailure("Calibration preflight modified source samples")
    ratios = [
        item["projected_rms_at_reference_multiplier"] / item["raw_rms"]
        for item in motifs if item["raw_rms"] != 0
    ]
    return {
        "report_type": "non_rendering_calibration_preflight",
        "policy": asdict(resolved),
        "motif_count": len(motifs),
        "projected_peak_distribution": {
            "minimum": min(item["projected_peak_at_reference_multiplier"] for item in motifs),
            "maximum": max(item["projected_peak_at_reference_multiplier"] for item in motifs),
        },
        "projected_rms_distribution": {
            "minimum": min(item["projected_rms_at_reference_multiplier"] for item in motifs),
            "maximum": max(item["projected_rms_at_reference_multiplier"] for item in motifs),
        },
        "finite_values": True,
        "diagnostic_intermediate": "float64",
        "playback_intensity_applied": False,
        "normalization_applied": False,
        "limiter_applied": False,
        "focus_role_applied": False,
        "relative_amplitude_preserved": bool(
            all(np.isclose(value, resolved.reference_multiplier) for value in ratios)
        ),
        "source_values_unchanged": True,
        "final_render_headroom_status": FINAL_HEADROOM_STATUS,
        "render_certification_claimed": False,
    }
