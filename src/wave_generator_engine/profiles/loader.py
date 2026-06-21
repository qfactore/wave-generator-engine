import json
from pathlib import Path
from typing import Any

from wave_generator_engine.errors import ValidationFailure


def load_document(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationFailure(f"Document is unreadable: {path.name}") from exc
    if not isinstance(data, dict):
        raise ValidationFailure(f"Document must be an object: {path.name}")
    return data


def write_document(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
