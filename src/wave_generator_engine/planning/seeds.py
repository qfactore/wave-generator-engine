import hashlib
import random


def derive_seed(root_seed: int, *labels: str) -> int:
    payload = ":".join((str(root_seed), *labels)).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def local_rng(root_seed: int, *labels: str) -> random.Random:
    return random.Random(derive_seed(root_seed, *labels))
