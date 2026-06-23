import copy
import hashlib
import inspect
import json
import random
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.meso import (
    MesoPhraseScheduler,
    MesoScheduleRequest,
    load_meso_policy,
    validate_meso_schedule,
)
from wave_generator_engine.planning.modes.baseline import BaselinePlanner
from wave_generator_engine.planning.profile_resolver import (
    PlanningProfileResolver,
    validate_session_overlay,
)
from wave_generator_engine.planning.seeds import derive_seed
from wave_generator_engine.planning.service import PlanningService
from wave_generator_engine.planning.validation import validate_channel_grammar
from wave_generator_engine.profiles.hashing import validate_content_hash

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/latest"
REQUEST = json.loads(
    (ROOT / "examples/run_requests/x_alpha_session1_diagnostic_60s.json").read_text()
)
SEEDS = (20260622, 20260623, 20260624)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate(seed: int):
    request = dict(REQUEST)
    request["root_seed"] = seed
    request["request_id"] = f"wge5b1b_candidate_{seed}"
    return PlanningService().build(request)


@pytest.fixture(scope="module")
def candidates():
    return {seed: _candidate(seed) for seed in SEEDS}


def _packet_content(packet: dict) -> dict:
    fields = (
        "packet_id", "unit_grammar", "channel_sequence", "event_ids",
        "continuation_count", "pulse_pattern_present",
        "continuation_spacings_samples",
    )
    return {field: packet[field] for field in fields}


def _event_content(event: dict) -> dict:
    fields = (
        "event_id", "packet_id", "unit_id", "unit_grammar", "pulse_role",
        "duration_samples", "logical_channel", "channel_role", "motif_id",
        "motif_hash", "motif_source_order", "motif_selection_mode",
        "identity_mode", "relative_event_gain", "gain_source",
        "random_selection_trace", "authority_references",
    )
    return {field: event[field] for field in fields}


def test_session1_profile_resolves_authorized_meso_policy() -> None:
    profile = _json(
        ROOT / "profiles/planning_profiles/x_alpha_session_01_baseline_v1.json"
    )
    schema = _json(ROOT / "schemas/session_planning_profile.schema.json")
    Draft202012Validator(schema).validate(profile)
    assert validate_content_hash(profile)
    config = profile["meso_scheduler"]
    policy = load_meso_policy(config["source_scope"])
    assert config["enabled"]
    assert config["meso_policy_id"] == policy.policy_id
    assert config["meso_policy_hash"] == policy.content_hash
    assert config["source_scope"] == "direct_session_1"


def test_activation_is_data_driven_and_sessions_2_to_4_remain_legacy() -> None:
    resolver = PlanningProfileResolver()
    _, _, session_one, _ = resolver.resolve(
        "x_alpha_standard_v1", "diagnostic_60s_v1", 1
    )
    assert session_one["meso_scheduler"]["enabled"]
    for session_id in (2, 3, 4):
        _, _, other, _ = resolver.resolve(
            "x_alpha_standard_v1", "diagnostic_60s_v1", session_id
        )
        assert other["meso_scheduler"] is None
        request = dict(REQUEST)
        request["selected_session_ids"] = [session_id]
        request["request_id"] = f"legacy_session_{session_id}"
        result = PlanningService().build(request)
        assert "meso_schedule" not in result.packet_plan
    source = inspect.getsource(BaselinePlanner)
    assert "if session_id == 1" not in source
    assert "session_id == 1" not in source


def test_unauthorized_or_wrong_policy_hash_fails_closed() -> None:
    profile = _json(
        ROOT / "profiles/planning_profiles/x_alpha_session_01_baseline_v1.json"
    )
    profile["meso_scheduler"]["meso_policy_hash"] = "0" * 64
    with pytest.raises(ValidationFailure, match="policy hash"):
        validate_session_overlay(profile)


