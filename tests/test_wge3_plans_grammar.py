import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.planning.service import PlanningService
from wave_generator_engine.planning.validation import validate_channel_grammar
from wave_generator_engine.profiles.hashing import validate_content_hash

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def result():
    request = json.loads(
        (ROOT / "examples/run_requests/x_alpha_session1_diagnostic_60s.json").read_text()
    )
    return PlanningService().build(request)


def test_all_core_plan_schemas_and_hashes_validate(result) -> None:
    documents = {
        "planning_profile_snapshot.schema.json": result.planning_profile,
        "session_pack_plan.schema.json": result.session_pack_plan,
        "session_plan.schema.json": result.session_plan,
        "macro_state_plan.schema.json": result.macro_state_plan,
        "packet_plan.schema.json": result.packet_plan,
        "event_plan.schema.json": result.event_plan,
        "plan_validation_report.schema.json": result.validation_report,
        "pulse_pattern_plan.schema.json": result.packet_plan["pulse_pattern_plan"],
        "channel_unit_plan.schema.json": result.packet_plan["channel_unit_plan"],
    }
    for schema_name, document in documents.items():
        schema = json.loads((ROOT / "schemas" / schema_name).read_text())
        Draft202012Validator(schema).validate(document)
        assert validate_content_hash(document)


def test_event_plan_is_metadata_only_and_in_bounds(result) -> None:
    events = result.event_plan["events"]
    assert events
    assert not result.event_plan["contains_waveform_samples"]
    assert not result.event_plan["calibration_applied"]
    assert not result.event_plan["playback_intensity_applied"]
    for event in events:
        assert isinstance(event["onset_sample"], int)
        assert isinstance(event["duration_samples"], int)
        assert 0 <= event["onset_sample"] < event["end_sample_exclusive"] <= 2880000
        assert event["logical_channel"] in range(8)
        assert event["identity_mode"] == "exact_frozen_identity"
        assert event["relative_event_gain"] == 1.0
        assert not {"samples", "waveform", "calibration_multiplier", "playback_intensity"} & set(event)


def test_motif_identity_and_source_guided_repetition_are_preserved(result) -> None:
    index = json.loads(
        (ROOT.parent / "wave-gen-interchange/bank/frozen_assets/frozen_motif_identity_index.json").read_text()
    )
    motifs = {item["motif_id"]: item["per_motif_sha256"] for item in index["motifs"]}
    ids = []
    for event in result.event_plan["events"]:
        assert motifs[event["motif_id"]] == event["motif_hash"]
        ids.append(event["motif_id"])
    repetition = sum(first == second for first, second in zip(ids, ids[1:]))
    assert repetition > 0
    assert len(set(ids)) >= 12


def test_pulse_pattern_grouping_and_not_forced(result) -> None:
    packets = result.packet_plan["packets"]
    assert any(item["continuation_count"] == 0 for item in packets)
    assert any(item["continuation_count"] > 0 for item in packets)
    by_id = {item["event_id"]: item for item in result.event_plan["events"]}
    for packet in packets:
        roles = [by_id[item]["pulse_role"] for item in packet["event_ids"]]
        assert roles[0] == "packet_start"
        assert all(role == "packet_continuation" for role in roles[1:])


def test_all_generated_channel_grammar_is_structurally_valid(result) -> None:
    for packet in result.packet_plan["packets"]:
        validate_channel_grammar(packet)


def test_invalid_channel_grammar_fails() -> None:
    with pytest.raises(ValidationFailure):
        validate_channel_grammar({
            "unit_grammar": "clean_plus_one_sweep",
            "channel_sequence": [0, 2, 3],
        })


def test_plan_is_not_render_executable(result) -> None:
    assert result.session_pack_plan["executable_for_rendering"] is False
    assert result.session_plan["headroom_status"] == \
        "not_certified_without_waveform_render_and_overlap_sum"
