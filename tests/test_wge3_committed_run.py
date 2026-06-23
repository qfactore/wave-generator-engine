import json
from pathlib import Path

from jsonschema import Draft202012Validator

from wave_generator_engine.planning.service import PlanningService
from wave_generator_engine.profiles.hashing import validate_content_hash

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/latest"


def test_committed_run_exists_and_validates() -> None:
    from wave_generator_engine import __version__
    assert __version__ == "0.5.2"
    assert RUN.is_dir()
    manifest = json.loads((RUN / "run_manifest.json").read_text())
    assert validate_content_hash(manifest)
    schema = json.loads((ROOT / "schemas/run_manifest.schema.json").read_text())
    Draft202012Validator(schema).validate(manifest)
    assert manifest["analysis_report_only"]
    assert not manifest["audio_directory_created"]


def test_committed_core_hashes_remain_frozen_while_candidate_rebuild_differs(
    tmp_path: Path,
) -> None:
    stored = json.loads((RUN / "run_manifest.json").read_text())
    paths = {
        "planning_profile": "planning_profile_snapshot.json",
        "session_pack_plan": "session_pack_plan.json",
        "session_plan": "sessions/session_01/session_plan.json",
        "macro_state_plan": "sessions/session_01/macro_state_plan.json",
        "packet_plan": "sessions/session_01/packet_plan.json",
        "event_plan": "sessions/session_01/event_plan.json",
        "validation_report": "sessions/session_01/validation_report.json",
    }
    for key, relative in paths.items():
        document = json.loads((RUN / relative).read_text())
        assert validate_content_hash(document)
        assert document["content_hash"] == stored["core_hashes"][key]
    request = json.loads(
        (ROOT / "examples/run_requests/x_alpha_session1_diagnostic_60s.json").read_text()
    )
    result = PlanningService().build(request)
    candidate_hashes = PlanningService.core_hashes(result)
    assert candidate_hashes["request"] == stored["core_hashes"]["request"]
    assert candidate_hashes["packet_plan"] != stored["core_hashes"]["packet_plan"]
    assert result.packet_plan["meso_schedule"]["enabled"]
    assert list(tmp_path.iterdir()) == []


def test_committed_run_has_no_audio_or_upstream_paths() -> None:
    assert not (RUN / "audio").exists()
    assert {
        path.relative_to(RUN) for path in RUN.rglob("*.wav")
    } == {
        Path(f"diagnostic_export/files/x_alpha_session_01_baseline_branch_{index:02d}.wav")
        for index in range(1, 5)
    }
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
    assert readiness["final_status"] == "WGE3_SESSION1_SOURCE_ALIGNED"
