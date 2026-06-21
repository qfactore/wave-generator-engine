import math
from typing import Any

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.profiles.hashing import validate_content_hash
from wave_generator_engine.profiles.validation import validate_schema


def validate_delivery_preset(document: dict[str, Any], registry: Any | None = None) -> None:
    validate_schema(document, "delivery_preset.schema.json")
    if not validate_content_hash(document):
        raise ValidationFailure("Delivery-preset content hash mismatch")
    value = document["default_playback_intensity"]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValidationFailure("Playback default must be finite")
    if value < 0 or value > 1:
        raise ValidationFailure("Playback default must be in the engine safety range 0.00-1.00")
    if document["executable"]:
        raise ValidationFailure("WGE-1 delivery presets must be non-executable")
    if document["assembly_policy"] != "unresolved_future_assembler":
        raise ValidationFailure("Assembly mapping must remain explicitly unresolved")
    if registry is not None:
        source = registry.get(document["source_profile_id"])
        if source["kind"] != "source_profile":
            raise ValidationFailure("Delivery preset source is not a source profile")
        if source["content_hash"] != document["source_profile_content_hash"]:
            raise ValidationFailure("Delivery preset source-profile hash mismatch")
