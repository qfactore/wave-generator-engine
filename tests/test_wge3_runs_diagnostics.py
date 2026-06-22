import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from wave_generator_engine.diagnostics.service import DIAGNOSTIC_NAMES
from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.planning.service import PlanningService
from wave_generator_engine.profiles.hashing import validate_content_hash
from wave_generator_engine.runs.storage import RunStorage

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def planned_result():
    request = json.loads(
        (ROOT / "examples/run_requests/x_alpha_session1_diagnostic_60s.json").read_text()
    )
    return PlanningService().build(request)


def test_run_layout_and_diagnostics_are_complete(
    planned_result, tmp_path: Path
) -> None:
    target = RunStorage(tmp_path / "runs").write_latest(planned_result)
    assert not (target / "audio").exists()
    required = [
        "run_manifest.json", "request.json", "authority_snapshot.json",
        "source_profile_snapshot.json", "delivery_preset_snapshot.json",
        "planning_profile_snapshot.json", "session_pack_plan.json",
        "sessions/session_01/session_plan.json",
        "sessions/session_01/macro_state_plan.json",
        "sessions/session_01/packet_plan.json",
        "sessions/session_01/pulse_pattern_plan.json",
        "sessions/session_01/channel_unit_plan.json",
        "sessions/session_01/event_plan.json",
        "sessions/session_01/events.csv",
        "sessions/session_01/validation_report.json",
        "diagnostics/diagnostic_manifest.json",
    ]
    assert all((target / item).is_file() for item in required)
    assert len(list((target / "diagnostics/figures").glob("*.png"))) == len(DIAGNOSTIC_NAMES)
    assert len(list((target / "diagnostics/raw").glob("*.json"))) == len(DIAGNOSTIC_NAMES) + 1
    assert len(list((target / "diagnostics/raw").glob("*.csv"))) == 2
    manifest = json.loads((target / "diagnostics/diagnostic_manifest.json").read_text())
    schema = json.loads((ROOT / "schemas/diagnostic_manifest.schema.json").read_text())
    Draft202012Validator(schema).validate(manifest)
    assert not manifest["waveform_access_required"]


def test_diagnostic_totals_match_plans(planned_result, tmp_path: Path) -> None:
    target = RunStorage(tmp_path / "runs").write_latest(planned_result)
    raw = target / "diagnostics/raw"
    event_density = json.loads((raw / "event_density_over_time.json").read_text())
    channel_occupancy = json.loads((raw / "channel_occupancy.json").read_text())
    motif_usage = json.loads((raw / "motif_usage.json").read_text())
    pulse = json.loads((raw / "pulse_pattern_prevalence.json").read_text())
    assert sum(event_density["event_count"]) == len(planned_result.event_plan["events"])
    assert sum(channel_occupancy.values()) == len(planned_result.event_plan["events"])
    assert sum(motif_usage.values()) == len(planned_result.event_plan["events"])
    assert pulse["with_continuations"] + pulse["without_continuations"] == \
        len(planned_result.packet_plan["packets"])


def test_core_plans_and_raw_diagnostics_are_byte_identical(
    planned_result, tmp_path: Path
) -> None:
    first = RunStorage(tmp_path / "one").write_latest(planned_result)
    second_result = PlanningService().build(planned_result.run_request)
    second = RunStorage(tmp_path / "two").write_latest(second_result)
    core = [
        "request.json", "authority_snapshot.json", "planning_profile_snapshot.json",
        "session_pack_plan.json", "sessions/session_01/session_plan.json",
        "sessions/session_01/macro_state_plan.json",
        "sessions/session_01/packet_plan.json",
        "sessions/session_01/event_plan.json",
        "sessions/session_01/validation_report.json",
    ]
    for relative in core:
        assert (first / relative).read_bytes() == (second / relative).read_bytes()
    first_raw = sorted((first / "diagnostics/raw").glob("*"))
    second_raw = sorted((second / "diagnostics/raw").glob("*"))
    assert [item.name for item in first_raw] == [item.name for item in second_raw]
    for left, right in zip(first_raw, second_raw):
        assert left.read_bytes() == right.read_bytes()


def test_latest_replacement_is_complete(planned_result, tmp_path: Path) -> None:
    storage = RunStorage(tmp_path / "runs")
    target = storage.write_latest(planned_result)
    (target / "stale.txt").write_text("old")
    target = storage.write_latest(planned_result)
    assert not (target / "stale.txt").exists()
    assert (target / "run_manifest.json").is_file()


def test_saved_run_id_and_overwrite_protection(planned_result, tmp_path: Path) -> None:
    storage = RunStorage(tmp_path / "runs")
    with pytest.raises(ValidationFailure):
        storage.write_saved("../escape", planned_result)
    storage.write_saved("safe-run", planned_result)
    with pytest.raises(ValidationFailure, match="already exists"):
        storage.write_saved("safe-run", planned_result)
    assert storage.write_saved("safe-run", planned_result, overwrite=True).is_dir()


def test_run_manifest_hash_and_no_raw_paths(planned_result, tmp_path: Path) -> None:
    target = RunStorage(tmp_path / "runs").write_latest(planned_result)
    manifest = json.loads((target / "run_manifest.json").read_text())
    assert validate_content_hash(manifest)
    schema = json.loads((ROOT / "schemas/run_manifest.schema.json").read_text())
    Draft202012Validator(schema).validate(manifest)
    for path in target.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".csv"}:
            assert "/Users/" not in path.read_text()
