import json
from pathlib import Path

from wave_generator_engine.interchange.readiness import validate_interchange, write_reports


def test_success_readiness_and_reports(interchange_root: Path, tmp_path: Path) -> None:
    report = validate_interchange(interchange_root)
    assert report["final_status"] == "WGE0_ENGINE_SCAFFOLD_READY"
    assert report["authority_artifacts_validated"] == 5
    assert report["frozen_authority"]["identity_count"] == 84
    write_reports(tmp_path, report)
    saved = json.loads((tmp_path / "wge0_readiness_report.json").read_text())
    assert saved["audio_generated"] is False
    assert saved["playback_json_generated"] is False
    markdown = (tmp_path / "WGE0_READINESS_REPORT.md").read_text()
    assert str(interchange_root.parent) not in markdown
