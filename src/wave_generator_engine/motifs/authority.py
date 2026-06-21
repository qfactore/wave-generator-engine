import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wave_generator_engine.config import EXPECTED_FROZEN_SHA256, EXPECTED_IDENTITY_COUNT
from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.interchange.discovery import discover_interchange
from wave_generator_engine.config import ENGINE_ROOT
from .integrity import sha256_file

ARCHIVE_ID = "frozen_84_morphology_archive"
ASSET_MANIFEST_ID = "frozen_morphology_asset_manifest"
STORAGE_CONTRACT_ID = "frozen_morphology_renderer_contract"


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationFailure(f"Authority document is unreadable: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValidationFailure("Authority document must be an object")
    return value


def _included_tier0(manifest: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    matches = [item for item in manifest.get("artifacts", []) if item.get("id") == artifact_id]
    if len(matches) != 1:
        raise ValidationFailure(f"Authority source is ambiguous: {artifact_id}")
    record = matches[0]
    if record.get("classification_status") != "include":
        raise ValidationFailure(f"Authority source is not included: {artifact_id}")
    if record.get("authority_tier") != "tier_0":
        raise ValidationFailure(f"Authority source is not Tier 0: {artifact_id}")
    if record.get("superseded_by") or record.get("conflicts"):
        raise ValidationFailure(f"Authority source is superseded or conflicted: {artifact_id}")
    if not isinstance(record.get("path"), str):
        raise ValidationFailure(f"Authority source path is missing: {artifact_id}")
    return record


def _safe_path(root: Path, recorded: str) -> Path:
    if "final_test" in recorded.casefold():
        raise ValidationFailure("Blocked final-test material cannot be resolved")
    return (root / recorded).resolve()


@dataclass(frozen=True)
class FrozenAuthority:
    interchange_root: Path
    archive_path: Path
    asset_manifest_path: Path
    storage_contract_path: Path
    identity_index_path: Path
    expected_archive_hash: str
    classification_status: str = "include"
    authority_tier: str = "tier_0"


def resolve_authority(interchange_dir: Path | None = None) -> FrozenAuthority:
    root = discover_interchange(ENGINE_ROOT, interchange_dir)
    sources = _json(root / "manifests/source_artifact_manifest.json")
    hashes = _json(root / "manifests/source_hashes.json")
    bank = _json(root / "bank/frozen_assets/frozen_asset_manifest.json")
    archive = _included_tier0(sources, ARCHIVE_ID)
    asset = _included_tier0(sources, ASSET_MANIFEST_ID)
    storage = _included_tier0(sources, STORAGE_CONTRACT_ID)
    bindings = [item for item in hashes.get("hashes", []) if item.get("artifact_id") == ARCHIVE_ID]
    if len(bindings) != 1 or bindings[0].get("binding") is not True:
        raise ValidationFailure("Frozen archive binding is missing or ambiguous")
    if bindings[0].get("path") != archive.get("path") or \
            bindings[0].get("authority_tier") != "tier_0":
        raise ValidationFailure("Frozen archive source and binding records disagree")
    expected_values = {
        str(archive.get("hash", {}).get("value", "")).removeprefix("sha256:"),
        str(bindings[0].get("expected_value", "")).removeprefix("sha256:"),
        str(bank.get("archive", {}).get("expected_sha256", "")).removeprefix("sha256:"),
    }
    if expected_values != {EXPECTED_FROZEN_SHA256}:
        raise ValidationFailure("Frozen archive authority hashes disagree")
    if bank.get("archive", {}).get("asset_count") != EXPECTED_IDENTITY_COUNT:
        raise ValidationFailure("Frozen asset bank count is not 84")
    authority = FrozenAuthority(
        interchange_root=root,
        archive_path=_safe_path(root, archive["path"]),
        asset_manifest_path=_safe_path(root, asset["path"]),
        storage_contract_path=_safe_path(root, storage["path"]),
        identity_index_path=root / "bank/frozen_assets/frozen_motif_identity_index.json",
        expected_archive_hash=EXPECTED_FROZEN_SHA256,
    )
    for record, path in ((asset, authority.asset_manifest_path), (storage, authority.storage_contract_path)):
        if sha256_file(path) != str(record["hash"]["value"]).removeprefix("sha256:"):
            raise ValidationFailure("Referenced authority document hash mismatch")
    return authority
