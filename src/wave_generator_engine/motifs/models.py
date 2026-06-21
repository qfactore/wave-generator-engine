from dataclasses import asdict, dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class MotifIdentityMetadata:
    motif_id: str
    source_order: int
    shape: tuple[int, ...]
    dtype: str
    sample_count: int
    sample_rate_hz: int
    duration_seconds: float
    source_hash: str
    archive_hash: str
    authority_tier: str
    provenance_references: tuple[str, ...]
    read_only: bool

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["shape"] = list(self.shape)
        value["provenance_references"] = list(self.provenance_references)
        return value


@dataclass(frozen=True)
class FrozenMotifRecord:
    metadata: MotifIdentityMetadata
    samples: np.ndarray

    def diagnostic_copy(self) -> tuple[np.ndarray, dict[str, Any]]:
        return np.array(self.samples, copy=True), {
            "authoritative": False,
            "label": "detached_diagnostic_copy",
            "may_replace_exact_identity": False,
            "production_source": False,
        }


@dataclass(frozen=True)
class ExactIdentityReceipt:
    motif_id: str
    archive_hash: str
    motif_hash: str
    identity_index_version: str
    operations: tuple[str, ...]
    exact_bypass: bool
    randomness_used: bool
    transform_path_entered: bool
    source_dtype: str
    source_shape: tuple[int, ...]
    result_dtype: str
    result_shape: tuple[int, ...]
    bitwise_equal: bool
    read_only: bool
    provenance_references: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["operations"] = list(self.operations)
        value["source_shape"] = list(self.source_shape)
        value["result_shape"] = list(self.result_shape)
        value["provenance_references"] = list(self.provenance_references)
        return value
