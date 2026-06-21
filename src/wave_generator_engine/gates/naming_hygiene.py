from dataclasses import dataclass
from pathlib import Path

from wave_generator_engine.errors import ValidationFailure

TEXT_SUFFIXES = {".py", ".md", ".toml", ".json", ".txt", ".yaml", ".yml"}
EXCLUDED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", "wave_generator_engine.egg-info"}


@dataclass(frozen=True)
class NamingResult:
    clean: bool
    files_scanned: int


def scan_engine_owned_files(root: Path, forbidden_terms: tuple[str, ...]) -> NamingResult:
    terms = tuple(term.casefold() for term in forbidden_terms if term)
    scanned = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="strict").casefold()
        for term in terms:
            if term in text or term in path.name.casefold():
                raise ValidationFailure(f"Naming hygiene failed in engine-owned file: {path.name}")
    return NamingResult(True, scanned)
