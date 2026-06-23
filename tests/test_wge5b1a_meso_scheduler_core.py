import inspect
import json
import random
from dataclasses import replace
from pathlib import Path

import pytest

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.meso import (
    MesoPhraseScheduler,
    MesoScheduleRequest,
    load_meso_policy,
    validate_meso_schedule,
)
from wave_generator_engine.meso.policy import SCHEMA_PATH
from wave_generator_engine.profiles.hashing import content_hash, validate_content_hash

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "policies/meso_cluster_rhythm_policy_v1.json"
RUN = ROOT / "runs/latest"
SEEDS = (20260622, 20260623, 20260624)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _request(seed: int = SEEDS[0], *, count: int = 149) -> MesoScheduleRequest:
    return MesoScheduleRequest(
        duration_samples=60 * 48_000,
        sample_rate_hz=48_000,
        root_seed=seed,
        policy_id="x_alpha_meso_cluster_rhythm_policy_v1",
        source_scope="direct_session_1",
        target_packet_count=count,
    )


@pytest.fixture(scope="module")
def policy():
    return load_meso_policy("direct_session_1")


@pytest.fixture(scope="module")
def schedules(policy):
    scheduler = MesoPhraseScheduler()
    return {
        seed: scheduler.schedule(_request(seed), policy=policy)
        for seed in SEEDS
    }


def test_qualified_policy_loads_with_authority_provenance(policy) -> None:
    assert policy.policy_id == "x_alpha_meso_cluster_rhythm_policy_v1"
    assert policy.document["wge5b_meso_cluster_implementation_authorized"]
    assert validate_content_hash(policy.document)
    assert all(
        item["source_artifact"] and item["source_field"]
        for item in policy.parameters.values()
    )


def test_modified_policy_hash_fails_closed(tmp_path: Path) -> None:
    policy = _json(POLICY_PATH)
    policy["phrase_selection_weights"]["weights"]["phrase_active"] = 0.5
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy))
    with pytest.raises(ValidationFailure, match="content hash"):
        load_meso_policy("direct_session_1", path, SCHEMA_PATH)


def test_unresolved_required_policy_field_fails_closed(tmp_path: Path) -> None:
    policy = _json(POLICY_PATH)
    record = next(
        item for item in policy["source_supported_parameters"]
        if item["parameter_id"] == "session_1_within_cluster_interval"
    )
    record["value"] = None
    policy["content_hash"] = content_hash(policy)
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy))
    with pytest.raises(ValidationFailure, match="unresolved"):
        load_meso_policy("direct_session_1", path, SCHEMA_PATH)


def test_unsupported_source_scope_fails_closed() -> None:
    with pytest.raises(ValidationFailure, match="Unsupported meso source scope"):
        load_meso_policy("baseline_sessions_1_4")


@pytest.mark.parametrize("seed", SEEDS)
def test_primary_and_holdouts_validate(seed, policy, schedules) -> None:
    result = schedules[seed]
    validation = validate_meso_schedule(_request(seed), result, policy)
    assert validation["valid"]
    assert result.metrics["packet_count"] == 149
    assert result.metrics["phrase_count"] == 15
    assert 0.298 <= result.metrics["phrase_active_window_share"] <= 0.667
    assert result.metrics["local_phrase_recurrence_present"]


def test_state_model_initiates_continues_terminates_and_has_gaps(schedules) -> None:
    result = schedules[SEEDS[0]]
    assert {"background", "phrase_active"} == set(result.phrase_states)
    assert len(result.phrases) > 1
    for phrase in result.phrases:
        assert phrase.packet_count >= 4
        assert phrase.state_entry in {"session_boundary", "background"}
        assert phrase.state_exit in {"session_boundary", "background"}
        assert all(
            result.packet_phrase_ids[index] == phrase.phrase_id
            for index in range(phrase.first_packet_index, phrase.last_packet_index + 1)
        )
    for left, right in zip(result.phrases, result.phrases[1:]):
        assert right.first_packet_index > left.last_packet_index + 1


@pytest.mark.parametrize("seed", SEEDS)
def test_onsets_count_rate_and_boundaries(seed, schedules) -> None:
    result = schedules[seed]
    assert result.onset_samples[0] == 0
    assert all(
        left < right
        for left, right in zip(result.onset_samples, result.onset_samples[1:])
    )
    assert len(set(result.onset_samples)) == len(result.onset_samples)
    assert result.onset_samples[-1] < 60 * 48_000
    assert result.metrics["final_boundary_margin_samples"] == (60 * 48_000) // 149
    assert result.metrics["packet_rate_hz"] == pytest.approx(149 / 60)


def test_packet_rate_constraint_is_supported(policy) -> None:
    request = MesoScheduleRequest(
        duration_samples=60 * 48_000,
        sample_rate_hz=48_000,
        root_seed=20260622,
        policy_id=policy.policy_id,
        source_scope="direct_session_1",
        target_packet_rate_hz=2.5,
    )
    result = MesoPhraseScheduler().schedule(request, policy=policy)
    assert len(result.onset_samples) == 150
    validate_meso_schedule(request, result, policy)


