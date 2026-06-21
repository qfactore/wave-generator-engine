import json
from pathlib import Path
from typing import Any

from wave_generator_engine.errors import ValidationFailure


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationFailure(f"Required JSON is unreadable: {path.name}") from exc


def parse_required_json(root: Path, required_paths: tuple[str, ...]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for relative in required_paths:
        if relative.endswith(".json"):
            parsed[relative] = load_json(root / relative)
    return parsed
