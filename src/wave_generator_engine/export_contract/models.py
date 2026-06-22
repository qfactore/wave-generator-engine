from typing import TypedDict


class DiagnosticWavFileRecord(TypedDict):
    branch_number: int
    left_logical_channel: int
    right_logical_channel: int
    filename: str
    sample_rate_hz: int
    frame_count: int
    encoding: str
    bit_depth: int
    wav_sha256: str
    data_chunk_sha256: str
    readback_status: str
    maximum_quantization_error: float


class DiagnosticExportManifest(TypedDict):
    schema_version: str
    contract_id: str
    contract_hash: str
    source_render_receipt_hash: str
    source_bus_hashes: dict[str, str]
    files: list[DiagnosticWavFileRecord]
    calibration_already_applied: bool
    export_calibration_multiplier: float
    playback_intensity_applied: bool
    content_hash: str


class DiagnosticReadbackResult(TypedDict):
    schema_version: str
    valid: bool
    frame_count: int
    wav_sha256: str
    data_chunk_sha256: str
    maximum_quantization_error: float
    content_hash: str
