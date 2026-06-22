import hashlib
import struct
from pathlib import Path
from typing import Any

import numpy as np

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.profiles.hashing import content_hash
from .quantization import PCM16_MAX_ERROR, PCM16_MAX_INPUT
from .service import DiagnosticExportContractService


def parse_pcm16_wav(payload: bytes, contract: dict) -> dict[str, Any]:
    if len(payload) < 44 or payload[:4] != b"RIFF" or payload[8:12] != b"WAVE":
        raise ValidationFailure("Malformed RIFF/WAVE header")
    riff_size = struct.unpack_from("<I", payload, 4)[0]
    if riff_size != len(payload) - 8:
        raise ValidationFailure("RIFF size mismatch")
    offset = 12
    chunks: list[tuple[bytes, bytes]] = []
    while offset < len(payload):
        if offset + 8 > len(payload):
            raise ValidationFailure("Truncated WAV chunk header")
        chunk_id = payload[offset:offset + 4]
        size = struct.unpack_from("<I", payload, offset + 4)[0]
        start = offset + 8
        end = start + size
        if end > len(payload):
            raise ValidationFailure("Truncated WAV chunk")
        chunks.append((chunk_id, payload[start:end]))
        offset = end + (size & 1)
    if [item[0] for item in chunks] != [b"fmt ", b"data"]:
        raise ValidationFailure("Unexpected or reordered WAV chunks")
    fmt, data = chunks[0][1], chunks[1][1]
    if len(fmt) != 16:
        raise ValidationFailure("WAV fmt chunk size is invalid")
    format_code, channels, rate, byte_rate, alignment, bits = struct.unpack(
        "<HHIIHH", fmt
    )
    expected = contract["container"]
    if (format_code, channels, rate, byte_rate, alignment, bits) != (
        expected["format_code"], expected["channel_count_per_file"],
        contract["sample_rate_hz"], expected["byte_rate"],
        expected["block_alignment_bytes"], contract["bit_depth"],
    ):
        raise ValidationFailure("WAV format does not match frozen contract")
    if len(data) % alignment:
        raise ValidationFailure("WAV data size is not frame-aligned")
    frame_count = len(data) // alignment
    codes = np.frombuffer(data, dtype="<i2").reshape(frame_count, 2).copy()
    return {
        "frame_count": frame_count,
        "data": data,
        "codes": codes,
        "wav_sha256": hashlib.sha256(payload).hexdigest(),
        "data_chunk_sha256": hashlib.sha256(data).hexdigest(),
    }


def _independent_reference_codes(values: np.ndarray) -> np.ndarray:
    if values.dtype != np.float64 or values.ndim != 1 or not len(values):
        raise ValidationFailure("Readback reference must be non-empty float64 vector")
    if not np.all(np.isfinite(values)) or np.any(values < -1.0) or \
            np.any(values > PCM16_MAX_INPUT):
        raise ValidationFailure("Readback reference samples are invalid")
    return np.rint(values * 32768.0).astype("<i2")


class DiagnosticPcm16ReadbackValidator:
    """Independent parser and code-equivalence validator."""

    def __init__(self) -> None:
        service = DiagnosticExportContractService()
        self.contract = service.load()
        service.validate()

    def validate_bytes(
        self, payload: bytes, expected_left: np.ndarray, expected_right: np.ndarray
    ) -> dict[str, Any]:
        if expected_left.shape != expected_right.shape:
            raise ValidationFailure("Readback reference channel lengths differ")
        parsed = parse_pcm16_wav(payload, self.contract)
        if parsed["frame_count"] != len(expected_left):
            raise ValidationFailure("Readback frame count mismatch")
        left_codes = _independent_reference_codes(expected_left)
        right_codes = _independent_reference_codes(expected_right)
        if not np.array_equal(parsed["codes"][:, 0], left_codes) or \
                not np.array_equal(parsed["codes"][:, 1], right_codes):
            raise ValidationFailure("Readback PCM codes or channel order differ")
        decoded = parsed["codes"].astype(np.float64) / 32768.0
        expected = np.column_stack((expected_left, expected_right))
        maximum_error = float(np.max(np.abs(decoded - expected)))
        if maximum_error > PCM16_MAX_ERROR:
            raise ValidationFailure("Readback quantization error exceeds contract")
        result = {
            "schema_version": "wge.diagnostic_readback_result.v1",
            "valid": True,
            "frame_count": parsed["frame_count"],
            "wav_sha256": parsed["wav_sha256"],
            "data_chunk_sha256": parsed["data_chunk_sha256"],
            "maximum_quantization_error": maximum_error,
            "content_hash": "",
        }
        result["content_hash"] = content_hash(result)
        return result

    def validate_file(
        self, path: Path, expected_left: np.ndarray, expected_right: np.ndarray
    ) -> dict[str, Any]:
        return self.validate_bytes(path.read_bytes(), expected_left, expected_right)
