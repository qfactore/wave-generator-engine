import numpy as np
import pytest

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.motifs.metrics import inspect_samples, summarize_corpus


def test_known_synthetic_metrics_are_correct() -> None:
    samples = np.array([-1.0, 0.0, 1.0, -1.0], dtype=np.float32)
    before = samples.copy()
    metrics = inspect_samples(samples, 4)
    assert metrics["sample_count"] == 4
    assert metrics["duration_seconds"] == 1.0
    assert metrics["minimum"] == -1.0 and metrics["maximum"] == 1.0
    assert metrics["sample_peak"] == 1.0
    assert np.isclose(metrics["rms"], np.sqrt(0.75))
    assert metrics["mean"] == -0.25
    assert metrics["zero_crossing_count"] == 2
    assert np.array_equal(samples, before)


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_non_finite_metrics_fail(value: float) -> None:
    with pytest.raises(ValidationFailure, match="finite"):
        inspect_samples(np.array([0.0, value]), 48000)


def test_real_corpus_summary_contains_84(real_motif_bank) -> None:
    summary = summarize_corpus(real_motif_bank.records())
    assert summary["motif_count"] == 84
    assert summary["identity_verification"] == "all_matched"
    assert set(summary["dtype_distribution"]) == {"float32", "float64"}
    assert summary["authority_claim"] is False
