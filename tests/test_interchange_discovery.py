from pathlib import Path

import pytest

from wave_generator_engine.errors import DiscoveryError
from wave_generator_engine.interchange.discovery import MARKERS, discover_interchange


def make_root(path: Path) -> Path:
    for marker in MARKERS:
        target = path / marker
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}")
    return path


def test_successful_sibling_discovery(tmp_path: Path) -> None:
    engine = tmp_path / "wave-generator-engine"
    engine.mkdir()
    expected = make_root(tmp_path / "wave-gen-interchange")
    assert discover_interchange(engine, environ={}) == expected.resolve()


def test_explicit_override_wins(tmp_path: Path) -> None:
    explicit = make_root(tmp_path / "authority")
    engine = tmp_path / "engine"
    engine.mkdir()
    assert discover_interchange(engine, explicit, {}) == explicit.resolve()


def test_environment_override(tmp_path: Path) -> None:
    expected = make_root(tmp_path / "authority")
    engine = tmp_path / "engine"
    engine.mkdir()
    assert discover_interchange(
        engine, environ={"WAVE_GEN_INTERCHANGE_DIR": str(expected)}
    ) == expected.resolve()


def test_missing_interchange_fails_closed(tmp_path: Path) -> None:
    engine = tmp_path / "engine"
    engine.mkdir()
    with pytest.raises(DiscoveryError):
        discover_interchange(engine, environ={})


def test_ambiguous_environment_discovery_fails(tmp_path: Path) -> None:
    engine = tmp_path / "engine"
    engine.mkdir()
    first = make_root(tmp_path / "authority-one")
    second = make_root(tmp_path / "authority-two")
    with pytest.raises(DiscoveryError, match="ambiguous"):
        discover_interchange(
            engine,
            environ={"WAVE_GEN_INTERCHANGE_DIR": f"{first}:{second}"},
        )


@pytest.mark.parametrize("marker", MARKERS)
def test_missing_marker_fails(tmp_path: Path, marker: str) -> None:
    root = make_root(tmp_path / "authority")
    (root / marker).unlink()
    with pytest.raises(DiscoveryError):
        discover_interchange(tmp_path / "engine", root, {})
