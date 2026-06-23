import copy
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.export_contract.authority import (
    authority_inventory, verify_channel_mapping_evidence,
    verify_source_pcm16_evidence,
)
from wave_generator_engine.export_contract.quantization import (
    PCM16_MAX_ERROR, PCM16_MAX_INPUT, decode_pcm16, quantize_pcm16,
)
from wave_generator_engine.export_contract.service import (
    DiagnosticExportContractService,
)
from wave_generator_engine.export_contract.validation import validate_contract
from wave_generator_engine.profiles.hashing import content_hash
from wave_generator_engine.qualification.authority import select_permitted_artifact

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "contracts/diagnostic_wav_export_contract_v1.json"


def _contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text())


def _rehash(value: dict) -> dict:
    value["content_hash"] = ""
    value["content_hash"] = content_hash(value)
    return value


def test_contract_schema_authority_and_lock_validate() -> None:
    contract = _contract()
    schema = json.loads(
        (ROOT / "schemas/diagnostic_wav_export_contract.schema.json").read_text()
    )
    Draft202012Validator(schema).validate(contract)
    assert DiagnosticExportContractService().validate()["valid"]
    assert contract["status"] == "locked_diagnostic_contract"
    assert contract["user_editable"] is False
    assert contract["authority_references"] == authority_inventory()
    verify_channel_mapping_evidence()
    verify_source_pcm16_evidence()


def test_authoritative_branch_mapping_is_complete_and_ordered() -> None:
    mappings = _contract()["branch_mappings"]
    assert [
        (item["left_logical_channel"], item["right_logical_channel"])
        for item in mappings
    ] == [(0, 1), (2, 3), (4, 5), (6, 7)]
    assert sorted(
        channel for item in mappings
        for channel in (item["left_logical_channel"], item["right_logical_channel"])
    ) == list(range(8))
    assert all(
        item["provenance_expression"]
        == "(track_in_session - 1) * 2 + stereo_channel_index"
        for item in mappings
    )


def test_ambiguous_mapping_and_unsupported_encoding_fail_closed() -> None:
    ambiguous = copy.deepcopy(_contract())
    ambiguous["branch_mappings"][1]["left_logical_channel"] = 0
    with pytest.raises(ValidationFailure, match="mapping"):
        validate_contract(_rehash(ambiguous))
    provisional = copy.deepcopy(_contract())
    provisional["encoding"]["subtype"] = "signed_pcm24"
    provisional["encoding"]["authority_status"] = "tier_3_provisional"
    provisional["bit_depth"] = 24
    with pytest.raises(ValidationFailure, match="schema|encoding|bit depth"):
        validate_contract(_rehash(provisional))


def test_blocked_and_final_test_authority_is_rejected() -> None:
    artifact = {
        "id": "blocked",
        "classification_status": "blocked",
        "authority_tier": "tier_1",
        "blocked_use": ["final-test arrays"],
    }
    with pytest.raises(ValidationFailure):
        select_permitted_artifact([artifact], "blocked")


def test_calibration_playback_and_processing_boundaries() -> None:
    contract = _contract()
    assert contract["calibration_stage"]["additional_multiplier_at_export"] == 1.0
    assert contract["playback_intensity_stage"]["baked_into_samples"] is False
    assert contract["dither_policy"]["mode"] == "none_prohibited"
    blocked = set(contract["blocked_processing"])
    assert {"normalization", "limiting", "double_calibration",
            "baked_playback_intensity"}.issubset(blocked)


@pytest.mark.parametrize(("section", "field", "value", "message"), [
    ("calibration_stage", "additional_multiplier_at_export", 1.1, "calibration"),
    ("playback_intensity_stage", "baked_into_samples", True, "playback"),
    ("dither_policy", "mode", "tpdf", "Dither"),
])
def test_unsafe_processing_contracts_fail(
    section: str, field: str, value, message: str
) -> None:
    contract = copy.deepcopy(_contract())
    contract[section][field] = value
    with pytest.raises(ValidationFailure, match=message):
        validate_contract(_rehash(contract))


def test_pcm16_quantizer_edge_values_and_rounding() -> None:
    values = np.array([
        -1.0, -1.5 / 32768, -0.5 / 32768, 0.0,
        0.5 / 32768, 1.5 / 32768, PCM16_MAX_INPUT,
    ], dtype=np.float64)
    codes = quantize_pcm16(values)
    assert codes.tolist() == [-32768, -2, 0, 0, 0, 2, 32767]
    decoded = decode_pcm16(codes)
    assert np.max(np.abs(decoded - values)) <= PCM16_MAX_ERROR
    assert quantize_pcm16(np.array([-1.0], dtype=np.float64))[0] == -32768


@pytest.mark.parametrize("value", [
    1.0, PCM16_MAX_INPUT + 1 / 32768, -1.00001, np.nan, np.inf, -np.inf,
])
def test_pcm16_quantizer_rejects_invalid_values(value: float) -> None:
    with pytest.raises(ValidationFailure):
        quantize_pcm16(np.array([value], dtype=np.float64))


def test_filename_policy_is_neutral_unique_and_path_safe() -> None:
    filenames = _contract()["filename_policy"]["resolved_filenames"]
    assert len(filenames) == len(set(filenames)) == 4
    assert all(name.startswith("x_alpha_session_01_baseline_branch_") for name in filenames)
    assert all("/" not in name and "\\" not in name for name in filenames)
    text = " ".join(filenames).casefold()
    assert "motif" not in text and "users" not in text


def test_wge4b1_creates_no_audio_or_waveform_artifact() -> None:
    for root in (ROOT / "reports", ROOT / "contracts"):
        assert not list(root.rglob("*.wav"))
        assert not list(root.rglob("*.wave"))
        assert not list(root.rglob("*.aiff"))
        assert not list(root.rglob("*.flac"))
        assert not list(root.rglob("*.mp3"))
        assert not list(root.rglob("*.ogg"))
        assert not list(root.rglob("*.npy"))
        assert not list(root.rglob("*.npz"))


def test_cli_contract_commands_are_read_only_json() -> None:
    executable = ROOT / ".venv/bin/wge"
    manifest_path = ROOT / "runs/latest/diagnostic_export/export_manifest.json"
    before = manifest_path.read_bytes() if manifest_path.exists() else None
    shown = subprocess.run(
        [str(executable), "export", "contract", "show", "--json"],
        cwd=ROOT, text=True, capture_output=True, check=True,
    )
    validated = subprocess.run(
        [str(executable), "export", "contract", "validate", "--json"],
        cwd=ROOT, text=True, capture_output=True, check=True,
    )
    assert json.loads(shown.stdout)["contract_id"] == \
        "diagnostic_wav_export_contract_v1"
    assert json.loads(validated.stdout)["wge4b2_authorized"]
    assert (manifest_path.read_bytes() if manifest_path.exists() else None) == before
