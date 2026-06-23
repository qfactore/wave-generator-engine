import math
from collections import Counter
from typing import Iterable

import numpy as np

from wave_generator_engine.qualification.statistics import summary


def lag_correlation(values: list[int], lag: int) -> float:
    if len(values) <= lag:
        return 0.0
    left = np.asarray(values[:-lag], dtype=float)
    right = np.asarray(values[lag:], dtype=float)
    if not left.std() or not right.std():
        return 0.0
    return float(np.corrcoef(left, right)[0, 1])


def repeated_cell_prevalence(
    intervals: Iterable[int], sample_rate_hz: int, cell_seconds: float = 0.01
) -> float:
    width = max(1, round(sample_rate_hz * cell_seconds))
    cells = [round(value / width) for value in intervals]
    counts = Counter(cells)
    return (
        sum(1 for cell in cells if counts[cell] > 1) / len(cells)
        if cells else 0.0
    )


def maximum_identical_run(values: Iterable[int]) -> int:
    maximum = current = 0
    previous = None
    for value in values:
        current = current + 1 if value == previous else 1
        maximum = max(maximum, current)
        previous = value
    return maximum


def dominant_schedule_spectrum(
    onsets: Iterable[int], duration_samples: int, sample_rate_hz: int
) -> dict[str, float]:
    duration = duration_samples / sample_rate_hz
    bin_width = 0.01
    bins = np.arange(0, duration + bin_width, bin_width)
    seconds = np.asarray(list(onsets), dtype=float) / sample_rate_hz
    counts, _ = np.histogram(seconds, bins=bins)
    centered = counts - counts.mean()
    power = np.abs(np.fft.rfft(centered)) ** 2
    frequencies = np.fft.rfftfreq(centered.size, d=bin_width)
    selected = np.flatnonzero((frequencies >= 0.1) & (frequencies <= 10.0))
    if not selected.size or not power[selected].sum():
        return {"dominant_frequency_hz": 0.0, "peak_power_fraction": 0.0}
    index = selected[np.argmax(power[selected])]
    return {
        "dominant_frequency_hz": float(frequencies[index]),
        "peak_power_fraction": float(power[index] / power[selected].sum()),
    }


def schedule_metrics(
    *,
    onsets: list[int],
    phrase_sizes: list[int],
    phrase_durations: list[int],
    within_intervals: list[int],
    between_gaps: list[int],
    sample_rate_hz: int,
    duration_samples: int,
) -> dict:
    intervals = [right - left for left, right in zip(onsets, onsets[1:])]
    active_windows = sum(max(0, size - 3) for size in phrase_sizes)
    window_count = max(1, len(onsets) - 3)
    metrics = {
        "packet_count": len(onsets),
        "packet_rate_hz": len(onsets) / (duration_samples / sample_rate_hz),
        "phrase_count": len(phrase_sizes),
        "phrases_per_minute": len(phrase_sizes) / (duration_samples / sample_rate_hz) * 60,
        "phrase_active_window_share": active_windows / window_count,
        "phrase_size_packets": summary(phrase_sizes),
        "phrase_duration_seconds": summary(
            value / sample_rate_hz for value in phrase_durations
        ),
        "within_phrase_interval_seconds": summary(
            value / sample_rate_hz for value in within_intervals
        ),
        "between_phrase_gap_seconds": summary(
            value / sample_rate_hz for value in between_gaps
        ),
        "all_interval_seconds": summary(
            value / sample_rate_hz for value in intervals
        ),
        "unique_interval_count": len(set(intervals)),
        "interval_lag_correlations": {
            f"lag_{lag}": lag_correlation(intervals, lag) for lag in range(1, 5)
        },
        "repeated_10ms_interval_cell_prevalence": repeated_cell_prevalence(
            intervals, sample_rate_hz
        ),
        "maximum_identical_interval_run": maximum_identical_run(intervals),
        "schedule_spectrum": dominant_schedule_spectrum(
            onsets, duration_samples, sample_rate_hz
        ),
        "final_boundary_margin_samples": duration_samples - onsets[-1],
    }
    metrics["interval_coefficient_of_variation"] = metrics[
        "all_interval_seconds"
    ]["coefficient_of_variation"]
    metrics["local_phrase_recurrence_present"] = (
        metrics["repeated_10ms_interval_cell_prevalence"] > 0
        and any(
            not math.isclose(value, 0.0, abs_tol=1e-12)
            for value in metrics["interval_lag_correlations"].values()
        )
    )
    return metrics
