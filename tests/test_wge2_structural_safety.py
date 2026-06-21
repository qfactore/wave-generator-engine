import inspect
from pathlib import Path

import wave_generator_engine.motifs.archive as archive
import wave_generator_engine.motifs.authority as authority
import wave_generator_engine.motifs.identity as identity

ROOT = Path(__file__).resolve().parents[1]


def test_archive_is_only_opened_read_only_and_without_pickle() -> None:
    archive_source = inspect.getsource(archive)
    assert 'open("rb")' in archive_source
    assert "allow_pickle=False" in archive_source
    assert 'open("wb")' not in archive_source
    assert 'open("ab")' not in archive_source


def test_blocked_final_test_paths_are_guarded() -> None:
    source = inspect.getsource(authority)
    assert '"final_test" in recorded.casefold()' in source


def test_no_wge3_or_execution_modules_exist() -> None:
    package = ROOT / "src/wave_generator_engine"
    names = {path.name for path in package.rglob("*.py")}
    assert not {
        "scheduler.py", "renderer.py", "exporter.py", "transform_executor.py",
        "session_plan.py", "render_plan.py", "wge3.py",
    } & names


def test_exact_access_has_no_random_import() -> None:
    source = inspect.getsource(identity)
    assert "import random" not in source
    assert "from random" not in source
