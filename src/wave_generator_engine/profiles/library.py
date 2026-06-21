import json
from pathlib import Path
from typing import Any

from wave_generator_engine.errors import ValidationFailure


def load_profile_registry(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationFailure("Profile registry is unreadable") from exc
    if not isinstance(data, dict) or not isinstance(data.get("source_profiles"), list):
        raise ValidationFailure("Profile registry has an invalid shape")
    return data
