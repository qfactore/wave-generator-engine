import math
from collections.abc import Iterable

import numpy as np


def summary(values: Iterable[float]) -> dict:
    data = np.asarray(list(values), dtype=float)
    if data.size == 0:
        return {"count": 0}
    return {
        "count": int(data.size),
        "minimum": float(data.min()),
        "p10": float(np.quantile(data, 0.1)),
        "median": float(np.median(data)),
        "mean": float(data.mean()),
        "p90": float(np.quantile(data, 0.9)),
        "maximum": float(data.max()),
        "variance": float(data.var()),
        "coefficient_of_variation": (
            float(data.std() / data.mean()) if data.mean() else 0.0
        ),
    }


def ks_statistic(first: Iterable[float], second: Iterable[float]) -> float:
    left = np.sort(np.asarray(list(first), dtype=float))
    right = np.sort(np.asarray(list(second), dtype=float))
    if not left.size or not right.size:
        return 0.0
    points = np.sort(np.unique(np.concatenate((left, right))))
    return float(max(
        abs(np.searchsorted(left, point, side="right") / left.size
            - np.searchsorted(right, point, side="right") / right.size)
        for point in points
    ))


def wasserstein_distance(first: Iterable[float], second: Iterable[float]) -> float:
    left = np.sort(np.asarray(list(first), dtype=float))
    right = np.sort(np.asarray(list(second), dtype=float))
    if not left.size or not right.size:
        return 0.0
    quantiles = np.linspace(0, 1, max(left.size, right.size))
    return float(np.mean(np.abs(
        np.quantile(left, quantiles) - np.quantile(right, quantiles)
    )))


def jensen_shannon(first: dict[str, float], second: dict[str, float]) -> float:
    keys = sorted(set(first) | set(second))
    left = np.asarray([first.get(key, 0.0) for key in keys], dtype=float)
    right = np.asarray([second.get(key, 0.0) for key in keys], dtype=float)
    left = left / left.sum() if left.sum() else left
    right = right / right.sum() if right.sum() else right
    middle = (left + right) / 2

    def divergence(values):
        return sum(
            value * math.log2(value / mean)
            for value, mean in zip(values, middle) if value and mean
        )

    return float((divergence(left) + divergence(right)) / 2)


def matrix_correlation(first: Iterable[Iterable[float]], second: Iterable[Iterable[float]]) -> float:
    left = np.asarray(list(first), dtype=float).ravel()
    right = np.asarray(list(second), dtype=float).ravel()
    if left.size != right.size or left.size < 2 or not left.std() or not right.std():
        return 0.0
    return float(np.corrcoef(left, right)[0, 1])


def empirical_band(value: float, source: dict) -> str:
    if source.get("p10") is not None and source["p10"] <= value <= source["p90"]:
        return "within_source_reference"
    if source.get("minimum") is not None and source["minimum"] <= value <= source["maximum"]:
        return "near_source_reference"
    return "outside_source_reference"
