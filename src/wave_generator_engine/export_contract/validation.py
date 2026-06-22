import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from wave_generator_engine.config import ENGINE_ROOT
from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.profiles.hashing import validate_content_hash
from wave_generator_engine.profiles.hashing import content_hash
from .authority import (
    authority_inventory, verify_channel_mapping_evidence,
    verify_source_pcm16_evidence,
)


def validate_contract(
    contract: dict[str, Any], interchange_dir: Path | None = None
) -> dict[str, Any]:
    schema = json.loads(
        (ENGINE_ROOT / "schemas/diagnostic_wav_export_contract.schema.json").read_text()
    )
    try:
        Draft202012Validator(schema).validate(contract)
    except ValidationError as exc:
        raise ValidationFailure("Diagnostic WAV export contract schema failed") from exc
    if not validate_content_hash(contract):
        raise ValidationFailure("Diagnostic WAV export contract hash failed")
    inventory = authority_inventory(interchange_dir)
    if contract["authority_references"] != inventory:
        raise ValidationFailure("Diagnostic export authority snapshot changed")
    expected_snapshot_hash = content_hash({
        "authority_references": inventory, "content_hash": ""
    })
    if contract["authority_snapshot_hash"] != expected_snapshot_hash:
        raise ValidationFailure("Diagnostic export authority hash changed")
    verify_channel_mapping_evidence(interchange_dir)
    verify_source_pcm16_evidence(interchange_dir)
    mappings = contract["branch_mappings"]
    if len(mappings) != 4:
        raise ValidationFailure("Diagnostic export requires exactly four stereo branches")
    channels = [
        channel for item in mappings
        for channel in (item["left_logical_channel"], item["right_logical_channel"])
    ]
    if sorted(channels) != list(range(8)) or len(set(channels)) != 8:
        raise ValidationFailure("Logical-channel mapping is ambiguous or duplicated")
    if any(
        item["left_logical_channel"] != (item["source_order"] - 1) * 2
        or item["right_logical_channel"] != (item["source_order"] - 1) * 2 + 1
        for item in mappings
    ):
        raise ValidationFailure("Branch left/right order contradicts authority")
    if contract["sample_rate_hz"] != 48000 or contract["stereo_branch_count"] != 4:
        raise ValidationFailure("Diagnostic export structure is invalid")
    if contract["encoding"]["subtype"] != "signed_pcm16" or \
            contract["encoding"]["authority_status"] != \
            "tier_1_source_equivalent_diagnostic":
        raise ValidationFailure("Unsupported or unresolved diagnostic encoding")
    if contract["bit_depth"] != 16:
        raise ValidationFailure("Diagnostic export bit depth is unresolved")
    quantization = contract["quantization_policy"]
    if quantization["rounding"] != "nearest_integer_ties_to_even" or \
            quantization["overflow"] != "reject" or \
            quantization["non_finite"] != "reject":
        raise ValidationFailure("Quantization is not deterministic and fail-closed")
    if contract["dither_policy"]["mode"] != "none_prohibited":
        raise ValidationFailure("Dither behaviour is unresolved")
    if contract["calibration_stage"]["additional_multiplier_at_export"] != 1.0:
        raise ValidationFailure("Contract would double-apply calibration")
    if contract["playback_intensity_stage"]["baked_into_samples"]:
        raise ValidationFailure("Contract would bake playback intensity")
    blocked = set(contract["blocked_processing"])
    if not {"normalization", "limiting", "double_calibration",
            "baked_playback_intensity"}.issubset(blocked):
        raise ValidationFailure("Required blocked processing is missing")
    if contract["unresolved_items"]:
        raise ValidationFailure("Critical export-contract items remain unresolved")
    if contract["wge4b2_authorized"] is not True:
        raise ValidationFailure("WGE-4B2 is not authorized by the contract")
    text = json.dumps(contract).casefold()
    if "/users/" in text or "final_test" in text:
        raise ValidationFailure("Contract leaks a source path or blocked material")
    return {
        "valid": True,
        "contract_id": contract["contract_id"],
        "wge4b2_authorized": True,
    }
