from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import numpy as np


@contextmanager
def open_npz_read_only(path: Path) -> Iterator[Any]:
    with path.open("rb") as handle:
        with np.load(handle, allow_pickle=False) as archive:
            yield archive
