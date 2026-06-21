import copy
import json

import pytest

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.levers.registry import load_lever_registry
from wave_generator_engine.levers.validation import validate_lever_registry, validate_lever_set
from wave_generator_engine.profiles.hashing import content_hash
from wave_generator_engine.profiles.registry import Registry


def test_canonical_hashes_are_deterministic_and_semantic() -> None:
    first = {"b": 2, "a": 1, "content_hash": "ignored"}
    second = json.loads(' { "a": 1, "b": 2, "content_hash": "different" } ')
    assert content_hash(first) == content_hash(second)
    second["b"] = 3
    assert content_hash(first) != content_hash(second)


def test_initial_lever_registry_contract() -> None:
    registry = load_lever_registry()
    validate_lever_registry(registry)
    ids = {item["lever_id"] for item in registry["levers"]}
    assert "carrier_frequency_hz" not in ids
    assert "playback_intensity" not in ids
    assert len(ids) == 8
    pulse = [item for item in registry["levers"] if item["category"] == "pulse_pattern"]
    assert len(pulse) == 6
    assert all(not item["basic_visible"] and item["advanced_visible"] for item in pulse)
    assert all(item["minimum"] is None and item["maximum"] is None for item in pulse)


def test_time_scale_remains_experimental() -> None:
    scale = next(item for item in load_lever_registry()["levers"]
                 if item["lever_id"] == "motif_time_scale_ratio")
    assert scale["availability"] == "experimental_uncertified"
    assert scale["minimum_trust_level"] == "experimental"
    assert scale["locked_in_exact"]
    assert scale["minimum"] is None and scale["maximum"] is None
    assert not scale["basic_visible"]


def test_basic_and_advanced_share_registry() -> None:
    registry = Registry.load()
    basic = registry.load_entry("basic")
    advanced = registry.load_entry("advanced")
    assert basic["lever_registry_id"] == advanced["lever_registry_id"]
    assert "motif_time_scale_ratio" not in basic["visible_lever_ids"]
    assert "motif_time_scale_ratio" in advanced["visible_lever_ids"]


def test_unknown_and_unavailable_levers_fail() -> None:
    registry = load_lever_registry()
    lever_set = copy.deepcopy(Registry.load().load_entry("x_alpha_standard_lever_set_v1"))
    lever_set["values"]["unknown"] = 1
    lever_set["content_hash"] = content_hash(lever_set)
    with pytest.raises(ValidationFailure, match="Unknown"):
        validate_lever_set(lever_set, registry, "exact")
    lever_set["values"] = {"trailing_event_count": 2}
    lever_set["content_hash"] = content_hash(lever_set)
    with pytest.raises(ValidationFailure, match="Unavailable"):
        validate_lever_set(lever_set, registry, "bounded")


def test_adjustable_carrier_definition_fails() -> None:
    registry = copy.deepcopy(load_lever_registry())
    candidate = copy.deepcopy(registry["levers"][0])
    candidate.update({
        "lever_id": "carrier_frequency_hz", "availability": "available",
        "profile_mutable": True, "run_mutable": True,
    })
    registry["levers"].append(candidate)
    registry["content_hash"] = content_hash(registry)
    with pytest.raises(ValidationFailure, match="carrier"):
        validate_lever_registry(registry)


def test_focus_role_coupling_is_preserved() -> None:
    lever_set = Registry.load().load_entry("x_alpha_standard_lever_set_v1")
    focus = lever_set["role_bindings"]["focus_role"]
    assert focus["allowed_logical_channels"] == list(range(8))
    assert focus["associated_density_emphasis"]
    assert not focus["changes_global_playback_intensity"]
    assert focus["target_logical_channel"] is None
