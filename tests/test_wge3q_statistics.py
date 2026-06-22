from wave_generator_engine.qualification.statistics import (
    empirical_band,
    jensen_shannon,
    ks_statistic,
    matrix_correlation,
    wasserstein_distance,
)


def test_identical_distributions_compare_identically() -> None:
    values = [1, 2, 3, 4]
    assert ks_statistic(values, values) == 0
    assert wasserstein_distance(values, values) == 0


def test_divergent_distributions_report_distance() -> None:
    assert ks_statistic([0, 0, 0], [10, 10, 10]) == 1
    assert wasserstein_distance([0, 0], [10, 10]) == 10


def test_categorical_divergence_is_symmetric() -> None:
    first = {"a": 1, "b": 0}
    second = {"a": 0, "b": 1}
    assert jensen_shannon(first, second) == jensen_shannon(second, first) == 1


def test_transition_matrix_correlation() -> None:
    matrix = [[1, 2], [3, 4]]
    assert matrix_correlation(matrix, matrix) == 1
    assert matrix_correlation(matrix, [[4, 3], [2, 1]]) == -1


def test_empirical_bands_are_transparent() -> None:
    source = {"minimum": 0, "p10": 1, "p90": 9, "maximum": 10}
    assert empirical_band(5, source) == "within_source_reference"
    assert empirical_band(0.5, source) == "near_source_reference"
    assert empirical_band(11, source) == "outside_source_reference"
