from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_output_or_wge2_implementation_exists() -> None:
    excluded = {".git", ".venv", "__pycache__", ".pytest_cache"}
    files = [
        path for path in ROOT.rglob("*")
        if path.is_file() and not any(part in excluded for part in path.parts)
    ]
    assert not any(path.suffix.lower() in {".wav", ".wave", ".flac", ".mp3"} for path in files)
    assert not any("playback" in path.name.lower() and path.suffix == ".json" for path in files)
    assert not any("upload" in path.name.lower() and path.suffix == ".json" for path in files)
    module_names = {path.name for path in (ROOT / "src/wave_generator_engine").rglob("*.py")}
    assert not {"renderer.py", "scheduler.py", "exporter.py", "transform_executor.py"} & module_names


def test_no_frozen_archive_is_copied() -> None:
    files = [
        path for path in ROOT.rglob("*")
        if path.is_file() and ".venv" not in path.parts
    ]
    assert not [path for path in files if path.suffix == ".npz"]
    assert not [path for path in files if path.suffix == ".npy"]
