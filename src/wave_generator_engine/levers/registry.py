from pathlib import Path

from wave_generator_engine.config import PROFILE_ROOT
from wave_generator_engine.profiles.loader import load_document
from .validation import validate_lever_registry


def load_lever_registry(root: Path = PROFILE_ROOT) -> dict:
    document = load_document(root / "lever_definitions/lever_registry.json")
    validate_lever_registry(document)
    return document


def get_lever(lever_id: str, root: Path = PROFILE_ROOT) -> dict:
    matches = [item for item in load_lever_registry(root)["levers"] if item["lever_id"] == lever_id]
    if len(matches) != 1:
        from wave_generator_engine.errors import ValidationFailure
        raise ValidationFailure(f"Unknown lever ID: {lever_id}")
    return matches[0]
