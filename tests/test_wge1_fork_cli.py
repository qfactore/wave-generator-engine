import json
import shutil
from pathlib import Path

import pytest

from wave_generator_engine.cli import main
from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.profiles.fork import fork_profile
from wave_generator_engine.profiles.hashing import content_hash
from wave_generator_engine.profiles.loader import load_document
from wave_generator_engine.profiles.registry import Registry

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def profile_copy(tmp_path: Path) -> Path:
    target = tmp_path / "profiles"
    shutil.copytree(ROOT / "profiles", target)
    return target


def test_fork_creates_one_draft_and_preserves_parent(profile_copy: Path) -> None:
    parent_path = profile_copy / "presets/x_alpha_standard_v1/source_profile.json"
    before = parent_path.read_bytes()
    profile_path, record_path = fork_profile(
        "x_alpha_standard_v1", "custom_profile_v1", "Custom Profile",
        profile_root=profile_copy, now="2026-06-21T12:00:00+00:00",
    )
    assert parent_path.read_bytes() == before
    child = load_document(profile_path)
    record = load_document(record_path)
    assert child["profile_status"] == "draft" and not child["immutable"]
    assert child["parent_content_hash"] == load_document(parent_path)["content_hash"]
    assert record["parent_profile_version"] == "1.0.0"
    assert record["content_hash"] == content_hash(record)
    assert len(list((profile_copy / "active").glob("*/source_profile.json"))) == 1
    assert Registry.load(profile_copy).get("custom_profile_v1")["status"] == "draft"


def test_duplicate_fork_and_overwrite_fail(profile_copy: Path) -> None:
    fork_profile("x_alpha_standard_v1", "custom_profile_v1", "Custom", profile_root=profile_copy)
    with pytest.raises(ValidationFailure):
        fork_profile("x_alpha_standard_v1", "custom_profile_v1", "Custom", profile_root=profile_copy)


def test_fork_preserves_prohibited_authority(profile_copy: Path) -> None:
    child_path, _ = fork_profile(
        "x_alpha_standard_v1", "custom_profile_v1", "Custom", profile_root=profile_copy
    )
    parent = load_document(profile_copy / "presets/x_alpha_standard_v1/source_profile.json")
    child = load_document(child_path)
    assert child["frozen_authority"] == parent["frozen_authority"]
    assert child["calibration_policy"] == parent["calibration_policy"]
    assert child["permitted_configuration_surface"]["carrier_control"] is False
    assert child["permitted_configuration_surface"]["motif_timing_override"] is False


def test_cli_list_show_and_json(capsys) -> None:
    assert main(["profiles", "list", "--json"]) == 0
    assert "x_alpha_standard_v1" in json.loads(capsys.readouterr().out)
    assert main(["presets", "show", "x_alpha25_v1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["nominal_duration_seconds"] == 1500
    assert main(["levers", "show", "motif_time_scale_ratio", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["availability"] == "experimental_uncertified"


def test_cli_request_validation(tmp_path: Path, capsys) -> None:
    path = tmp_path / "request.json"
    path.write_text(json.dumps({
        "schema_version": "wge.run_request.v1",
        "source_profile_id": "x_alpha_standard_v1",
        "delivery_preset_id": "diagnostic_60s_v1",
        "selected_session_ids": [1],
        "requested_duration_seconds": 60,
        "requested_export_target": "analysis_report"
    }))
    assert main(["requests", "validate", str(path), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] and not result["executable"]


def test_cli_fork_writes_one_draft_without_parent_change(
    profile_copy: Path, capsys
) -> None:
    parent = profile_copy / "presets/x_alpha_standard_v1/source_profile.json"
    before = parent.read_bytes()
    assert main([
        "profiles", "fork", "x_alpha_standard_v1",
        "--new-id", "cli_custom_v1", "--display-name", "CLI Custom",
        "--profile-dir", str(profile_copy), "--json",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["created"]
    assert parent.read_bytes() == before
    assert len(list((profile_copy / "active").glob("*/source_profile.json"))) == 1


def test_cycle_detection_rejects_parent_loop() -> None:
    from wave_generator_engine.profiles.fork import _assert_no_cycle

    class FakeRegistry:
        def load_entry(self, item_id):
            return {"profile_id": item_id, "parent_profile_id": "new_profile_v1"}

    with pytest.raises(ValidationFailure, match="Cyclic"):
        _assert_no_cycle(
            {"profile_id": "parent_v1", "parent_profile_id": "other_v1"},
            "new_profile_v1", FakeRegistry(),
        )
