import json
from pathlib import Path

from wave_generator_engine.cli import main


def test_cli_success(interchange_root: Path, tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    assert main([
        "validate-interchange", "--interchange-dir", str(interchange_root),
        "--report-dir", str(report_dir),
    ]) == 0
    report = json.loads((report_dir / "wge0_readiness_report.json").read_text())
    assert report["final_status"] == "WGE0_ENGINE_SCAFFOLD_READY"


def test_cli_failure_is_nonzero_and_reported(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    assert main([
        "validate-interchange", "--interchange-dir", str(tmp_path / "missing"),
        "--report-dir", str(report_dir),
    ]) == 1
    report = json.loads((report_dir / "wge0_readiness_report.json").read_text())
    assert report["final_status"] == "REVISE_WGE0_ENGINE_SCAFFOLD"
