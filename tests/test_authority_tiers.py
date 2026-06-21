import json

import pytest

from wave_generator_engine.config import AUTHORITY_ARTIFACT_SCHEMAS
from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.interchange.authority_tiers import validate_authority_tiers


def authority_data(root):
    artifacts = [json.loads((root / path).read_text()) for path in AUTHORITY_ARTIFACT_SCHEMAS]
    decisions = json.loads((root / "manifests/decision_registry.json").read_text())
    sources = json.loads((root / "manifests/source_artifact_manifest.json").read_text())
    return artifacts, decisions, sources


def test_current_authority_tiers_validate(interchange_root) -> None:
    validate_authority_tiers(*authority_data(interchange_root))


def test_incorrect_artifact_tier_fails(interchange_root) -> None:
    artifacts, decisions, sources = authority_data(interchange_root)
    artifacts[0]["authority_tier"] = "tier_2"
    with pytest.raises(ValidationFailure):
        validate_authority_tiers(artifacts, decisions, sources)


def test_tier_3_cannot_be_certified(interchange_root) -> None:
    artifacts, decisions, sources = authority_data(interchange_root)
    candidate = next(item for item in decisions["decisions"] if item["authority_tier"] == "tier_3")
    candidate["production_certified"] = True
    with pytest.raises(ValidationFailure):
        validate_authority_tiers(artifacts, decisions, sources)


def test_equal_tier_source_conflict_fails(interchange_root) -> None:
    artifacts, decisions, sources = authority_data(interchange_root)
    candidate = next(item for item in sources["artifacts"] if item["classification_status"] == "include")
    candidate["conflicts"] = ["same_tier_candidate"]
    with pytest.raises(ValidationFailure, match="conflict"):
        validate_authority_tiers(artifacts, decisions, sources)