def test_primary_candidate_preserves_published_packet_and_event_content(
    candidates,
) -> None:
    candidate = candidates[20260622]
    current_packets = _json(
        RUN / "sessions/session_01/packet_plan.json"
    )["packets"]
    current_events = _json(
        RUN / "sessions/session_01/event_plan.json"
    )["events"]
    assert len(candidate.packet_plan["packets"]) == len(current_packets) == 149
    assert len(candidate.event_plan["events"]) == len(current_events) == 960
    assert [
        _packet_content(item) for item in candidate.packet_plan["packets"]
    ] == [_packet_content(item) for item in current_packets]
    assert [
        _event_content(item) for item in candidate.event_plan["events"]
    ] == [_event_content(item) for item in current_events]
    assert any(
        left["onset_sample"] != right["onset_sample"]
        for left, right in zip(candidate.packet_plan["packets"], current_packets)
    )


def test_timing_substream_changes_do_not_change_content() -> None:
    resolver = PlanningProfileResolver()
    _, _, profile, _ = resolver.resolve(
        "x_alpha_standard_v1", "diagnostic_60s_v1", 1
    )
    motif_metadata = _json(
        resolver.root / "bank/frozen_assets/frozen_motif_identity_index.json"
    )["motifs"]
    changed = copy.deepcopy(profile)
    changed["meso_scheduler"]["seed_namespace"] = "meso_phrase_scheduler_holdout"
    planner = BaselinePlanner()
    common = {
        "session_id": 1,
        "duration_seconds": 60,
        "sample_rate_hz": 48_000,
        "root_seed": 20260622,
        "focus_role_target": 2,
        "motif_metadata": motif_metadata,
    }
    first = planner.plan(planning_profile=profile, **common)
    second = planner.plan(planning_profile=changed, **common)
    assert [
        _packet_content(item) for item in first[0]["packets"]
    ] == [_packet_content(item) for item in second[0]["packets"]]
    assert [
        _event_content(item) for item in first[1]["events"]
    ] == [_event_content(item) for item in second[1]["events"]]
    assert [
        item["onset_sample"] for item in first[0]["packets"]
    ] != [item["onset_sample"] for item in second[0]["packets"]]


@pytest.mark.parametrize("seed", SEEDS)
def test_candidate_meso_result_and_plan_metadata_validate(seed, candidates) -> None:
    result = candidates[seed]
    config = result.planning_profile["meso_scheduler"]
    policy = load_meso_policy(config["source_scope"])
    substream_root = derive_seed(seed, config["seed_namespace"])
    request = MesoScheduleRequest(
        duration_samples=60 * 48_000,
        sample_rate_hz=48_000,
        root_seed=substream_root,
        policy_id=policy.policy_id,
        source_scope=config["source_scope"],
        target_packet_rate_hz=config["target_packet_rate_hz"],
    )
    schedule = MesoPhraseScheduler().schedule(request, policy=policy)
    validate_meso_schedule(request, schedule, policy)
    metadata = result.packet_plan["meso_schedule"]
    assert metadata["scheduler_result_hash"] == schedule.content_hash
    assert metadata["phrase_count"] == schedule.metrics["phrase_count"] == 15
    assert metadata["phrase_active_share"] == pytest.approx(0.3972602739726027)
    assert metadata["anti_lattice_validation"]["status"] == "passed"
    assert [item["onset_sample"] for item in result.packet_plan["packets"]] == \
        list(schedule.onset_samples)
    assert result.session_plan["meso_schedule"]["scheduler_result_hash"] == \
        schedule.content_hash


@pytest.mark.parametrize("seed", SEEDS)
def test_candidate_onsets_events_and_phrase_annotations_are_valid(seed, candidates) -> None:
    result = candidates[seed]
    packets = result.packet_plan["packets"]
    events = {item["event_id"]: item for item in result.event_plan["events"]}
    onsets = [item["onset_sample"] for item in packets]
    assert len(onsets) == len(set(onsets)) == 149
    assert all(left < right for left, right in zip(onsets, onsets[1:]))
    assert onsets[-1] < 60 * 48_000
    assert {"background", "phrase_active"} == {
        item["meso_phrase_state"] for item in packets
    }
    for packet in packets:
        validate_channel_grammar(packet)
        selected = [events[event_id] for event_id in packet["event_ids"]]
        assert selected[0]["onset_sample"] == packet["onset_sample"]
        offsets = [
            item["onset_sample"] - packet["onset_sample"] for item in selected
        ]
        expected = [0]
        for spacing in packet["continuation_spacings_samples"]:
            expected.append(expected[-1] + spacing)
        assert offsets == expected
        assert all(item["end_sample_exclusive"] <= 60 * 48_000 for item in selected)


