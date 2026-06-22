import json
from pathlib import Path
from typing import Any

from wave_generator_engine.config import ENGINE_ROOT
from wave_generator_engine.errors import ValidationFailure
from .validation import validate_contract


class DiagnosticExportContractService:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (
            ENGINE_ROOT / "contracts/diagnostic_wav_export_contract_v1.json"
        )

    def load(self) -> dict[str, Any]:
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValidationFailure("Diagnostic export contract must be an object")
        return value

    def show(self) -> dict[str, Any]:
        return self.load()

    def validate(self, interchange_dir: Path | None = None) -> dict[str, Any]:
        return validate_contract(self.load(), interchange_dir)
