import json
from pathlib import Path

import pytest

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.motifs.loader import FrozenMotifBank


def _index(root: Path) -> tuple[Path, dict]:
    path = root / "bank/frozen_assets/frozen_motif_identity_index.json"
    return path, json.loads(path.read_text())


def test_identity_metadata_matches_archive(real_motif_bank) -> None:
    for position, record in enumerate(real_motif_bank.records()):
        assert record.metadata.source_order == position
        assert record.metadata.motif_id == real_motif_bank.ids()[position]
        assert record.metadata.shape == record.samples.shape
        assert record.metadata.dtype == str(record.samples.dtype)
        assert record.metadata.sample_count == record.samples.size
        assert record.metadata.source_hash


@pytest.mark.parametrize("mutation,match", [
    (lambda d: d["motifs"].pop(), "structure"),
    (lambda d: d["motifs"].append(dict(d["motifs"][0])), "structure"),
    (lambda d: d["motifs"][1].update(motif_id=d["motifs"][0]["motif_id"]), "duplicated"),
    (lambda d: d["motifs"][0].update(ordered_index=2), "source order"),
    (lambda d: d["motifs"][0].update(archive_key="missing"), "key mapping"),
    (lambda d: d["motifs"][0].update(shape=[1]), "shape mismatch"),
    (lambda d: d["motifs"][0].update(dtype="float64"), "dtype mismatch"),
    (lambda d: d["motifs"][0].update(per_motif_sha256="0" * 64), "identity hash"),
    (lambda d: d["motifs"][0].update(source_archive_sha256="0" * 64), "provenance"),
])
def test_identity_index_corruption_fails(
    motif_authority_copy: Path, mutation, match: str
) -> None:
    path, data = _index(motif_authority_copy)
    mutation(data)
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationFailure, match=match):
        FrozenMotifBank.load(motif_authority_copy)


def test_ambiguous_index_shape_fails(motif_authority_copy: Path) -> None:
    path, data = _index(motif_authority_copy)
    data["motifs"] = {"records": data["motifs"]}
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationFailure, match="structure"):
        FrozenMotifBank.load(motif_authority_copy)
