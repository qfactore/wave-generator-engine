import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wave_generator_engine.config import EXPECTED_FROZEN_SHA256, EXPECTED_IDENTITY_COUNT
from wave_generator_engine.errors import ValidationFailure
from .loader import load_json

FROZEN_ARCHIVE_ID = "frozen_84_morphology_archive"


@dataclass(frozen=True)
class FrozenAuthorityResult:
    sha256: str
    hash_matches: bool
    identity_count: int
    identities_unique: bool
    archive_label: str = "tier-0-frozen-archive"


def resolve_frozen_archive(root: Path) -> tuple[Path, str]:
    sources = load_json(root / "manifests/source_artifact_manifest.json")
    hashes = load_json(root / "manifests/source_hashes.json")
    source_matches = [x for x in sources.get("artifacts", []) if x.get("id") == FROZEN_ARCHIVE_ID]
    hash_matches = [x for x in hashes.get("hashes", []) if x.get("artifact_id") == FROZEN_ARCHIVE_ID]
    if len(source_matches) != 1 or len(hash_matches) != 1:
        raise ValidationFailure("Frozen archive authority is ambiguous")
    source, binding = source_matches[0], hash_matches[0]
    if source.get("authority_tier") != "tier_0" or source.get("classification_status") != "include":
        raise ValidationFailure("Frozen archive is not included Tier 0 authority")
    if source.get("superseded_by") or source.get("conflicts"):
        raise ValidationFailure("Frozen archive source is superseded or conflicted")
    if binding.get("authority_tier") != "tier_0" or binding.get("binding") is not True:
        raise ValidationFailure("Frozen archive hash is not binding Tier 0 authority")
    if source.get("path") != binding.get("path"):
        raise ValidationFailure("Frozen archive manifest paths disagree")
    expected = binding.get("expected_value")
    if expected != EXPECTED_FROZEN_SHA256 or source.get("hash", {}).get("value") != expected:
        raise ValidationFailure("Frozen archive binding hash disagrees")
    path = (root / source["path"]).resolve()
    if not path.is_file():
        raise ValidationFailure("Frozen archive is missing")
    return path, expected


def _whole_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _identity_records(index: Any) -> list[dict[str, Any]]:
    if not isinstance(index, dict) or set(("motif_count", "motifs")) - index.keys():
        raise ValidationFailure("Frozen identity index has an ambiguous shape")
    motifs = index["motifs"]
    if not isinstance(motifs, list) or not all(isinstance(item, dict) for item in motifs):
        raise ValidationFailure("Frozen identity index has an ambiguous shape")
    return motifs


def validate_frozen_authority(root: Path) -> FrozenAuthorityResult:
    archive, expected = resolve_frozen_archive(root)
    digest = _whole_file_sha256(archive)
    if digest != expected:
        raise ValidationFailure("Frozen archive hash mismatch")
    index = load_json(root / "bank/frozen_assets/frozen_motif_identity_index.json")
    if index.get("authority_tier") != "tier_0":
        raise ValidationFailure("Frozen identity index is not Tier 0")
    motifs = _identity_records(index)
    ids = [item.get("motif_id") for item in motifs]
    if any(not isinstance(item, str) or not item for item in ids):
        raise ValidationFailure("Frozen identity index contains an invalid identity")
    if len(ids) != len(set(ids)):
        raise ValidationFailure("Frozen identity index contains duplicate identities")
    if index.get("motif_count") != len(ids) or len(ids) != EXPECTED_IDENTITY_COUNT:
        raise ValidationFailure("Frozen identity count must equal 84")
    return FrozenAuthorityResult(digest, True, len(ids), True)
