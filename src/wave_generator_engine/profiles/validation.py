from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from wave_generator_engine.config import (
    EXPECTED_FROZEN_SHA256, EXPECTED_IDENTITY_COUNT, SCHEMA_ROOT,
)
from wave_generator_engine.errors import ValidationFailure
from .hashing import validate_content_hash
from .loader import load_document

IMMUTABLE_STATUSES = {"preset_locked", "active", "archived"}
SELECTABLE_STATUSES = {"preset_locked", "active"}


def validate_schema(document: dict[str, Any], schema_name: str) -> None:
    schema = load_document(SCHEMA_ROOT / schema_name)
    Draft202012Validator.check_schema(schema)
    try:
        Draft202012Validator(schema).validate(document)
    except ValidationError as exc:
        raise ValidationFailure(f"{schema_name} validation failed: {exc.message}") from exc


def validate_source_profile(document: dict[str, Any]) -> None:
    validate_schema(document, "source_profile.schema.json")
    if not validate_content_hash(document):
        raise ValidationFailure("Source-profile content hash mismatch")
    status = document["profile_status"]
    if status in IMMUTABLE_STATUSES and document["immutable"] is not True:
        raise ValidationFailure(f"{status} profiles must be immutable")
    if status == "invalid" or status == "deprecated":
        if document.get("selectable", False):
            raise ValidationFailure(f"{status} profiles cannot be selectable")
    if document["executable"]:
        raise ValidationFailure("WGE-1 source profiles must be non-executable")
    frozen = document["frozen_authority"]
    if frozen["archive_sha256"] != EXPECTED_FROZEN_SHA256:
        raise ValidationFailure("Frozen archive authority changed")
    if frozen["identity_count"] != EXPECTED_IDENTITY_COUNT:
        raise ValidationFailure("Frozen identity count changed")
    sessions = document["session_topology"]["sessions"]
    ids = [item["session_id"] for item in sessions]
    if len(ids) != 7 or len(set(ids)) != 7 or set(ids) != set(range(1, 8)):
        raise ValidationFailure("Source profile must define seven unique sessions")
    expected_modes = {
        1: "baseline", 2: "baseline", 3: "baseline", 4: "baseline",
        5: "dense", 6: "dense", 7: "complex",
    }
    if {item["session_id"]: item["mode_id"] for item in sessions} != expected_modes:
        raise ValidationFailure("Session mode assignments are invalid")
    channels = document["channel_topology"]
    if channels["indexing"] != "zero_based_0_7" or channels["logical_channel_ids"] != list(range(8)):
        raise ValidationFailure("Engine channels must use canonical 0-7 indexing")
    focus = channels["focus_role"]
    if focus["associated_density_emphasis"] is not True:
        raise ValidationFailure("Focus Role must carry density emphasis")
    if focus["changes_global_playback_intensity"] or focus["changes_render_calibration"]:
        raise ValidationFailure("Focus Role must remain independent of intensity and calibration")
    calibration = document["calibration_policy"]["resolved_validation"]
    if calibration != {
        "reference_multiplier": 1.1,
        "preserve_relative_amplitude_relationships": True,
        "per_motif_normalization": False,
        "per_session_normalization": False,
        "default_limiter": False,
        "invalid_headroom_policy": "fail_validation",
    }:
        raise ValidationFailure("Calibration contract changed")
    if document["calibration_policy"]["authority_artifact_id"] != \
            "x_alpha_reference_calibration_v1":
        raise ValidationFailure("Calibration authority changed")
    policies = set(document["authority_snapshot"]["policy_artifact_ids"])
    if policies != {
        "x_alpha_reference_calibration_v1",
        "x_alpha_carrier_frequency_policy_v1",
        "x_alpha_pulse_pattern_grammar_v1",
        "x_alpha_macro_density_state_model_v1",
        "x_alpha_timing_dependency_policy_v1",
    }:
        raise ValidationFailure("Authority policy references are incomplete")
    surface = document["permitted_configuration_surface"]
    if document["trust_level"] in {"exact", "bounded"} and (
        surface["carrier_control"] or surface["motif_timing_override"]
        or surface["calibration_override"]
    ):
        raise ValidationFailure("Exact and bounded prohibited controls cannot be unlocked")


def validate_parent(profile: dict[str, Any], parent: dict[str, Any]) -> None:
    if profile.get("parent_profile_id") != parent.get("profile_id"):
        raise ValidationFailure("Parent profile ID mismatch")
    if profile.get("parent_content_hash") != parent.get("content_hash"):
        raise ValidationFailure("Parent content hash mismatch")
    if profile.get("parent_profile_version") != parent.get("profile_version"):
        raise ValidationFailure("Parent profile version mismatch")


def assert_editable(profile: dict[str, Any]) -> None:
    if profile["profile_status"] != "draft" or profile["immutable"]:
        raise ValidationFailure("Only mutable draft profiles may be edited")
