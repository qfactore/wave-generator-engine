import copy

import pytest

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.qualification.authority import (
    QualificationAuthority,
    select_permitted_artifact,
)


def _artifact(status="include", tier="tier_2", blocked_use=None):
    return {
        "id": "candidate", "classification_status": status,
        "authority_tier": tier, "blocked_use": blocked_use or [],
    }


def test_included_source_reference_is_accepted() -> None:
    assert select_permitted_artifact([_artifact()], "candidate")["authority_tier"] == "tier_2"


@pytest.mark.parametrize(("status", "tier"), [
    ("blocked", "unknown"), ("archive", "tier_4"),
    ("superseded", "tier_4"), ("reference", "tier_3"),
])
def test_disallowed_source_is_rejected(status: str, tier: str) -> None:
    with pytest.raises(ValidationFailure):
        select_permitted_artifact([_artifact(status, tier)], "candidate")


def test_final_test_material_is_rejected() -> None:
    with pytest.raises(ValidationFailure, match="Final-test"):
        select_permitted_artifact(
            [_artifact(blocked_use=["Opening final-test arrays"])], "candidate"
        )


def test_ambiguous_source_mapping_fails_closed() -> None:
    with pytest.raises(ValidationFailure, match="Ambiguous"):
        select_permitted_artifact([_artifact(), copy.deepcopy(_artifact())], "candidate")


def test_runtime_inventory_is_hash_verified_and_high_authority() -> None:
    inventory = QualificationAuthority().inventory()
    assert inventory
    assert all(item.authority_tier in {"tier_1", "tier_2"} for item in inventory)
    assert all(item.path.is_file() for item in inventory)
