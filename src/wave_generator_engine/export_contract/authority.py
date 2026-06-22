import hashlib
import json
from pathlib import Path
from typing import Any

from wave_generator_engine.config import ENGINE_ROOT
from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.interchange.discovery import discover_interchange
from wave_generator_engine.qualification.authority import QualificationAuthority


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationFailure("Export-contract authority must be an object")
    return value


def authority_inventory(interchange_dir: Path | None = None) -> list[dict[str, Any]]:
    root = discover_interchange(ENGINE_ROOT, interchange_dir)
    authority = QualificationAuthority(interchange_dir)
    references = [
        authority.closure_reference(
            "data/calibration_audit.json", "source_format|playback_path",
            "source_recording_and_playback_architecture", "tier_1",
        ),
        authority.closure_reference(
            "scripts/run_x_alpha_closure.py",
            "carrier_analysis.logical_channel|analyze_wav.decode",
            "channel_order_and_pcm_decode", "tier_1",
        ),
        authority.closure_reference(
            "methods/measurement_methods.md", "Calibration",
            "calibration_measurement", "tier_1",
        ),
        authority.direct(
            "frozen_morphology_renderer_contract", "stored_asset_form",
            "native_render_input",
        ),
    ]
    values = [{
        "artifact_id": item.artifact_id,
        "authority_tier": item.authority_tier,
        "classification_status": item.classification_status,
        "source_field": item.source_field,
        "scope": item.scope,
        "sha256": _sha256(item.path),
    } for item in references]
    for relative, artifact_id, source_field in (
        ("manifests/decision_registry.json", "wave_gen_interchange_decision_registry",
         "AD-017|AD-018|AD-028"),
        ("handoff/CALIBRATION_HANDOFF.md", "x_alpha_calibration_handoff",
         "calibration|playback_intensity|delivery"),
        ("handoff/BLOCKED_BEHAVIORS.md", "wave_gen_interchange_blocked_behaviors",
         "playback_intensity|production_wav|24_bit"),
    ):
        path = root / relative
        values.append({
            "artifact_id": artifact_id,
            "authority_tier": "tier_1",
            "classification_status": "include",
            "source_field": source_field,
            "scope": "engine_handoff_policy",
            "sha256": _sha256(path),
        })
    return values


def verify_channel_mapping_evidence(interchange_dir: Path | None = None) -> None:
    reference = QualificationAuthority(interchange_dir).closure_reference(
        "scripts/run_x_alpha_closure.py",
        "carrier_analysis.logical_channel", "channel_order", "tier_1",
    )
    text = reference.path.read_text(encoding="utf-8")
    required = '(row["track_in_session"] - 1) * 2 + channel'
    if required not in text:
        raise ValidationFailure("Authoritative logical-channel mapping is ambiguous")


def verify_source_pcm16_evidence(interchange_dir: Path | None = None) -> None:
    reference = QualificationAuthority(interchange_dir).closure_reference(
        "data/calibration_audit.json", "source_format", "source_format", "tier_1",
    )
    source_format = _json(reference.path).get("source_format", {})
    expected = {
        "sample_rate_hz": 48000,
        "sample_format": "signed_integer_pcm",
        "bit_depth": 16,
        "channels_per_file": 2,
        "files_per_session": 4,
        "logical_channels_per_session": 8,
        "routing": "each stereo file is sent to an independent output device",
    }
    if source_format != expected:
        raise ValidationFailure("Source-equivalent PCM16 evidence changed")
