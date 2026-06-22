import hashlib
import inspect
import json
import os
import struct
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.export_contract.manifest import (
    DiagnosticExportManifestBuilder,
)
from wave_generator_engine.export_contract.quantization import (
    PCM16_MAX_ERROR, PCM16_MAX_INPUT, quantize_pcm16,
)
from wave_generator_engine.export_contract.readback import (
    DiagnosticPcm16ReadbackValidator, parse_pcm16_wav,
)
from wave_generator_engine.export_contract.service import (
    DiagnosticExportContractService,
)
from wave_generator_engine.export_contract.writer import (
    DiagnosticPcm16WavWriter, build_pcm16_wav_bytes, interleave_pcm16,
    validate_frame_count,
)
from wave_generator_engine.profiles.hashing import validate_content_hash

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = DiagnosticExportContractService().load()


def fixture_channels() -> tuple[np.ndarray, np.ndarray]:
    left = np.array([
        -1.0, -2.5 / 32768, -1.5 / 32768, -0.5 / 32768,
        0.0, 0.5 / 32768, 1.5 / 32768, 2.5 / 32768,
        PCM16_MAX_INPUT,
    ], dtype=np.float64)
    right = left[::-1].copy()
    return left, right


def test_exact_ties_to_even_for_both_signs() -> None:
    values = np.array([
        -2.5 / 32768, -1.5 / 32768, -0.5 / 32768,
        0.5 / 32768, 1.5 / 32768, 2.5 / 32768,
    ], dtype=np.float64)
    assert quantize_pcm16(values).tolist() == [-2, -2, 0, 0, 2, 2]


def test_quantizer_bounds_dtype_error_and_no_saturation() -> None:
    values = np.array([-1.0, 0.0, PCM16_MAX_INPUT], dtype=np.float64)
    codes = quantize_pcm16(values)
    assert codes.dtype == np.dtype("<i2")
    assert codes.tolist() == [-32768, 0, 32767]
    decoded = codes.astype(np.float64) / 32768
    assert np.max(np.abs(decoded - values)) <= PCM16_MAX_ERROR
    for bad in (
        np.array([1.0], dtype=np.float64),
        np.array([-1.00001], dtype=np.float64),
        np.array([np.nan], dtype=np.float64),
        np.array([np.inf], dtype=np.float64),
        np.array([0.0], dtype=np.float32),
    ):
        with pytest.raises(ValidationFailure):
            quantize_pcm16(bad)


def test_stereo_interleaving_is_exact_l0_r0_order() -> None:
    left = np.array([1 / 32768, 2 / 32768], dtype=np.float64)
    right = np.array([-1 / 32768, -2 / 32768], dtype=np.float64)
    data = interleave_pcm16(left, right)
    assert np.frombuffer(data, dtype="<i2").tolist() == [1, -1, 2, -2]
    assert data == struct.pack("<hhhh", 1, -1, 2, -2)


@pytest.mark.parametrize(("left", "right"), [
    (np.array([], dtype=np.float64), np.array([], dtype=np.float64)),
    (np.zeros(2, dtype=np.float64), np.zeros(3, dtype=np.float64)),
    (np.zeros((2, 1), dtype=np.float64), np.zeros(2, dtype=np.float64)),
    (np.zeros(2, dtype=np.float32), np.zeros(2, dtype=np.float64)),
])
def test_stereo_input_validation(left: np.ndarray, right: np.ndarray) -> None:
    with pytest.raises(ValidationFailure):
        interleave_pcm16(left, right)


