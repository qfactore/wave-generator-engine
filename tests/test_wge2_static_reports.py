import json
from pathlib import Path

from jsonschema import Draft202012Validator

from wave_generator_engine.calibration.preflight import run_calibration_preflight
from wave_generator_engine.motifs.metrics import summarize_corpus

ROOT = Path(__file__).resolve().parents[1]


def test_static_diagnostic_reports_match_real_corpus(real_motif_bank) -> None:
    stored_summary = json.loads(
        (ROOT / "reports/frozen_motif_corpus_summary.json").read_text()
    )
    actual_summary = summarize_corpus(real_motif_bank.records())
    for key in (
        "motif_count", "duration_seconds_distribution",
        "sample_count_distribution", "sample_peak_distribution",
        "rms_distribution", "dtype_distribution", "identity_verification",
    ):
        assert stored_summary[key] == actual_summary[key]

    stored_preflight = json.loads(
        (ROOT / "reports/calibration_preflight.json").read_text()
    )
    actual_preflight = run_calibration_preflight(real_motif_bank)
    assert stored_preflight == actual_preflight
    schema = json.loads(
        (ROOT / "schemas/calibration_preflight.schema.json").read_text()
    )
    Draft202012Validator(schema).validate(stored_preflight)
