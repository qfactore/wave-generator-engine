import json
from pathlib import Path

from wave_generator_engine.domain import (
    DeliveryPreset, ExportTarget, LeverView, ProfileStatus, SessionSelection, TrustLevel,
)
from wave_generator_engine.profiles.registry import validate_profile_scaffold

ENGINE_ROOT = Path(__file__).resolve().parents[1]


def test_required_profile_scaffold_exists() -> None:
    validate_profile_scaffold(ENGINE_ROOT)


def test_reserved_profile_is_non_executable_and_shared() -> None:
    data = json.loads((ENGINE_ROOT / "profiles/registry.json").read_text())
    source = data["source_profiles"][0]
    assert source["id"] == "x_alpha_standard_v1"
    assert source["executable"] is False
    presets = data["delivery_presets"]
    assert presets["x_alpha25"]["source_profile_id"] == presets["x_alpha45"]["source_profile_id"]


def test_inert_domain_types_cover_future_seams() -> None:
    assert set(LeverView) == {LeverView.BASIC, LeverView.ADVANCED}
    assert TrustLevel.EXACT.value == "exact"
    assert ProfileStatus.ARCHIVED.value == "archived"
    assert DeliveryPreset.DIAGNOSTIC_60S.value == "diagnostic_60s"
    assert ExportTarget.PLAYBACK_JSON.value == "playback_json"
    assert SessionSelection(all_seven=True, preview_seconds=60).preview_seconds == 60


def test_no_renderer_or_exporter_module_exists() -> None:
    package = ENGINE_ROOT / "src/wave_generator_engine"
    names = {path.name for path in package.rglob("*.py")}
    assert "renderer.py" not in names
    assert "exporter.py" not in names
    assert "scheduler.py" not in names
