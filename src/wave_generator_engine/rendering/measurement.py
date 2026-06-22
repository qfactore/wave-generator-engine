import hashlib
import json
import math
from typing import Any

import numpy as np

PCM16_FULL_SCALE = 32768.0


def dbfs(value: float) -> float:
    return float("-inf") if value <= 0 else float(20.0 * math.log10(value))


def estimate_true_peak(values: np.ndarray, oversample: int = 8) -> float:
    """Faithful port of the permitted eight-phase windowed-sinc estimator."""
    if values.dtype != np.float64 or values.ndim != 1:
        raise ValueError("True-peak input must be one-dimensional float64")
    if not np.all(np.isfinite(values)):
        raise ValueError("True-peak input contains non-finite samples")
    if not len(values):
        return 0.0
    absolute = np.abs(values)
    candidate_count = min(64, len(values))
    candidates = np.argpartition(absolute, -candidate_count)[-candidate_count:]
    peak = float(np.max(absolute))
    radius = 16
    fractions = np.arange(oversample, dtype=np.float64) / oversample
    for center in candidates:
        start = max(0, int(center) - radius)
        end = min(len(values), int(center) + radius + 1)
        samples = values[start:end]
        positions = np.arange(start, end, dtype=np.float64)
        for offset in (-1, 0):
            times = int(center) + offset + fractions
            distance = times[:, None] - positions[None, :]
            window = np.where(
                np.abs(distance) <= radius,
                0.5 + 0.5 * np.cos(np.pi * distance / radius),
                0.0,
            )
            interpolation = (np.sinc(distance) * window) @ samples
            peak = max(peak, float(np.max(np.abs(interpolation))))
    return peak


def canonical_array_hash(channel: int, values: np.ndarray) -> str:
    canonical = np.ascontiguousarray(values, dtype="<f8")
    header = json.dumps({
        "channel": channel,
        "dtype": "float64-le",
        "shape": list(canonical.shape),
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(len(header).to_bytes(8, "big"))
    digest.update(header)
    digest.update(canonical.tobytes(order="C"))
    return digest.hexdigest()


def channel_metrics(
    channel: int, values_native: np.ndarray, occupancy: np.ndarray,
    event_count: int,
) -> dict[str, Any]:
    normalized = np.asarray(values_native, dtype=np.float64) / PCM16_FULL_SCALE
    finite = np.isfinite(normalized)
    non_finite = int(normalized.size - np.count_nonzero(finite))
    if non_finite:
        sample_peak = true_peak = rms = dc = float("nan")
        sample_index = -1
    else:
        absolute = np.abs(normalized)
        sample_index = int(np.argmax(absolute)) if len(absolute) else -1
        sample_peak = float(absolute[sample_index]) if len(absolute) else 0.0
        true_peak = estimate_true_peak(normalized)
        rms = float(np.sqrt(np.mean(normalized ** 2))) if len(normalized) else 0.0
        dc = float(np.mean(normalized)) if len(normalized) else 0.0
    active = int(np.count_nonzero(occupancy))
    overlap = int(np.count_nonzero(occupancy > 1))
    return {
        "logical_channel": channel,
        "sample_peak_linear": sample_peak,
        "sample_peak_dbfs": dbfs(sample_peak),
        "sample_peak_index": sample_index,
        "estimated_true_peak_linear": true_peak,
        "estimated_true_peak_dbfs": dbfs(true_peak),
        "rms": rms,
        "crest_factor": float(sample_peak / rms) if rms > 0 else 0.0,
        "dc_offset": dc,
        "non_finite_sample_count": non_finite,
        "samples_greater_than_or_equal_positive_full_scale":
            int(np.count_nonzero(normalized >= 1.0)),
        "samples_less_than_or_equal_negative_full_scale":
            int(np.count_nonzero(normalized <= -1.0)),
        "clipped_full_scale_sample_count":
            int(np.count_nonzero(np.abs(normalized) >= 1.0)),
        "active_sample_count": active,
        "active_fraction": float(active / len(values_native)),
        "event_count": event_count,
        "maximum_same_channel_concurrency": int(np.max(occupancy)),
        "overlap_sample_count": overlap,
        "overlap_fraction": float(overlap / len(values_native)),
    }


def true_peak_method_record(source_hash: str) -> dict[str, Any]:
    return {
        "method_id": "x_alpha_eight_phase_windowed_sinc_v1",
        "source_artifact": "x_alpha_closure:methods/measurement_methods.md",
        "source_implementation": "x_alpha_closure:scripts/run_x_alpha_closure.py",
        "source_hash": source_hash,
        "candidate_peak_count": 64,
        "candidate_selection": "largest_absolute_sample_peaks_argpartition",
        "interpolation_kernel": "numpy_normalized_sinc",
        "window": "raised_cosine_0.5_plus_0.5_cos_pi_distance_over_radius",
        "support_radius_samples": 16,
        "phase_count": 8,
        "phase_positions": [index / 8 for index in range(8)],
        "center_offsets": [-1, 0],
        "boundary_handling": "clip_support_to_available_samples",
        "duplicate_window_handling": "evaluate_all_candidates_and_take_global_maximum",
        "input_dtype": "float64",
    }
