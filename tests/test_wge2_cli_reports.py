import json
from pathlib import Path

from jsonschema import Draft202012Validator

from wave_generator_engine.cli import main

ROOT = Path(__file__).resolve().parents[1]


def _schema(name: str) -> dict:
    return json.loads((ROOT / "schemas" / name).read_text())


def test_motif_cli_commands_return_valid_json(capsys) -> None:
    assert main(["motifs", "validate", "--json"]) == 0
    validation = json.loads(capsys.readouterr().out)
    assert validation["motif_count"] == 84
    assert validation["read_only_validation"]

    assert main(["motifs", "list", "--json"]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert len(listing) == 84
    motif_id = listing[0]["motif_id"]

    assert main(["motifs", "show", motif_id, "--json"]) == 0
    inspection = json.loads(capsys.readouterr().out)
    Draft202012Validator(_schema("motif_inspection_report.schema.json")).validate(
        inspection
    )

    assert main(["motifs", "verify-exact", motif_id, "--json"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    Draft202012Validator(_schema("exact_identity_receipt.schema.json")).validate(
        receipt
    )

    assert main(["motifs", "summarize", "--json"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["motif_count"] == 84


def test_invalid_motif_id_returns_nonzero(capsys) -> None:
    assert main(["motifs", "show", "not_a_motif", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["valid"] is False


def test_calibration_cli_commands(capsys) -> None:
    assert main(["calibration", "inspect", "--json"]) == 0
    policy = json.loads(capsys.readouterr().out)
    assert policy["reference_multiplier"] == 1.1
    assert policy["default_playback_intensity"] == 0.8

    assert main(["calibration", "preflight", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    Draft202012Validator(_schema("calibration_preflight.schema.json")).validate(
        report
    )


def test_wge2_schemas_compile() -> None:
    for name in (
        "exact_identity_receipt.schema.json",
        "motif_inspection_report.schema.json",
        "calibration_preflight.schema.json",
    ):
        Draft202012Validator.check_schema(_schema(name))
