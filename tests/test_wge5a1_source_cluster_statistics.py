import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from wave_generator_engine.profiles.hashing import validate_content_hash
from wave_generator_engine.qualification.authority import QualificationAuthority

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "reports/wge5a1_source_cluster_statistics.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_root() -> Path:
    report = QualificationAuthority().direct(
        "phase5l_unit_grammar_audit_report",
        "training/validation event metadata",
        "direct_session_1_and_baseline_sessions_1_4",
    )
    return report.path.parents[2]


def _packet_starts(path: Path, sessions: set[int]) -> dict[str, list[int]]:
    blocks: dict[str, list[int]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if int(row["session"]) in sessions and row["packet_position"] == "packet_start":
                blocks[row["source_block"]].append(int(row["event_start_sample"]))
    return {block: sorted(starts) for block, starts in sorted(blocks.items())}


def _triples(blocks: dict[str, list[int]]) -> list[tuple[int, int, int]]:
    values: list[tuple[int, int, int]] = []
    for starts in blocks.values():
        intervals = [right - left for left, right in zip(starts, starts[1:])]
        values.extend(
            tuple(intervals[index:index + 3])
            for index in range(max(0, len(intervals) - 2))
        )
    return values


def _active_cluster_count(
    validation: dict[str, list[int]], reference: set[tuple[int, int, int]]
) -> int:
    count = 0
    for starts in validation.values():
        intervals = [right - left for left, right in zip(starts, starts[1:])]
        active = [
            index for index in range(max(0, len(intervals) - 2))
            if tuple(intervals[index:index + 3]) in reference
        ]
        if not active:
            continue
        count += 1
        current_end = active[0] + 3
        for index in active[1:]:
            if index <= current_end + 1:
                current_end = max(current_end, index + 3)
            else:
                count += 1
                current_end = index + 3
    return count


def test_source_tables_are_permitted_hash_verified_and_training_validation_only() -> None:
    report = _json(REPORT_PATH)
    source_root = _source_root()
    for record in report["authority"]["source_files"]:
        path = source_root / record["relative_path"]
        assert path.is_file()
        assert record["classification"] == "audit-only"
        assert _sha256(path) == record["sha256"]
        assert "final_test" not in path.name
    assert report["authority"]["blocked_final_test_accessed"] is False


def test_source_packet_counts_and_phrase_state_analysis_reproduce() -> None:
    report = _json(REPORT_PATH)
    source_root = _source_root()
    training_path = source_root / report["authority"]["source_files"][0]["relative_path"]
    validation_path = source_root / report["authority"]["source_files"][1]["relative_path"]

    for sessions, population_key, expected_matches, expected_clusters in (
        ({1}, "direct_session_1", 130, 24),
        ({1, 2, 3, 4}, "baseline_sessions_1_4", 1724, 97),
    ):
        training = _packet_starts(training_path, sessions)
        validation = _packet_starts(validation_path, sessions)
        expected = report["populations"][population_key]
        assert sum(map(len, training.values())) == expected["training_count"]
        assert sum(map(len, validation.values())) == expected["validation_count"]
        assert len(training) + len(validation) == expected["source_block_count"]

        reference = set(_triples(training))
        validation_triples = _triples(validation)
        assert sum(item in reference for item in validation_triples) == expected_matches
        assert _active_cluster_count(validation, reference) == expected_clusters


def test_state_model_is_deterministic_and_not_a_fixed_gap_threshold() -> None:
    report = _json(REPORT_PATH)
    boundary = report["cluster_boundary_analysis"]
    assert boundary["fixed_threshold_verdict"] == "not_supported"
    assert boundary["selected_model"] == "probabilistic_recurrent_interval_phrase_state"
    assert report["packet_start_semantics"]["prohibited_threshold_samples"] == 12376
    assert "may not" in boundary["runtime_boundary"]


def test_reports_and_policy_authorize_only_future_non_executable_wge5b() -> None:
    report = _json(REPORT_PATH)
    policy = _json(ROOT / "policies/meso_cluster_rhythm_policy_v1.json")
    audit = _json(ROOT / "reports/wge5a_meso_cluster_rhythm_audit.json")
    assert validate_content_hash(report)
    assert report["authorization"]["wge5b_meso_cluster_implementation_authorized"]
    assert policy["wge5b_meso_cluster_implementation_authorized"]
    assert policy["executable"] is False
    assert audit["authorization"]["wge5b_meso_cluster_implementation_authorized"]
    assert report["generated_plan_comparison"]["overall"] == "outside_source_reference"


def test_source_and_generated_populations_remain_separate() -> None:
    report = _json(REPORT_PATH)
    assert report["populations"]["direct_session_1"]["packet_start_count"] == 752
    assert report["populations"]["baseline_sessions_1_4"]["packet_start_count"] == 6112
    assert report["populations"]["generated_session_1"]["packet_start_count"] == 149
    assert report["generated_plan_comparison"]["cluster_count"] == 0
    assert report["rhythmic_phrase_findings"]["interpretation"]["continuous_component"] == \
        "unsupported"
