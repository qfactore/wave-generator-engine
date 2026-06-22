import copy
import json
from collections import Counter
from pathlib import Path

import pytest

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.planning.service import PlanningService

ROOT = Path(__file__).resolve().parents[1]


def base_request() -> dict:
    return json.loads(
        (ROOT / "examples/run_requests/x_alpha_session1_diagnostic_60s.json").read_text()
    )


def test_focus_target_is_required_and_valid() -> None:
    request = base_request()
    request["focus_role_target"] = None
    with pytest.raises(ValidationFailure, match="Focus Role"):
        PlanningService().build(request)
    request["focus_role_target"] = 8
    with pytest.raises(ValidationFailure):
        PlanningService().build(request)


def test_focus_remapping_moves_emphasis_without_changing_global_policy() -> None:
    service = PlanningService()
    results = []
    for target in (2, 5, 7):
        request = base_request()
        request["focus_role_target"] = target
        request["request_id"] = f"focus_{target}"
        results.append(service.build(request))
    assert len({item.planning_profile["content_hash"] for item in results}) == 1
    assert len({item.session_plan["packet_count"] for item in results}) == 1
    assert len({item.session_plan["event_count"] for item in results}) == 1
    motif_sequences = [
        [event["motif_id"] for event in item.event_plan["events"]] for item in results
    ]
    assert motif_sequences[0] == motif_sequences[1] == motif_sequences[2]
    grammar_sequences = [
        [packet["unit_grammar"] for packet in item.packet_plan["packets"]]
        for item in results
    ]
    assert grammar_sequences[0] == grammar_sequences[1] == grammar_sequences[2]
    for target, result in zip((2, 5, 7), results):
        mapping = result.session_pack_plan["focus_role_mapping"]
        assert mapping["target_logical_channel"] == target
        assert mapping["focus_role_source"] == "diagnostic_run_request"
        assert mapping["profile_default"] is False
        assert mapping["associated_density_emphasis"]
        assert not mapping["playback_intensity_changed"]
        assert not mapping["calibration_changed"]
        occupancy = Counter(event["logical_channel"] for event in result.event_plan["events"])
        assert occupancy[target] >= min(occupancy.values())


@pytest.mark.parametrize("session_id", [5, 6, 7])
def test_unsupported_session_requests_do_not_fallback(session_id: int) -> None:
    request = base_request()
    request["selected_session_ids"] = [session_id]
    with pytest.raises(ValidationFailure, match="mode_not_implemented_in_wge3"):
        PlanningService().build(request)


@pytest.mark.parametrize("target", ["diagnostic_wav", "playback_json", "assembled_stereo_wav_pack"])
def test_audio_and_playback_targets_are_rejected(target: str) -> None:
    request = base_request()
    request["requested_export_target"] = target
    with pytest.raises(ValidationFailure):
        PlanningService().build(request)
