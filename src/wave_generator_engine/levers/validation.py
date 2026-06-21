import math
from typing import Any

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.profiles.hashing import validate_content_hash
from wave_generator_engine.profiles.validation import validate_schema

WAVEFORM_CATEGORIES = {
    "channel_roles", "packet_grammar", "pulse_pattern", "density",
    "timing", "motif_morphology",
}


def validate_lever_registry(document: dict[str, Any]) -> None:
    validate_schema(document, "lever_definition.schema.json")
    if not validate_content_hash(document):
        raise ValidationFailure("Lever registry content hash mismatch")
    levers = document["levers"]
    ids = [item["lever_id"] for item in levers]
    if len(ids) != len(set(ids)):
        raise ValidationFailure("Lever IDs must be unique")
    if "carrier_frequency_hz" in ids:
        carrier = next(item for item in levers if item["lever_id"] == "carrier_frequency_hz")
        if carrier["availability"] in {"available", "locked"} or carrier["profile_mutable"] or carrier["run_mutable"]:
            raise ValidationFailure("Adjustable carrier-frequency lever is forbidden")
    if any(item["category"] == "calibration" and item["profile_mutable"] for item in levers):
        raise ValidationFailure("Calibration cannot be an editable lever")
    if any(item["lever_id"] == "playback_intensity" for item in levers):
        raise ValidationFailure("Playback intensity is not a waveform LeverSet value")
    scale = next(item for item in levers if item["lever_id"] == "motif_time_scale_ratio")
    if scale["availability"] != "experimental_uncertified" or not scale["locked_in_exact"]:
        raise ValidationFailure("Motif time scaling must remain uncertified and exact-locked")
    if scale["minimum"] is not None or scale["maximum"] is not None:
        raise ValidationFailure("No motif time-scaling range is certified")


def validate_view(document: dict[str, Any], registry: Any) -> None:
    if not validate_content_hash(document):
        raise ValidationFailure("Lever view content hash mismatch")
    lever_registry = registry.load_entry(document["lever_registry_id"])
    definitions = {item["lever_id"]: item for item in lever_registry["levers"]}
    for lever_id in document["visible_lever_ids"]:
        if lever_id not in definitions:
            raise ValidationFailure("Lever view references an unknown lever")
    if document["view_id"] == "basic":
        blocked = {
            "trailing_event_count", "primary_to_trailing_gap",
            "trailing_event_spacing", "cycle_span",
            "continuation_probability", "pattern_contrast",
            "motif_time_scale_ratio",
        }
        if blocked & set(document["visible_lever_ids"]):
            raise ValidationFailure("Basic view exposes hidden controls")


def validate_lever_set(
    document: dict[str, Any],
    registry_document: dict[str, Any],
    trust_level: str,
) -> None:
    validate_schema(document, "lever_set.schema.json")
    if not validate_content_hash(document):
        raise ValidationFailure("LeverSet content hash mismatch")
    definitions = {item["lever_id"]: item for item in registry_document["levers"]}
    for lever_id, value in document["values"].items():
        if lever_id not in definitions:
            raise ValidationFailure(f"Unknown lever: {lever_id}")
        definition = definitions[lever_id]
        if definition["availability"] in {"future", "experimental_uncertified", "blocked"}:
            raise ValidationFailure(f"Unavailable lever used: {lever_id}")
        if trust_level == "exact" and definition["locked_in_exact"] and document.get("mutable", False):
            raise ValidationFailure(f"Exact-locked lever cannot be mutable: {lever_id}")
        minimum, maximum = definition["minimum"], definition["maximum"]
        if (minimum is None or maximum is None) and definition["value_type"] in {"integer", "number"}:
            if definition["availability"] != "locked":
                raise ValidationFailure("Null certified range is not free permission")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not math.isfinite(value):
                raise ValidationFailure("Lever values must be finite")
            if minimum is not None and value < minimum:
                raise ValidationFailure("Lever value is below its certified range")
            if maximum is not None and value > maximum:
                raise ValidationFailure("Lever value is above its certified range")
    focus = document["role_bindings"]["focus_role"]
    if not focus["associated_density_emphasis"]:
        raise ValidationFailure("Focus density emphasis must move with the role")
    if focus["changes_global_playback_intensity"]:
        raise ValidationFailure("Focus Role must not alter global intensity")
