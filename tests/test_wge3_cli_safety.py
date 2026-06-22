import inspect
import json
from pathlib import Path

from wave_generator_engine.cli import main

ROOT = Path(__file__).resolve().parents[1]
REQUEST = ROOT / "examples/run_requests/x_alpha_session1_diagnostic_60s.json"


def test_plan_and_run_cli(tmp_path: Path, capsys) -> None:
    runs = tmp_path / "runs"
    assert main([
        "plans", "build", "--request", str(REQUEST),
        "--runs-dir", str(runs), "--json",
    ]) == 0
    built = json.loads(capsys.readouterr().out)
    assert built["valid"] and not built["executable_for_rendering"]
    plan = runs / "latest/session_pack_plan.json"
    assert main(["plans", "validate", str(plan), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["valid"]
    assert main(["runs", "list", "--runs-dir", str(runs), "--json"]) == 0
    assert "latest" in json.loads(capsys.readouterr().out)
    assert main(["runs", "show", "latest", "--runs-dir", str(runs), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["analysis_report_only"]


def test_diagnostics_cli_regenerates_metadata_only(tmp_path: Path, capsys) -> None:
    runs = tmp_path / "runs"
    assert main([
        "plans", "build", "--request", str(REQUEST),
        "--runs-dir", str(runs), "--json",
    ]) == 0
    capsys.readouterr()
    assert main([
        "diagnostics", "generate", "--plan", str(runs / "latest"), "--json"
    ]) == 0
    manifest = json.loads(capsys.readouterr().out)
    assert not manifest["waveform_access_required"]


def test_no_renderer_exporter_or_waveform_buffer() -> None:
    package = ROOT / "src/wave_generator_engine"
    names = {path.name for path in package.rglob("*.py")}
    assert not {"renderer.py", "audio_exporter.py", "playback_exporter.py", "wge4.py"} & names
    planning_source = "\n".join(
        path.read_text() for path in (package / "planning").rglob("*.py")
    )
    assert "np.zeros" not in planning_source
    assert "waveform_buffer" not in planning_source
    assert "motif.samples" not in planning_source


def test_committed_request_is_analysis_only() -> None:
    request = json.loads(REQUEST.read_text())
    assert request["requested_export_target"] == "analysis_report"
    assert request["root_seed"] == 20260622
    assert request["selected_session_ids"] == [1]
    assert request["focus_role_target"] in {2, 5, 7}
