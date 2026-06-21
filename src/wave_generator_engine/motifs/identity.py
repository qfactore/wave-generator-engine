from typing import Any

import numpy as np

from wave_generator_engine.errors import ValidationFailure
from .loader import FrozenMotifBank
from .models import ExactIdentityReceipt, FrozenMotifRecord


class ExactIdentityAccess:
    """Exact identity is a direct immutable lookup, never an operation pipeline."""

    def __init__(self, bank: FrozenMotifBank) -> None:
        self._bank = bank

    def access(self, motif_id: str, **parameters: Any) -> tuple[FrozenMotifRecord, ExactIdentityReceipt]:
        if parameters:
            raise ValidationFailure("Exact identity access accepts no transform parameters")
        source = self._bank.get(motif_id)
        result = source.samples
        receipt = ExactIdentityReceipt(
            motif_id=motif_id,
            archive_hash=source.metadata.archive_hash,
            motif_hash=source.metadata.source_hash,
            identity_index_version=self._bank.identity_index_version,
            operations=(),
            exact_bypass=True,
            randomness_used=False,
            transform_path_entered=False,
            source_dtype=source.metadata.dtype,
            source_shape=source.metadata.shape,
            result_dtype=str(result.dtype),
            result_shape=tuple(result.shape),
            bitwise_equal=bool(np.array_equal(result, source.samples, equal_nan=True)),
            read_only=not result.flags.writeable,
            provenance_references=source.metadata.provenance_references,
        )
        return source, receipt
