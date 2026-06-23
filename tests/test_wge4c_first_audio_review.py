import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from wave_generator_engine.export_contract.diagnostic import (
    DiagnosticSessionExportService,
)
from wave_generator_engine.profiles.hashing import validate_content_hash

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/latest"
EXPORT = RUN / "diagnostic_export"
SCHEMA = json.loads(
    (ROOT / "schemas/human_listening_review.schema.json").read_text()
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text())


def test_review_artifacts_validate_and_have_matching_content() -> None:
    run_review = _json(EXPORT / "human_listening_review.json")
    report_review = _json(ROOT / "reports/wge4c_first_audio_review.json")
    validator = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
    validator.validate(run_review)
    validator.validate(report_review)
    assert validate_content_hash(run_review)
    assert validate_content_hash(report_review)
    assert run_review == report_review


def test_three_part_verdict_preserves_duration_block() -> None:
    review = _json(EXPORT / "human_listening_review.json")
    assert review["human_overall_verdict"] == "PASS"
    assert review["audio_chain_integrity"] == "approved"
    assert review["first_audio_milestone"] == "passed"
    assert review["session1_duration_qualification_authorized"] is False
    assert review["duration_blocker"] == \
        "missing meso-scale cluster/rhythm organization"
    assert review["meso_cluster_rhythm_modeling_authorized"] is True


def test_human_observations_meet_integrity_gate() -> None:
    observations = _json(
        EXPORT / "human_listening_review.json"
    )["human_observations"]
    for branch_id in ("branch_01", "branch_02", "branch_03", "branch_04"):
        branch = observations[branch_id]
        assert branch["left_and_right_active"] == "YES"
        assert branch["corruption_or_crackle"] == "none observed"
        assert branch["unexpected_start_or_end_pop"] == "none observed"
        assert branch["other_observation"] == "structurally appears correct"


def test_committed_wav_hashes_and_pack_remain_valid() -> None:
    review = _json(EXPORT / "human_listening_review.json")
    validation = DiagnosticSessionExportService.validate(RUN)
    assert validation == {
        "valid": True,
        "file_count": 4,
        "pack_hash": review["export_pack_hash"],
        "wge4c_authorized": True,
    }
    files = sorted((EXPORT / "files").glob("*.wav"))
    assert len(files) == 4
    actual = [hashlib.sha256(path.read_bytes()).hexdigest() for path in files]
    expected = [item["wav_sha256"] for item in review["ordered_wav_hashes"]]
    assert actual == expected


def test_review_does_not_authorize_unreviewed_claims_or_generation() -> None:
    review = _json(EXPORT / "human_listening_review.json")
    joined = " ".join(review["limitations"]).casefold()
    for limitation in (
        "therapeutic efficacy",
        "subjective-effect equivalence",
        "target-headset certification",
        "production readiness",
        "safety certification",
        "not validated",
    ):
        assert limitation in joined
    assert not list(EXPORT.rglob("*playback*.json"))
    assert not list(EXPORT.rglob("*upload*.json"))
    assert not list(EXPORT.rglob("*.pkf"))
