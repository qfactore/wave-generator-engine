import hashlib
import os
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from wave_generator_engine.errors import ValidationFailure
from .quantization import (
    PCM16_MAX, PCM16_MAX_ERROR, PCM16_MAX_INPUT, PCM16_MIN, PCM16_SCALE,
    quantize_pcm16,
)
from .service import DiagnosticExportContractService


@dataclass(frozen=True)
class WavWriteResult:
    path: Path
    frame_count: int
    data_byte_count: int
    wav_sha256: str
    data_chunk_sha256: str


def validate_frame_count(frame_count: int) -> None:
    maximum = (0xFFFFFFFF - 36) // 4
    if frame_count <= 0 or frame_count > maximum:
        raise ValidationFailure("WAV frame count exceeds contract or RIFF size limit")


def interleave_pcm16(left: np.ndarray, right: np.ndarray) -> bytes:
    if left.dtype != np.float64 or right.dtype != np.float64:
        raise ValidationFailure("Stereo writer requires float64 channel arrays")
    if left.ndim != 1 or right.ndim != 1:
        raise ValidationFailure("Stereo writer requires one-dimensional channels")
    if not len(left) or not len(right):
        raise ValidationFailure("Empty diagnostic WAV channels are prohibited")
    if len(left) != len(right):
        raise ValidationFailure("Stereo channel lengths differ")
    validate_frame_count(len(left))
    codes = np.empty((len(left), 2), dtype="<i2")
    codes[:, 0] = quantize_pcm16(left)
    codes[:, 1] = quantize_pcm16(right)
    return codes.tobytes(order="C")


def build_pcm16_wav_bytes(
    left: np.ndarray, right: np.ndarray, contract: dict
) -> tuple[bytes, bytes]:
    container = contract["container"]
    encoding = contract["encoding"]
    quantization = contract["quantization_policy"]
    if contract["sample_rate_hz"] != 48000 or \
            container["format_code"] != 1 or \
            container["channel_count_per_file"] != 2 or \
            container["byte_order"] != "little_endian" or \
            encoding["subtype"] != "signed_pcm16" or contract["bit_depth"] != 16:
        raise ValidationFailure("Contract does not authorize deterministic PCM16 WAV")
    if quantization["positive_scale_factor"] != PCM16_SCALE or \
            quantization["negative_scale_factor"] != PCM16_SCALE or \
            quantization["integer_minimum"] != PCM16_MIN or \
            quantization["integer_maximum"] != PCM16_MAX or \
            quantization["valid_input_maximum"] != PCM16_MAX_INPUT or \
            quantization["maximum_absolute_error_normalized"] != PCM16_MAX_ERROR or \
            quantization["rounding"] != "nearest_integer_ties_to_even":
        raise ValidationFailure("Contract quantization differs from writer core")
    if contract["dither_policy"]["mode"] != "none_prohibited" or \
            contract["calibration_stage"]["additional_multiplier_at_export"] != 1.0 or \
            contract["playback_intensity_stage"]["baked_into_samples"]:
        raise ValidationFailure("Contract processing boundary is unsafe")
    data = interleave_pcm16(left, right)
    fmt = struct.pack("<HHIIHH",
        container["format_code"],
        container["channel_count_per_file"],
        contract["sample_rate_hz"],
        container["byte_rate"],
        container["block_alignment_bytes"],
        contract["bit_depth"],
    )
    riff_size = 4 + 8 + len(fmt) + 8 + len(data)
    payload = (
        b"RIFF" + struct.pack("<I", riff_size) + b"WAVE"
        + b"fmt " + struct.pack("<I", len(fmt)) + fmt
        + b"data" + struct.pack("<I", len(data)) + data
    )
    return payload, data


def _safe_output(root: Path, filename: str) -> Path:
    if Path(filename).name != filename or filename in {"", ".", ".."} or \
            not filename.endswith(".wav"):
        raise ValidationFailure("Synthetic WAV filename is unsafe")
    if root.is_symlink():
        raise ValidationFailure("Controlled synthetic output root is invalid")
    root = root.resolve()
    if not root.is_dir():
        raise ValidationFailure("Controlled synthetic output root is invalid")
    target = root / filename
    if target.exists() or target.is_symlink():
        raise ValidationFailure("Synthetic WAV target collision")
    if target.parent.resolve() != root:
        raise ValidationFailure("Synthetic WAV path escapes controlled root")
    return target


class DiagnosticPcm16WavWriter:
    """Contract-specific PCM16 writer; not a generic export abstraction."""

    def __init__(self) -> None:
        service = DiagnosticExportContractService()
        self.contract = service.load()
        service.validate()

    def bytes(self, left: np.ndarray, right: np.ndarray) -> tuple[bytes, bytes]:
        return build_pcm16_wav_bytes(left, right, self.contract)

    def branch_filename(self, branch_number: int) -> str:
        mappings = self.contract["branch_mappings"]
        matches = [
            item for item in mappings if item["source_order"] == branch_number
        ]
        if len(matches) != 1:
            raise ValidationFailure("Unsupported or ambiguous branch number")
        filenames = self.contract["filename_policy"]["resolved_filenames"]
        return filenames[branch_number - 1]

    def write_synthetic(
        self, root: Path, filename: str, left: np.ndarray, right: np.ndarray
    ) -> WavWriteResult:
        target = _safe_output(root, filename)
        payload, data = self.bytes(left, right)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(target, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return WavWriteResult(
            path=target,
            frame_count=len(left),
            data_byte_count=len(data),
            wav_sha256=hashlib.sha256(payload).hexdigest(),
            data_chunk_sha256=hashlib.sha256(data).hexdigest(),
        )
