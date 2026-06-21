import copy
import json
from pathlib import Path

import numpy as np
import pytest

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.motifs.authority import resolve_authority
from wave_generator_engine.motifs.integrity import array_identity_hash
from wave_generator_engine.motifs.loader import FrozenMotifBank


def _source_record(root: Path) -> tuple[Path, dict]:
    path = root / "manifests/source_artifact_manifest.json"
    data = json.loads(path.read_text())
    return path, data


def test_real_archive_loads_84_verified_motifs(real_motif_bank) -> None:
    assert len(real_motif_bank) == 84
    assert len(set(real_motif_bank.ids())) == 84
    assert real_motif_bank.pre_access_hash == real_motif_bank.post_access_hash
    assert all(item.metadata.source_order == index
               for index, item in enumerate(real_motif_bank.records()))


@pytest.mark.parametrize("classification", ["blocked", "reference", "archive", "unknown"])
def test_non_included_archive_source_rejected(
    motif_authority_copy: Path, classification: str
) -> None:
    path, data = _source_record(motif_authority_copy)
    record = next(item for item in data["artifacts"]
                  if item["id"] == "frozen_84_morphology_archive")
    record["classification_status"] = classification
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationFailure, match="not included"):
        resolve_authority(motif_authority_copy)


def test_superseded_source_rejected(motif_authority_copy: Path) -> None:
    path, data = _source_record(motif_authority_copy)
    record = next(item for item in data["artifacts"]
                  if item["id"] == "frozen_84_morphology_archive")
    record["superseded_by"] = "replacement"
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationFailure, match="superseded"):
        resolve_authority(motif_authority_copy)


def test_ambiguous_source_rejected(motif_authority_copy: Path) -> None:
    path, data = _source_record(motif_authority_copy)
    record = next(item for item in data["artifacts"]
                  if item["id"] == "frozen_84_morphology_archive")
    data["artifacts"].append(copy.deepcopy(record))
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationFailure, match="ambiguous"):
        resolve_authority(motif_authority_copy)


def test_missing_source_record_rejected(motif_authority_copy: Path) -> None:
    path, data = _source_record(motif_authority_copy)
    data["artifacts"] = [
        item for item in data["artifacts"]
        if item["id"] != "frozen_84_morphology_archive"
    ]
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationFailure, match="ambiguous"):
        resolve_authority(motif_authority_copy)


def test_missing_archive_fails(motif_authority_copy: Path) -> None:
    authority = resolve_authority(motif_authority_copy)
    authority.archive_path.unlink()
    with pytest.raises(ValidationFailure, match="missing"):
        FrozenMotifBank.load(motif_authority_copy)


def test_wrong_hash_fails_before_np_load(
    motif_authority_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    authority = resolve_authority(motif_authority_copy)
    authority.archive_path.write_bytes(authority.archive_path.read_bytes() + b"x")
    entered = False

    def forbidden_open(*args, **kwargs):
        nonlocal entered
        entered = True
        raise AssertionError("np.load path must not be entered")

    monkeypatch.setattr(
        "wave_generator_engine.motifs.loader.open_npz_read_only", forbidden_open
    )
    with pytest.raises(ValidationFailure, match="before waveform access"):
        FrozenMotifBank.load(motif_authority_copy)
    assert not entered


def test_allow_pickle_false_is_enforced(
    motif_authority_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    original = np.load

    def observed(*args, **kwargs):
        calls.append(kwargs.get("allow_pickle"))
        return original(*args, **kwargs)

    monkeypatch.setattr(np, "load", observed)
    FrozenMotifBank.load(motif_authority_copy)
    assert calls and set(calls) == {False}


def test_source_archive_not_copied_into_repository() -> None:
    root = Path(__file__).resolve().parents[1]
    files = [path for path in root.rglob("*")
             if path.is_file() and ".venv" not in path.parts]
    assert not [path for path in files if path.suffix == ".npz"]
    assert not [path for path in files if path.suffix == ".npy"]


def test_object_arrays_are_rejected() -> None:
    with pytest.raises(ValidationFailure, match="Object"):
        array_identity_hash(np.array([{"unsafe": True}], dtype=object))
