import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WGE = ROOT / ".venv/bin/wge"


def test_qualification_cli_show_and_validate() -> None:
    for command in (
        [str(WGE), "qualification", "show", "runs/latest", "--json"],
        [str(WGE), "qualification", "validate", "runs/latest", "--json"],
    ):
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 0
        assert json.loads(result.stdout)


def test_qualify_baseline_cli_is_additive(tmp_path: Path) -> None:
    run = tmp_path / "run"
    shutil.copytree(
        ROOT / "runs/latest", run,
        ignore=shutil.ignore_patterns("qualification"),
    )
    before = (run / "sessions/session_01/event_plan.json").read_bytes()
    result = subprocess.run(
        [
            str(WGE), "qualify", "baseline", "--run", str(run),
            "--report-dir", str(tmp_path / "reports"), "--json",
        ],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["verdict"] == "qualified_with_documented_caveats"
    assert (run / "sessions/session_01/event_plan.json").read_bytes() == before


def test_no_render_export_or_wge4_modules_exist() -> None:
    source = ROOT / "src/wave_generator_engine"
    names = {path.name.lower() for path in source.rglob("*") if path.is_file()}
    assert not {"renderer.py", "exporter.py", "wge4.py"} & names
    assert {
        path.relative_to(ROOT) for path in ROOT.rglob("*.wav")
        if ".venv" not in path.parts
    } == {
        Path(f"runs/latest/diagnostic_export/files/"
             f"x_alpha_session_01_baseline_branch_{index:02d}.wav")
        for index in range(1, 5)
    }
    assert not list(ROOT.rglob("*playback*.json"))
    assert not list(ROOT.rglob("*upload*.json"))
