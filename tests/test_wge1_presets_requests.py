import copy
import json
import math
from pathlib import Path

import pytest

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.presets.validation import validate_delivery_preset
from wave_generator_engine.profiles.hashing import content_hash
from wave_generator_engine.profiles.registry import Registry
from wave_generator_engine.requests.validation import validate_run_request


@pytest.fixture
def registry() -> Registry:
    return Registry.load()


def test_three_delivery_presets_are_distinct_presentations(registry: Registry) -> None:
    expected = {"x_alpha25_v1": 1500, "x_alpha45_v1": 2700, "diagnostic_60s_v1": 60}
    hashes = set()
    for preset_id, duration in expected.items():
        preset = registry.load_entry(preset_id)
        assert preset["source_profile_id"] == "x_alpha_standard_v1"
        assert preset["nominal_duration_seconds"] == duration
        assert preset["default_playback_intensity"] == 0.80
        assert preset["assembly_policy"] == "unresolved_future_assembler"
        assert preset["session_selection_policy"] == "explicit_at_run_time"
        assert not preset["executable"]
        hashes.add(preset["source_profile_content_hash"])
    assert len(hashes) == 1
    assert len(registry.entries("source_profile")) == 1


@pytest.mark.parametrize("value", [1.01, -0.01, math.inf, math.nan])
def test_unsafe_playback_defaults_fail(registry: Registry, value: float) -> None:
    preset = copy.deepcopy(registry.load_entry("x_alpha25_v1"))
    preset["default_playback_intensity"] = value
    if math.isfinite(value):
        preset["content_hash"] = content_hash(preset)
    with pytest.raises(ValidationFailure):
        validate_delivery_preset(preset)


def request(sessions=(1,), duration=60, preset="diagnostic_60s_v1") -> dict:
    return {
        "schema_version": "wge.run_request.v1",
        "source_profile_id": "x_alpha_standard_v1",
        "delivery_preset_id": preset,
        "selected_session_ids": list(sessions),
        "requested_duration_seconds": duration,
        "focus_role_override": None,
        "playback_default_override": None,
        "requested_export_target": "analysis_report",
        "random_seed": 42,
        "motif_time_scale_ratio": None,
        "carrier_frequency_hz": None,
        "notes": [],
    }


@pytest.mark.parametrize("sessions", [(1,), (1, 4, 7), tuple(range(1, 8))])
def test_session_selections_validate_without_planning(registry: Registry, sessions) -> None:
    result = validate_run_request(request(sessions), registry)
    assert result == {
        "valid": True, "executable": False, "creates_session_plan": False,
        "creates_render_plan": False, "export_target_authorized": False,
    }


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(selected_session_ids=[1, 1]),
    lambda d: d.update(selected_session_ids=[8]),
    lambda d: d.update(requested_duration_seconds=0),
    lambda d: d.update(delivery_preset_id="x_alpha45_v1", source_profile_id="other"),
    lambda d: d.update(playback_default_override=1.1),
    lambda d: d.update(focus_role_override={"target_logical_channel": 2}),
    lambda d: d.update(motif_time_scale_ratio=1.1),
    lambda d: d.update(carrier_frequency_hz=9.5),
])
def test_invalid_run_requests_fail(registry: Registry, mutation) -> None:
    document = request()
    mutation(document)
    with pytest.raises(ValidationFailure):
        validate_run_request(document, registry)


def test_playback_default_is_not_lever_data(registry: Registry) -> None:
    lever_set = registry.load_entry("x_alpha_standard_lever_set_v1")
    assert "playback_intensity" not in lever_set["values"]
    assert "default_playback_intensity" not in lever_set["values"]
