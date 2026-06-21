import json
import shutil
from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
INTERCHANGE_ROOT = ENGINE_ROOT.parent / "wave-gen-interchange"


@pytest.fixture
def interchange_root() -> Path:
    return INTERCHANGE_ROOT


@pytest.fixture
def authority_copy(tmp_path: Path, interchange_root: Path) -> Path:
    target = tmp_path / "wave-gen-interchange"
    shutil.copytree(interchange_root, target)
    manifest = json.loads(
        (target / "manifests/source_artifact_manifest.json").read_text()
    )
    record = next(
        item for item in manifest["artifacts"]
        if item["id"] == "frozen_84_morphology_archive"
    )
    source = (interchange_root / record["path"]).resolve()
    destination = (target / record["path"]).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return target
