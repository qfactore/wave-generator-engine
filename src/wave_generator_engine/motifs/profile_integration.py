from typing import Any

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.profiles.registry import Registry
from .loader import FrozenMotifBank
from wave_generator_engine.calibration.models import CalibrationPolicy


def validate_profile_integration(
    bank: FrozenMotifBank,
    calibration: CalibrationPolicy,
    registry: Registry | None = None,
) -> dict[str, Any]:
    profiles = registry or Registry.load()
    profile = profiles.load_entry("x_alpha_standard_v1")
    if profile["frozen_authority"]["archive_sha256"] != bank.pre_access_hash:
        raise ValidationFailure("Profile archive hash does not match motif bank")
    if profile["frozen_authority"]["identity_count"] != len(bank):
        raise ValidationFailure("Profile identity count does not match motif bank")
    if profile["calibration_policy"]["authority_artifact_id"] != calibration.artifact_id:
        raise ValidationFailure("Profile calibration authority does not match loaded policy")
    if profile["trust_level"] != "exact":
        raise ValidationFailure("X-Alpha Standard must retain exact trust")
    surface = profile["permitted_configuration_surface"]
    if surface["carrier_control"] or surface["motif_timing_override"]:
        raise ValidationFailure("Exact profile exposes a blocked control")
    if profile["profile_status"] != "preset_locked" or not profile["immutable"]:
        raise ValidationFailure("X-Alpha Standard must remain locked")
    if profile["executable"]:
        raise ValidationFailure("X-Alpha Standard must remain non-executable")
    return {
        "valid": True,
        "profile_id": profile["profile_id"],
        "exact_access_only": True,
        "archive_hash_matches": True,
        "identity_count_matches": True,
        "calibration_authority_matches": True,
        "carrier_control_exposed": False,
        "motif_time_scaling_available": False,
        "locked": True,
        "executable": False,
        "session_plan_created": False,
    }
