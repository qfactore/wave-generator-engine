from enum import StrEnum


class ProfileStatus(StrEnum):
    RESERVED = "reserved"
    PRESET_LOCKED = "preset_locked"
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
    DEPRECATED = "deprecated"
    INVALID = "invalid"
