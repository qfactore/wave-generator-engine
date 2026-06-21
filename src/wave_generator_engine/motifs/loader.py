import json
from pathlib import Path
from typing import Any

import numpy as np

from wave_generator_engine.config import EXPECTED_IDENTITY_COUNT
from wave_generator_engine.errors import ValidationFailure
from .archive import open_npz_read_only
from .authority import FrozenAuthority, resolve_authority
from .integrity import array_identity_hash, sha256_file, verify_file_hash
from .models import FrozenMotifRecord, MotifIdentityMetadata


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationFailure("Motif authority document must be an object")
    return value


class FrozenMotifBank:
    """Hash-gated immutable access to all authoritative frozen motifs."""

    def __init__(self, authority: FrozenAuthority) -> None:
        self.authority = authority
        self.pre_access_hash: str | None = None
        self.post_access_hash: str | None = None
        self._records: dict[str, FrozenMotifRecord] = {}
        self._order: tuple[str, ...] = ()
        self.identity_index_version = ""

    @classmethod
    def load(cls, interchange_dir: Path | None = None) -> "FrozenMotifBank":
        bank = cls(resolve_authority(interchange_dir))
        bank._load()
        return bank

    def _load(self) -> None:
        self.pre_access_hash = verify_file_hash(
            self.authority.archive_path, self.authority.expected_archive_hash
        )
        asset_manifest = _json(self.authority.asset_manifest_path)
        identity_index = _json(self.authority.identity_index_path)
        storage = _json(self.authority.storage_contract_path)
        stored = storage.get("stored_asset_form", {})
        if stored.get("representation") != "native_sampled_signed_waveform" or \
                stored.get("normalization_or_resampling_applied_to_stored_assets") is not False:
            raise ValidationFailure("Frozen storage convention is missing or ambiguous")
        if identity_index.get("authority_tier") != "tier_0" or \
                identity_index.get("motif_count") != EXPECTED_IDENTITY_COUNT:
            raise ValidationFailure("Identity index is not binding Tier 0 with 84 motifs")
        index_archive = identity_index.get("source_archive", {})
        if index_archive.get("expected_sha256") != self.pre_access_hash or \
                index_archive.get("verified_sha256") != self.pre_access_hash:
            raise ValidationFailure("Identity index archive hash does not match verified authority")
        if str(asset_manifest.get("archive_sha256", "")).removeprefix("sha256:") != \
                self.pre_access_hash or \
                asset_manifest.get("total_asset_count") != EXPECTED_IDENTITY_COUNT:
            raise ValidationFailure("Asset manifest archive binding is invalid")
        index_records = identity_index.get("motifs")
        if not isinstance(index_records, list) or len(index_records) != EXPECTED_IDENTITY_COUNT:
            raise ValidationFailure("Identity index structure is ambiguous")
        index_ids = [item.get("motif_id") for item in index_records]
        if any(not isinstance(item, str) for item in index_ids) or len(set(index_ids)) != len(index_ids):
            raise ValidationFailure("Identity index IDs are invalid or duplicated")
        manifest_records = asset_manifest.get("assets")
        ordered_ids = asset_manifest.get("ordered_final_asset_ids")
        if not isinstance(manifest_records, list) or not isinstance(ordered_ids, list):
            raise ValidationFailure("Asset manifest structure is ambiguous")
        if len(manifest_records) != EXPECTED_IDENTITY_COUNT or ordered_ids != index_ids:
            raise ValidationFailure("Manifest and identity index ordering disagree")
        by_id = {item.get("final_asset_id"): item for item in manifest_records}
        if len(by_id) != EXPECTED_IDENTITY_COUNT:
            raise ValidationFailure("Asset manifest motif IDs are duplicated")
        records: dict[str, FrozenMotifRecord] = {}
        with open_npz_read_only(self.authority.archive_path) as archive:
            if list(archive.files) != ordered_ids:
                raise ValidationFailure("Archive motif order differs from authority")
            if len(archive.files) != EXPECTED_IDENTITY_COUNT:
                raise ValidationFailure("Archive does not contain exactly 84 motifs")
            for position, (motif_id, index_record) in enumerate(zip(ordered_ids, index_records)):
                manifest_record = by_id.get(motif_id)
                if manifest_record is None or index_record.get("ordered_index") != position:
                    raise ValidationFailure("Motif record or source order is invalid")
                key = index_record.get("archive_key")
                if key != motif_id or manifest_record.get("final_array_key") != key:
                    raise ValidationFailure("Motif-to-archive key mapping is invalid")
                array = archive[key]
                if array.dtype.hasobject:
                    raise ValidationFailure("Object arrays are prohibited")
                shape = tuple(array.shape)
                dtype = str(array.dtype)
                if list(shape) != index_record.get("shape") or \
                        list(shape) != manifest_record.get("array_shape"):
                    raise ValidationFailure(f"Motif shape mismatch: {motif_id}")
                if dtype != index_record.get("dtype") or dtype != manifest_record.get("array_dtype"):
                    raise ValidationFailure(f"Motif dtype mismatch: {motif_id}")
                digest = array_identity_hash(array)
                expected = str(index_record.get("per_motif_sha256", "")).removeprefix("sha256:")
                manifest_expected = str(manifest_record.get("final_array_sha256", "")).removeprefix("sha256:")
                if not expected or expected != manifest_expected or digest != expected:
                    raise ValidationFailure(f"Per-motif identity hash mismatch: {motif_id}")
                if index_record.get("source_archive_sha256") != self.pre_access_hash:
                    raise ValidationFailure(f"Motif archive provenance mismatch: {motif_id}")
                samples = np.array(array, copy=True, order="K")
                samples.setflags(write=False)
                rate = index_record.get("sample_rate_hz")
                if not isinstance(rate, int) or rate <= 0:
                    raise ValidationFailure("Authoritative sample rate is missing")
                metadata = MotifIdentityMetadata(
                    motif_id=motif_id,
                    source_order=position,
                    shape=shape,
                    dtype=dtype,
                    sample_count=int(samples.size),
                    sample_rate_hz=rate,
                    duration_seconds=float(samples.size / rate),
                    source_hash=digest,
                    archive_hash=self.pre_access_hash,
                    authority_tier="tier_0",
                    provenance_references=(
                        "frozen_84_morphology_archive",
                        "frozen_morphology_asset_manifest",
                        "frozen_morphology_renderer_contract",
                        "frozen_motif_identity_index",
                    ),
                    read_only=not samples.flags.writeable,
                )
                records[motif_id] = FrozenMotifRecord(metadata, samples)
        self.post_access_hash = sha256_file(self.authority.archive_path)
        if self.post_access_hash != self.pre_access_hash:
            raise ValidationFailure("Frozen archive changed during read-only access")
        self._records = records
        self._order = tuple(ordered_ids)
        self.identity_index_version = str(identity_index.get("status", "unknown"))

    def __len__(self) -> int:
        return len(self._records)

    def ids(self) -> tuple[str, ...]:
        return self._order

    def get(self, motif_id: str) -> FrozenMotifRecord:
        try:
            return self._records[motif_id]
        except KeyError as exc:
            raise ValidationFailure(f"Unknown frozen motif ID: {motif_id}") from exc

    def records(self) -> tuple[FrozenMotifRecord, ...]:
        return tuple(self._records[item] for item in self._order)
