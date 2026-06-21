from enum import StrEnum


class TrustLevel(StrEnum):
    EXACT = "exact"
    BOUNDED = "bounded"
    EXPERIMENTAL = "experimental"
    RESEARCH = "research"
