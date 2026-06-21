import hashlib
from pathlib import Path

import numpy as np

from wave_generator_engine.errors import ValidationFailure


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ValidationFailure("Frozen archive is missing")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file_hash(path: Path, expected: str) -> str:
    actual = sha256_file(path)
    if actual != expected:
        raise ValidationFailure("Frozen archive hash mismatch before waveform access")
    return actual


def array_identity_hash(array: np.ndarray) -> str:
    if array.dtype.hasobject:
        raise ValidationFailure("Object arrays are prohibited")
    contiguous = np.ascontiguousarray(array)
    digest = hashlib.sha256()
    digest.update(str(contiguous.dtype).encode("utf-8"))
    digest.update(str(contiguous.shape).encode("utf-8"))
    digest.update(contiguous.tobytes())
    return digest.hexdigest()
