from pathlib import Path

from wave_generator_engine.config import PROFILE_ROOT
from wave_generator_engine.profiles.loader import load_document


def load_view(view_id: str, root: Path = PROFILE_ROOT) -> dict:
    return load_document(root / f"lever_definitions/{view_id}_view.json")
