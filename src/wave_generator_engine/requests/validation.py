import math
from typing import Any

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.profiles.registry import Registry
from wave_generator_engine.profiles.validation import validate_schema


def validate_run_request(document: dict[str, Any], registry: Registry) -> dict[str, Any]:
    validate_schema(document, "run_request.schema.json")
    profile = registry.load_entry(document["source_profile_id"])
    preset = registry.load_entry(document["delivery_preset_id"])
    if preset["source_profile_id"] != profile["profile_id"]:
        raise ValidationFailure("Delivery preset and source profile do not match")
    selected = document["selected_session_ids"]
    if len(selected) != len(set(selected)):
        raise ValidationFailure("Duplicate session IDs are not allowed")
    valid_ids = {item["session_id"] for item in profile["session_topology"]["sessions"]}
    if not selected or not set(selected).issubset(valid_ids):
        raise ValidationFailure("Run request contains an unknown session")
    if document["requested_duration_seconds"] <= 0:
        raise ValidationFailure("Requested duration must be positive")
    if document["requested_duration_seconds"] != preset["nominal_duration_seconds"] and \
            "requested_duration_seconds" not in preset["allowed_overrides"]:
        raise ValidationFailure("Delivery preset does not permit a duration override")
    override = document.get("playback_default_override")
    if override is not None:
        if isinstance(override, bool) or not isinstance(override, (int, float)):
            raise ValidationFailure("Playback override must be numeric")
        if not math.isfinite(override) or not 0 <= override <= 1:
            raise ValidationFailure("Playback override is outside the engine safety range")
        if "playback_default_override" not in preset["allowed_overrides"]:
            raise ValidationFailure("Delivery preset does not permit a playback override")
    if document.get("focus_role_override") is not None:
        permissions = profile["permitted_configuration_surface"]
        if not permissions["focus_role_override"]:
            raise ValidationFailure("Focus Role override is not permitted")
        if document["focus_role_override"]["target_logical_channel"] not in \
                profile["channel_topology"]["logical_channel_ids"]:
            raise ValidationFailure("Focus Role target is not a logical channel")
    if document.get("focus_role_target") is not None:
        if document["requested_export_target"] != "analysis_report":
            raise ValidationFailure("Run-specific Focus Role target is diagnostic-only")
        if document["focus_role_target"] not in profile["channel_topology"]["logical_channel_ids"]:
            raise ValidationFailure("Focus Role target is not a logical channel")
    if document.get("motif_time_scale_ratio") is not None or \
            document.get("carrier_frequency_hz") is not None:
        raise ValidationFailure("Exact profiles reject timing and carrier overrides")
    return {
        "valid": True,
        "executable": False,
        "creates_session_plan": False,
        "creates_render_plan": False,
        "export_target_authorized": False,
    }