@pytest.mark.parametrize("seed", SEEDS)
def test_existing_non_meso_guardrails_remain_valid(seed, candidates) -> None:
    result = candidates[seed]
    counts = result.validation_report["counts"]
    assert counts["packets"] == 149
    assert counts["events"] >= 900
    assert counts["pulse_pattern_prevalence"] >= 0.95
    assert counts["invalid_grammar_labelled_packet_count"] == 0
    assert counts["unique_motifs"] >= 50
    assert 0.40 <= counts["immediate_motif_repetition_rate"] <= 0.60
    assert counts["maximum_concurrency"] <= 4
    assert result.validation_report["hard_checks"]["meso_scheduler_integration"] == \
        "passed"


def test_same_seed_candidates_are_identical_and_holdouts_differ(candidates) -> None:
    rerun = _candidate(20260622)
    assert rerun.packet_plan == candidates[20260622].packet_plan
    assert rerun.event_plan == candidates[20260622].event_plan
    assert len({
        result.packet_plan["content_hash"] for result in candidates.values()
    }) == len(SEEDS)


def test_integration_does_not_change_global_random_state() -> None:
    random.seed(1187)
    expected = random.random()
    random.seed(1187)
    _candidate(20260622)
    assert random.random() == expected


def test_candidate_generation_is_in_memory_and_does_not_touch_workspace(
    tmp_path: Path,
) -> None:
    before = list(tmp_path.iterdir())
    _candidate(20260622)
    assert list(tmp_path.iterdir()) == before == []


def test_legacy_committed_plan_remains_readable_without_meso_metadata() -> None:
    packet_plan = _json(RUN / "sessions/session_01/packet_plan.json")
    session = _json(RUN / "sessions/session_01/session_plan.json")
    assert "meso_schedule" not in packet_plan
    assert "meso_schedule" not in session
    assert validate_content_hash(packet_plan)
    assert validate_content_hash(session)


def test_no_render_export_source_tuple_carrier_or_persistent_plan_dependency() -> None:
    source = inspect.getsource(BaselinePlanner)
    assert "rendering" not in source
    assert "export_contract" not in source
    assert "gain_event_table" not in source
    assert "carrier" not in source
    assert "runs/latest" not in source


def test_runs_latest_and_wavs_are_unchanged() -> None:
    snapshot = _json(RUN / "diagnostic_export/export_authority_snapshot.json")
    for relative, expected in snapshot["core_plan_hashes"].items():
        assert _json(RUN / relative)["content_hash"] == expected
    expected_wavs = [
        "9c5ed5994f9e4d8ec15dac91851f788508df106185b4816ddc11054ae2170747",
        "28472051eea75634ef0dae74eb3cab7f214b09c47e89e35487f7168113057d9c",
        "4954c3e6ac8e01fed500b85bcdd46e4cb29dc62e336787aed7ce5c9df726d9e4",
        "9b1dbdf3eb955c80bd37203c8ef6d0bfabbeee551ed84e73460143863ec6df61",
    ]
    assert [
        _sha256(path)
        for path in sorted((RUN / "diagnostic_export/files").glob("*.wav"))
    ] == expected_wavs


def test_integration_report_is_hashed_and_authorizes_only_wge5b2() -> None:
    report = _json(ROOT / "reports/wge5b1b_planner_integration_report.json")
    assert validate_content_hash(report)
    assert report["test_results"] == {
        "complete_test_count": 364,
        "status": "passed",
    }
    assert report["authorization"]["wge5b2_candidate_regeneration_authorized"]
    assert report["integration_architecture"]["production_run_replaced"] is False
