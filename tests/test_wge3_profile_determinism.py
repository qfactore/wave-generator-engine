import copy
import inspect
import json
import random
from pathlib import Path

import pytest

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.planning.pipeline import PlanningPipeline
from wave_generator_engine.planning.profile_resolver import PlanningProfileResolver
from wave_generator_engine.planning.seeds import derive_seed
from wave_generator_engine.planning.service import PlanningService

ROOT = Path(__file__).resolve().parents[1]
REQUEST = ROOT / "examples/run_requests/x_alpha_session1_diagnostic_60s.json"


def request() -> dict:
    return json.loads(REQUEST.read_text())


def test_session_modes_resolve_through_profile_data() -> None:
    resolver = PlanningProfileResolver()
    _, _, first, _ = resolver.resolve("x_alpha_standard_v1", "diagnostic_60s_v1", 1)
    _, _, second, _ = resolver.resolve("x_alpha_standard_v1", "diagnostic_60s_v1", 2)
    assert first["mode"] == second["mode"] == "baseline"
    source = inspect.getsource(PlanningPipeline)
    assert "session_id == 1" not in source
    assert "if session_id == 1" not in "\n".join(
        path.read_text() for path in (ROOT / "src/wave_generator_engine/planning").rglob("*.py")
    )


@pytest.mark.parametrize("session_id", [5, 6, 7])
def test_unsupported_modes_fail_closed(session_id: int) -> None:
    with pytest.raises(ValidationFailure, match="mode_not_implemented_in_wge3"):
        PlanningProfileResolver().resolve(
            "x_alpha_standard_v1", "diagnostic_60s_v1", session_id
        )


def test_tier2_guidance_and_provisional_defaults_are_labelled() -> None:
    _, _, snapshot, _ = PlanningProfileResolver().resolve(
        "x_alpha_standard_v1", "diagnostic_60s_v1", 1
    )
    assert snapshot["numeric_guidance_used"]
    assert all(item["authority_tier"] == "tier_2"
               and item["binding_status"] == "diagnostic_guidance"
               for item in snapshot["numeric_guidance_used"].values())
    assert snapshot["provisional_defaults"]
    assert snapshot["authority_snapshot"]["tier_3_inputs_used"] == []
    assert snapshot["authority_snapshot"]["tier_4_inputs_used"] == []


def test_same_request_produces_identical_core_plans() -> None:
    service = PlanningService()
    first = service.build(request())
    second = service.build(request())
    assert service.core_hashes(first) == service.core_hashes(second)
    assert first.event_plan == second.event_plan


def test_changed_seed_changes_stochastic_decisions() -> None:
    service = PlanningService()
    first = service.build(request())
    changed = request()
    changed["root_seed"] += 1
    changed["request_id"] = "changed_seed"
    second = service.build(changed)
    assert first.event_plan["content_hash"] != second.event_plan["content_hash"]


def test_seed_derivation_is_stable_and_does_not_use_hash() -> None:
    assert derive_seed(20260622, "session:1", "packets") == \
        derive_seed(20260622, "session:1", "packets")
    source = inspect.getsource(derive_seed)
    assert "hash(" not in source
    assert "sha256" in source


def test_local_planning_does_not_alter_global_random_state() -> None:
    random.seed(123)
    expected = random.random()
    random.seed(123)
    PlanningService().build(request())
    assert random.random() == expected


def test_request_formatting_does_not_change_hash() -> None:
    document = request()
    reordered = json.loads(json.dumps(document, sort_keys=True, indent=4))
    from wave_generator_engine.profiles.hashing import content_hash
    assert content_hash(document) == content_hash(reordered)
