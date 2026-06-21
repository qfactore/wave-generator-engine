from pathlib import Path

import pytest

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.gates.naming_hygiene import scan_engine_owned_files


def test_synthetic_forbidden_token_detected(tmp_path: Path) -> None:
    (tmp_path / "example.md").write_text("synthetic_blocked_token")
    with pytest.raises(ValidationFailure):
        scan_engine_owned_files(tmp_path, ("synthetic_blocked_token",))


def test_clean_engine_passes(tmp_path: Path) -> None:
    (tmp_path / "example.py").write_text("value = 'neutral'")
    assert scan_engine_owned_files(tmp_path, ("synthetic_blocked_token",)).clean


def test_external_interchange_is_not_scanned(tmp_path: Path) -> None:
    engine = tmp_path / "wave-generator-engine"
    external = tmp_path / "wave-gen-interchange"
    engine.mkdir()
    external.mkdir()
    (external / "source.md").write_text("synthetic_blocked_token")
    assert scan_engine_owned_files(engine, ("synthetic_blocked_token",)).clean
