from dataclasses import dataclass


@dataclass(frozen=True)
class SessionSelection:
    """A declarative selection only; it cannot generate or trim content."""

    session_ids: tuple[int, ...] = ()
    all_seven: bool = False
    preview_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.all_seven and self.session_ids:
            raise ValueError("Choose explicit sessions or all seven, not both")
        if any(session < 1 or session > 7 for session in self.session_ids):
            raise ValueError("Session identifiers must be between 1 and 7")
        if self.preview_seconds is not None and self.preview_seconds <= 0:
            raise ValueError("Preview duration must be positive")
