from enum import StrEnum
from typing import Any

from wave_generator_engine.errors import ValidationFailure


class AuthorityTier(StrEnum):
    TIER_0 = "tier_0"
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"
    TIER_4 = "tier_4"


def validate_authority_tiers(
    artifacts: list[dict[str, Any]],
    decisions: dict[str, Any],
    source_manifest: dict[str, Any] | None = None,
) -> None:
    for artifact in artifacts:
        if artifact.get("authority_tier") != AuthorityTier.TIER_1:
            raise ValidationFailure("WG-I8 authority artifact must remain Tier 1")
    for decision in decisions.get("decisions", []):
        tier = decision.get("authority_tier")
        try:
            parsed_tier = AuthorityTier(tier)
        except (TypeError, ValueError):
            raise ValidationFailure("Decision has an unknown authority tier")
        if parsed_tier == AuthorityTier.TIER_4 and decision.get("enforcement_status") == "current":
            raise ValidationFailure("Tier 4 material cannot be current authority")
        if parsed_tier == AuthorityTier.TIER_3 and decision.get("production_certified") is True:
            raise ValidationFailure("Tier 3 guidance cannot be certified")
        if parsed_tier == AuthorityTier.TIER_2 and decision.get("universal_production_constant") is True:
            raise ValidationFailure("Tier 2 values cannot be universal production constants")
    if source_manifest is not None:
        for source in source_manifest.get("artifacts", []):
            if source.get("classification_status") != "include":
                continue
            try:
                tier = AuthorityTier(source.get("authority_tier"))
            except (TypeError, ValueError):
                raise ValidationFailure("Included source has an unknown authority tier")
            if source.get("conflicts"):
                raise ValidationFailure("Included authority conflict requires human resolution")
            if tier == AuthorityTier.TIER_4:
                raise ValidationFailure("Tier 4 source cannot be included as current authority")
