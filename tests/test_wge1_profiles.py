import copy
import json
from pathlib import Path

import pytest

from wave_generator_engine.config import EXPECTED_FROZEN_SHA256
from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.profiles.hashing import content_hash
from wave_generator_engine.profiles.lifecycle import validate_transition
from wave_generator_engine.profiles.registry import Registry
from wave_generator_engine.profiles.validation import (
    assert_editable, validate_parent, validate_source_profile,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def registry() -> Registry:
    return Registry.load()


def test_x_alpha_standard_contract(registry: Registry) -> None:
    profile = registry.load_entry("x_alpha_standard_v1")
    validate_source_profile(profile)
    assert profile["profile_status"] == "preset_locked"
    assert profile["immutable"] and not profile["executable"]
    assert profile["content_hash"] == content_hash(profile)
    assert profile["frozen_authority"] == {
        "archive_sha256": EXPECTED_FROZEN_SHA256,
        "identity_count": 84,
        "identity_index_reference": "bank/frozen_assets/frozen_motif_identity_index.json",
        "asset_access": "prohibited_in_wge1",
    }


def test_session_modes_are_profile_data(registry: Registry) -> None:
    sessions = registry.load_entry("x_alpha_standard_v1")["session_topology"]["sessions"]
    assert [item["mode_id"] for item in sessions] == [
        "baseline", "baseline", "baseline", "baseline", "dense", "dense", "complex"
    ]
    source = "\n".join(path.read_text() for path in (ROOT / "src").rglob("*.py"))
    assert "if session_number" not in source


def test_channel_convention_and_role_bundle(registry: Registry) -> None:
    channel = registry.load_entry("x_alpha_standard_v1")["channel_topology"]
    assert channel["logical_channel_ids"] == list(range(8))
    assert channel["indexing"] == "zero_based_0_7"
    focus = channel["focus_role"]
    assert focus["target_logical_channel"] is None
    assert focus["mapping_status"] == "unresolved_no_authoritative_default"
    assert focus["associated_density_emphasis"]
    assert not focus["fixed_physical_channel"]
    assert not focus["changes_global_playback_intensity"]
    assert not focus["changes_render_calibration"]


def test_calibration_is_locked_authority_not_gain_logic(registry: Registry) -> None:
    calibration = registry.load_entry("x_alpha_standard_v1")["calibration_policy"]
    assert calibration["authority_artifact_id"] == "x_alpha_reference_calibration_v1"
    assert calibration["resolved_validation"]["reference_multiplier"] == 1.1
    assert calibration["resolved_validation"]["per_motif_normalization"] is False
    assert calibration["resolved_validation"]["default_limiter"] is False


def test_incorrect_hash_and_authority_changes_fail(registry: Registry) -> None:
    profile = copy.deepcopy(registry.load_entry("x_alpha_standard_v1"))
    profile["display_name"] = "Changed"
    with pytest.raises(ValidationFailure, match="hash"):
        validate_source_profile(profile)
    profile = copy.deepcopy(registry.load_entry("x_alpha_standard_v1"))
    profile["frozen_authority"]["archive_sha256"] = "0" * 64
    profile["content_hash"] = content_hash(profile)
    with pytest.raises(ValidationFailure, match="Frozen"):
        validate_source_profile(profile)
    profile = copy.deepcopy(registry.load_entry("x_alpha_standard_v1"))
    profile["permitted_configuration_surface"]["carrier_control"] = True
    profile["content_hash"] = content_hash(profile)
    with pytest.raises(ValidationFailure, match="prohibited"):
        validate_source_profile(profile)
    profile = copy.deepcopy(registry.load_entry("x_alpha_standard_v1"))
    profile["calibration_policy"]["authority_artifact_id"] = "other"
    profile["content_hash"] = content_hash(profile)
    with pytest.raises(ValidationFailure, match="Calibration authority"):
        validate_source_profile(profile)


def test_immutable_lifecycle_rules(registry: Registry) -> None:
    profile = registry.load_entry("x_alpha_standard_v1")
    with pytest.raises(ValidationFailure):
        assert_editable(profile)
    with pytest.raises(ValidationFailure):
        validate_transition(profile, "draft")
    for status in ("active", "archived"):
        candidate = copy.deepcopy(profile)
        candidate["profile_status"] = status
        candidate["immutable"] = True
        with pytest.raises(ValidationFailure):
            assert_editable(candidate)


def test_parent_hash_validation(registry: Registry) -> None:
    parent = registry.load_entry("x_alpha_standard_v1")
    child = {"parent_profile_id": parent["profile_id"],
             "parent_content_hash": parent["content_hash"],
             "parent_profile_version": parent["profile_version"]}
    validate_parent(child, parent)
    child["parent_content_hash"] = "0" * 64
    with pytest.raises(ValidationFailure):
        validate_parent(child, parent)


def test_registry_rejects_duplicate_ids(tmp_path: Path) -> None:
    import shutil
    root = tmp_path / "profiles"
    shutil.copytree(ROOT / "profiles", root)
    data = json.loads((root / "registry.json").read_text())
    data["entries"].append(copy.deepcopy(data["entries"][0]))
    (root / "registry.json").write_text(json.dumps(data))
    with pytest.raises(ValidationFailure, match="unique"):
        Registry.load(root)


def test_registry_rejects_lifecycle_status_mismatch(tmp_path: Path) -> None:
    import shutil
    root = tmp_path / "profiles"
    shutil.copytree(ROOT / "profiles", root)
    data = json.loads((root / "registry.json").read_text())
    data["entries"][0]["status"] = "active"
    (root / "registry.json").write_text(json.dumps(data))
    with pytest.raises(ValidationFailure, match="lifecycle"):
        Registry.load(root)
