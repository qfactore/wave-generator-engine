import json
from pathlib import Path

from jsonschema import Draft202012Validator

from wave_generator_engine.planning.service import PlanningService
from wave_generator_engine.profiles.hashing import validate_content_hash
from wave_generator_engine.runs.storage import RunStorage

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/latest"


def test_committed_run_exists_and_validates() -> None:
    from wave_generator_engine import __version__
    assert __version__ == "0.4.0"
    assert RUN.is_dir()
    manifest = json.loads((RUN / "run_manifest.json").read_text())
    assert validate_content_hash(manifest)
    schema = json.loads((ROOT / "schemas/run_manifest.schema.json").read_text())
    Draft202012Validator(schema).validate(manifest)
    assert manifest["analysis_report_only"]
    assert not manifest["audio_directory_created"]


def test_committed_core_hashes_match_rebuild(tmp_path: Path) -> None:
    request = json.loads(
        (ROOT / "examples/run_requests/x_alpha_session1_diagnostic_60s.json").read_text()
    )
    result = PlanningService().build(request)
    stored = json.loads((RUN / "run_manifest.json").read_text())
    assert PlanningService.core_hashes(result) == stored["core_hashes"]
    rebuilt = RunStorage(tmp_path / "runs").write_latest(result)
    for relative in (
        "session_pack_plan.json",
        "planning_profile_snapshot.json",
        "sessions/session_01/session_plan.json",
        "sessions/session_01/packet_plan.json",
        "sessions/session_01/event_plan.json",
    ):
        assert (RUN / relative).read_bytes() == (rebuilt / relative).read_bytes()
    for source in sorted((RUN / "diagnostics/raw").glob("*")):
        assert source.read_bytes() == (rebuilt / "diagnostics/raw" / source.name).read_bytes()


def test_committed_run_has_no_audio_or_upstream_paths() -> None:
    assert not (RUN / "audio").exists()
    assert not list(RUN.rglob("*.wav"))
    for path in RUN.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".csv"}:
            text = path.read_text()
            assert "/Users/" not in text
            assert "playback_json" not in text
            assert "upload_ready" not in text


def test_readiness_report_matches_committed_run() -> None:
    readiness = json.loads((ROOT / "reports/wge3_readiness_report.json").read_text())
    manifest = json.loads((RUN / "run_manifest.json").read_text())
    assert readiness["session_pack_plan_hash"] == manifest["core_hashes"]["session_pack_plan"]
    assert readiness["session_plan_hash"] == manifest["core_hashes"]["session_plan"]
    assert readiness["event_plan_hash"] == manifest["core_hashes"]["event_plan"]
    assert readiness["final_status"] == "WGE3_BASELINE_PLAN_READY"