def test_frame_count_overflow_fails_before_allocation() -> None:
    with pytest.raises(ValidationFailure, match="RIFF"):
        validate_frame_count((0xFFFFFFFF - 36) // 4 + 1)


def test_pcm16_wav_header_and_sizes_exact() -> None:
    left, right = fixture_channels()
    payload, data = build_pcm16_wav_bytes(left, right, CONTRACT)
    assert payload[:4] == b"RIFF"
    assert struct.unpack_from("<I", payload, 4)[0] == len(payload) - 8
    assert payload[8:12] == b"WAVE"
    assert payload[12:16] == b"fmt "
    assert struct.unpack_from("<I", payload, 16)[0] == 16
    assert struct.unpack_from("<HHIIHH", payload, 20) == (
        1, 2, 48000, 192000, 4, 16
    )
    assert payload[36:40] == b"data"
    assert struct.unpack_from("<I", payload, 40)[0] == len(data) == len(left) * 4
    assert len(payload) == 44 + len(data)
    assert parse_pcm16_wav(payload, CONTRACT)["frame_count"] == len(left)


def test_readback_exact_codes_and_hashes() -> None:
    left, right = fixture_channels()
    payload, data = build_pcm16_wav_bytes(left, right, CONTRACT)
    result = DiagnosticPcm16ReadbackValidator().validate_bytes(
        payload, left, right
    )
    assert result["valid"]
    assert result["frame_count"] == len(left)
    assert result["wav_sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["data_chunk_sha256"] == hashlib.sha256(data).hexdigest()
    assert result["maximum_quantization_error"] <= PCM16_MAX_ERROR
    assert validate_content_hash(result)
    schema = json.loads(
        (ROOT / "schemas/diagnostic_readback_result.schema.json").read_text()
    )
    Draft202012Validator(schema).validate(result)


def test_readback_rejects_swap_modified_truncated_and_malformed() -> None:
    left, right = fixture_channels()
    payload, _ = build_pcm16_wav_bytes(left, right, CONTRACT)
    validator = DiagnosticPcm16ReadbackValidator()
    with pytest.raises(ValidationFailure, match="codes|channel"):
        validator.validate_bytes(payload, right, left)
    modified = bytearray(payload)
    modified[44] ^= 1
    with pytest.raises(ValidationFailure, match="codes"):
        validator.validate_bytes(bytes(modified), left, right)
    with pytest.raises(ValidationFailure, match="size|Truncated"):
        validator.validate_bytes(payload[:-1], left, right)
    malformed = b"NOPE" + payload[4:]
    with pytest.raises(ValidationFailure, match="Malformed"):
        validator.validate_bytes(malformed, left, right)


def test_readback_rejects_wrong_subtype_and_metadata_chunk() -> None:
    left, right = fixture_channels()
    payload, _ = build_pcm16_wav_bytes(left, right, CONTRACT)
    wrong = bytearray(payload)
    struct.pack_into("<H", wrong, 20, 3)
    with pytest.raises(ValidationFailure, match="format"):
        parse_pcm16_wav(bytes(wrong), CONTRACT)
    junk = b"JUNK" + struct.pack("<I", 4) + b"test"
    augmented = payload[:36] + junk + payload[36:]
    augmented = augmented[:4] + struct.pack("<I", len(augmented) - 8) + augmented[8:]
    with pytest.raises(ValidationFailure, match="Unexpected"):
        parse_pcm16_wav(augmented, CONTRACT)


def test_repeated_bytes_are_environment_and_cwd_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    left, right = fixture_channels()
    writer = DiagnosticPcm16WavWriter()
    first, first_data = writer.bytes(left, right)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TZ", "Pacific/Kiritimati")
    second, second_data = writer.bytes(left, right)
    assert first == second
    assert first_data == second_data


def test_synthetic_write_readback_and_cleanup(tmp_path: Path) -> None:
    left, right = fixture_channels()
    writer = DiagnosticPcm16WavWriter()
    written = writer.write_synthetic(tmp_path, "synthetic_branch.wav", left, right)
    assert written.path.is_file()
    result = DiagnosticPcm16ReadbackValidator().validate_file(
        written.path, left, right
    )
    assert result["wav_sha256"] == written.wav_sha256
    assert result["data_chunk_sha256"] == written.data_chunk_sha256
    written.path.unlink()
    assert not list(tmp_path.glob("*.wav"))


def test_output_path_collisions_traversal_and_symlink_escape_fail(
    tmp_path: Path,
) -> None:
    left, right = fixture_channels()
    writer = DiagnosticPcm16WavWriter()
    for filename in ("../escape.wav", "/absolute.wav", "not-wave.bin"):
        with pytest.raises(ValidationFailure, match="unsafe"):
            writer.write_synthetic(tmp_path, filename, left, right)
    collision = tmp_path / "collision.wav"
    collision.write_bytes(b"existing")
    with pytest.raises(ValidationFailure, match="collision"):
        writer.write_synthetic(tmp_path, collision.name, left, right)
    link = tmp_path / "linked-root"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValidationFailure, match="root"):
        writer.write_synthetic(link, "synthetic.wav", left, right)


def test_frozen_branch_filenames_are_contract_driven() -> None:
    writer = DiagnosticPcm16WavWriter()
    assert [writer.branch_filename(index) for index in range(1, 5)] == \
        CONTRACT["filename_policy"]["resolved_filenames"]
    with pytest.raises(ValidationFailure, match="branch"):
        writer.branch_filename(5)


def test_mutated_contract_values_fail_writer_core() -> None:
    left, right = fixture_channels()
    for path, value in (
        (("sample_rate_hz",), 44100),
        (("encoding", "subtype"), "signed_pcm24"),
        (("dither_policy", "mode"), "tpdf"),
        (("calibration_stage", "additional_multiplier_at_export"), 1.1),
        (("playback_intensity_stage", "baked_into_samples"), True),
    ):
        changed = json.loads(json.dumps(CONTRACT))
        target = changed
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        with pytest.raises(ValidationFailure):
            build_pcm16_wav_bytes(left, right, changed)


def test_future_manifest_model_and_schemas() -> None:
    left, right = fixture_channels()
    payload, data = build_pcm16_wav_bytes(left, right, CONTRACT)
    files = [{
        "branch_number": index,
        "left_logical_channel": (index - 1) * 2,
        "right_logical_channel": (index - 1) * 2 + 1,
        "filename": CONTRACT["filename_policy"]["resolved_filenames"][index - 1],
        "sample_rate_hz": 48000,
        "frame_count": len(left),
        "encoding": "signed_pcm16",
        "bit_depth": 16,
        "wav_sha256": hashlib.sha256(payload).hexdigest(),
        "data_chunk_sha256": hashlib.sha256(data).hexdigest(),
        "readback_status": "passed",
        "maximum_quantization_error": PCM16_MAX_ERROR,
    } for index in range(1, 5)]
    manifest = DiagnosticExportManifestBuilder.build(
        CONTRACT, "a" * 64, {str(index): "b" * 64 for index in range(8)}, files
    )
    assert validate_content_hash(manifest)
    manifest_schema = json.loads(
        (ROOT / "schemas/diagnostic_export_manifest.schema.json").read_text()
    )
    file_schema = json.loads(
        (ROOT / "schemas/diagnostic_wav_file_record.schema.json").read_text()
    )
    Draft202012Validator(manifest_schema).validate(manifest)
    for record in files:
        Draft202012Validator(file_schema).validate(record)


def test_writer_core_has_no_source_render_or_frozen_motif_dependency() -> None:
    sources = "\n".join(
        inspect.getsource(item)
        for item in (
            DiagnosticPcm16WavWriter,
            DiagnosticPcm16ReadbackValidator,
            DiagnosticExportManifestBuilder,
        )
    ).casefold()
    for forbidden in (
        "renderauditservice", "frozenmotif", "event_plan", "runs/latest",
        "calibration_multiplier *", "playback_intensity *",
    ):
        assert forbidden not in sources
    assert not (ROOT / "runs/latest/diagnostic_export").exists()
