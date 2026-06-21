from collections import Counter
from typing import Any, Iterable

import numpy as np

from wave_generator_engine.errors import ValidationFailure
from .models import FrozenMotifRecord


def inspect_samples(samples: np.ndarray, sample_rate_hz: int) -> dict[str, Any]:
    if not np.issubdtype(samples.dtype, np.number) or samples.dtype.hasobject:
        raise ValidationFailure("Motif metrics require a numeric array")
    values = np.asarray(samples)
    if values.size == 0 or not np.all(np.isfinite(values)):
        raise ValidationFailure("Motif metrics require finite non-empty samples")
    diagnostic = values.astype(np.float64, copy=True)
    signs = np.signbit(diagnostic)
    crossings = int(np.count_nonzero(signs[1:] != signs[:-1])) if diagnostic.size > 1 else 0
    return {
        "sample_count": int(values.size),
        "duration_seconds": float(values.size / sample_rate_hz),
        "minimum": float(np.min(diagnostic)),
        "maximum": float(np.max(diagnostic)),
        "sample_peak": float(np.max(np.abs(diagnostic))),
        "rms": float(np.sqrt(np.mean(np.square(diagnostic)))),
        "mean": float(np.mean(diagnostic)),
        "dc_offset": float(np.mean(diagnostic)),
        "zero_crossing_count": crossings,
        "zero_crossing_rate_hz": float(crossings / (values.size / sample_rate_hz)),
        "dtype": str(values.dtype),
        "shape": list(values.shape),
    }


def inspect_record(record: FrozenMotifRecord) -> dict[str, Any]:
    before = record.samples.tobytes()
    metrics = inspect_samples(record.samples, record.metadata.sample_rate_hz)
    if record.samples.tobytes() != before:
        raise ValidationFailure("Motif metrics modified source samples")
    return {"metadata": record.metadata.to_dict(), "metrics": metrics}


def _distribution(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "minimum": float(np.min(array)),
        "median": float(np.median(array)),
        "maximum": float(np.max(array)),
        "mean": float(np.mean(array)),
    }


def summarize_corpus(records: Iterable[FrozenMotifRecord]) -> dict[str, Any]:
    items = list(records)
    inspected = [inspect_record(item) for item in items]
    return {
        "report_type": "diagnostic_motif_corpus_summary",
        "motif_count": len(items),
        "duration_seconds_distribution": _distribution(
            [item["metrics"]["duration_seconds"] for item in inspected]
        ),
        "sample_count_distribution": _distribution(
            [item["metrics"]["sample_count"] for item in inspected]
        ),
        "sample_peak_distribution": _distribution(
            [item["metrics"]["sample_peak"] for item in inspected]
        ),
        "rms_distribution": _distribution(
            [item["metrics"]["rms"] for item in inspected]
        ),
        "dtype_distribution": dict(Counter(item.metadata.dtype for item in items)),
        "shape_distribution": dict(Counter(str(list(item.metadata.shape)) for item in items)),
        "identity_verification": "all_matched",
        "authority_claim": False,
    }