def test_same_seed_is_byte_identical_and_hash_valid(policy) -> None:
    scheduler = MesoPhraseScheduler()
    first = scheduler.schedule(_request(), policy=policy)
    second = scheduler.schedule(_request(), policy=policy)
    assert first.to_dict() == second.to_dict()
    assert first.content_hash == second.content_hash
    assert validate_content_hash(first.to_dict())


def test_holdout_seeds_differ(schedules) -> None:
    assert len({result.content_hash for result in schedules.values()}) == len(SEEDS)
    assert len({result.onset_samples for result in schedules.values()}) == len(SEEDS)


def test_scheduler_does_not_change_global_random_state(policy) -> None:
    random.seed(991)
    expected = random.random()
    random.seed(991)
    MesoPhraseScheduler().schedule(_request(), policy=policy)
    assert random.random() == expected


@pytest.mark.parametrize("seed", SEEDS)
def test_statistical_and_anti_lattice_metrics(seed, schedules) -> None:
    metrics = schedules[seed].metrics
    assert metrics["unique_interval_count"] > 100
    assert metrics["interval_coefficient_of_variation"] > 0.05
    assert metrics["maximum_identical_interval_run"] <= 2
    assert 0 < metrics["repeated_10ms_interval_cell_prevalence"] <= 1
    assert metrics["schedule_spectrum"]["peak_power_fraction"] < 0.2
    assert any(abs(value) > 0.01 for value in metrics[
        "interval_lag_correlations"
    ].values())
    assert metrics["within_phrase_interval_seconds"]["median"] == pytest.approx(
        0.28191666666666665, abs=0.08
    )
    assert 0.423 <= metrics["between_phrase_gap_seconds"]["median"] <= 4.515


def test_validator_rejects_lattice_and_membership_corruption(policy, schedules) -> None:
    original = schedules[SEEDS[0]]
    fixed_intervals = tuple([24_000] * (len(original.onset_samples) - 1))
    fixed_onsets = tuple(index * 24_000 for index in range(len(original.onset_samples)))
    broken = replace(
        original,
        onset_samples=fixed_onsets,
        inter_packet_intervals=fixed_intervals,
        content_hash="0" * 64,
    )
    with pytest.raises(ValidationFailure):
        validate_meso_schedule(_request(), broken, policy)

    memberships = list(original.packet_phrase_ids)
    memberships[original.phrases[0].first_packet_index + 1] = None
    corrupted_document = original.to_dict()
    corrupted_document["packet_phrase_ids"] = memberships
    corrupted_document["content_hash"] = content_hash(corrupted_document)
    corrupted = replace(
        original,
        packet_phrase_ids=tuple(memberships),
        content_hash=corrupted_document["content_hash"],
    )
    with pytest.raises(ValidationFailure, match="not contiguous"):
        validate_meso_schedule(_request(), corrupted, policy)


def test_core_has_no_planner_source_tuple_motif_render_or_export_dependency() -> None:
    package = ROOT / "src/wave_generator_engine/meso"
    source = "\n".join(path.read_text() for path in package.glob("*.py"))
    prohibited = (
        "BaselinePlanner",
        "PlanningPipeline",
        "FrozenMotifBank",
        "np.load",
        "gain_event_table",
        "rendering.service",
        "export_contract.service",
        "carrier_frequency",
    )
    assert not any(term in source for term in prohibited)
    assert "random.Random(seed)" in inspect.getsource(MesoPhraseScheduler)


def test_protected_plan_and_wav_hashes_remain_unchanged() -> None:
    snapshot = _json(RUN / "diagnostic_export/export_authority_snapshot.json")
    for relative, expected in snapshot["core_plan_hashes"].items():
        assert _json(RUN / relative)["content_hash"] == expected
    expected_wavs = [
        "9c5ed5994f9e4d8ec15dac91851f788508df106185b4816ddc11054ae2170747",
        "28472051eea75634ef0dae74eb3cab7f214b09c47e89e35487f7168113057d9c",
        "4954c3e6ac8e01fed500b85bcdd46e4cb29dc62e336787aed7ce5c9df726d9e4",
        "9b1dbdf3eb955c80bd37203c8ef6d0bfabbeee551ed84e73460143863ec6df61",
    ]
    import hashlib
    actual = [
        hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((RUN / "diagnostic_export/files").glob("*.wav"))
    ]
    assert actual == expected_wavs


def test_scheduler_core_report_is_hashed_and_authorizes_only_integration() -> None:
    report = _json(ROOT / "reports/wge5b1a_meso_scheduler_core_report.json")
    assert validate_content_hash(report)
    assert report["test_results"] == {
        "targeted_test_count": 59,
        "status": "passed",
    }
    assert report["authorization"]["wge5b1b_planner_integration_authorized"]
    assert not report["scheduler_architecture"]["production_planner_integrated"]
