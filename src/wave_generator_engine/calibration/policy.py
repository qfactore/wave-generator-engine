import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from wave_generator_engine.config import ENGINE_ROOT
from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.interchange.discovery import discover_interchange
from .models import CalibrationPolicy


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationFailure("Calibration authority must be an object")
    return value


def load_calibration_policy(interchange_dir: Path | None = None) -> CalibrationPolicy:
    root = discover_interchange(ENGINE_ROOT, interchange_dir)
    artifact = _json(root / "bank/calibration/x_alpha_reference_calibration_v1.json")
    schema = _json(root / "schemas/x_alpha_reference_calibration.schema.json")
    Draft202012Validator.check_schema(schema)
    try:
        Draft202012Validator(schema).validate(artifact)
    except ValidationError as exc:
        raise ValidationFailure("Calibration policy schema validation failed") from exc
    rules = artifact["settled_rules"]
    safety = artifact["render_safety"]
    guidance = artifact["tier_3_guidance"]
    policy = CalibrationPolicy(
        artifact_id=artifact["artifact_id"],
        reference_multiplier=rules["reference_multiplier"],
        default_playback_intensity=rules["default_playback_intensity"],
        playback_intensity_stage=rules["playback_intensity_stage"],
        per_motif_normalization=rules["per_motif_normalization"],
        per_session_normalization=rules["per_session_normalization"],
        default_limiter=rules["default_limiter"],
        preserve_relative_amplitude_relationships=rules["preserve_relative_amplitude_relationships"],
        invalid_headroom_policy=rules["invalid_headroom_policy"],
        internal_intermediate=safety["internal_intermediate"],
        true_peak_ceiling_dbfs=safety["true_peak_ceiling_dbfs"],
        reserve_db=safety["reserve_db"],
        delivery_24_bit_status=guidance["status"],
    )
    if policy != CalibrationPolicy(
        "x_alpha_reference_calibration_v1", 1.1, 0.8, "post_calibration",
        False, False, False, True, "fail_validation", "float64", -3.0, 3.0,
        "pending_target_hardware_validation",
    ):
        raise ValidationFailure("Calibration policy binding values changed")
    return policy
