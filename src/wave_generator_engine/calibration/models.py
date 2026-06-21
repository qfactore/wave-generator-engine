from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationPolicy:
    artifact_id: str
    reference_multiplier: float
    default_playback_intensity: float
    playback_intensity_stage: str
    per_motif_normalization: bool
    per_session_normalization: bool
    default_limiter: bool
    preserve_relative_amplitude_relationships: bool
    invalid_headroom_policy: str
    internal_intermediate: str
    true_peak_ceiling_dbfs: float
    reserve_db: float
    delivery_24_bit_status: str
