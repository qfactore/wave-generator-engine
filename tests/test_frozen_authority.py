import json
from pathlib import Path

import pytest

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.interchange.frozen_authority import (
    resolve_frozen_archive, validate_frozen_authority,
)


def test_correct_archive_hash_and_84_identities(interchange_root: Path) -> None:
    result = validate_frozen_authority(interchange_root)
    assert result.hash_matches
    assert result.identity_count == 84
    assert result.identities_unique


def test_archive_is_not_modified(interchange_root: Path) -> None:
    archive, _ = resolve_frozen_archive(interchange_root)
    before = archive.stat()
    validate_frozen_authority(interchange_root)
    after = archive.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)


def test_wrong_archive_hash_fails(authority_copy: Path) -> None:
    archive, _ = resolve_frozen_archive(authority_copy)
    archive.write_bytes(archive.read_bytes() + b"x")
    with pytest.raises(ValidationFailure, match="hash mismatch"):
        validate_frozen_authority(authority_copy)


def test_missing_archive_fails(authority_copy: Path) -> None:
    archive, _ = resolve_frozen_archive(authority_copy)
    archive.unlink()
    with pytest.raises(ValidationFailure, match="missing"):
        validate_frozen_authority(authority_copy)


@pytest.mark.parametrize("classification,tier,superseded", [
    ("blocked", "tier_0", None),
    ("reference", "tier_0", None),
    ("include", "tier_4", "newer_source"),
])
def test_non_current_source_cannot_be_selected(
    authority_copy: Path, classification: str, tier: str, superseded: str | None
) -> None:
    path = authority_copy / "manifests/source_artifact_manifest.json"
    data = json.loads(path.read_text())
    record = next(x for x in data["artifacts"] if x["id"] == "frozen_84_morphology_archive")
    record["classification_status"] = classification
    record["authority_tier"] = tier
    record["superseded_by"] = superseded
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationFailure):
        resolve_frozen_archive(authority_copy)


def test_wrong_identity_count_fails(authority_copy: Path) -> None:
    path = authority_copy / "bank/frozen_assets/frozen_motif_identity_index.json"
    data = json.loads(path.read_text())
    data["motifs"].pop()
    data["motif_count"] = 83
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationFailure, match="84"):
        validate_frozen_authority(authority_copy)


def test_duplicate_identity_fails(authority_copy: Path) -> None:
    path = authority_copy / "bank/frozen_assets/frozen_motif_identity_index.json"
    data = json.loads(path.read_text())
    data["motifs"][1]["motif_id"] = data["motifs"][0]["motif_id"]
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationFailure, match="duplicate"):
        validate_frozen_authority(authority_copy)


def test_ambiguous_identity_shape_fails(authority_copy: Path) -> None:
    path = authority_copy / "bank/frozen_assets/frozen_motif_identity_index.json"
    data = json.loads(path.read_text())
    data["motifs"] = {"records": data["motifs"]}
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationFailure, match="ambiguous"):
        validate_frozen_authority(authority_copy)
