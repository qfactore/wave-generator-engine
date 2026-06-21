class WGEError(RuntimeError):
    """Base fail-closed engine error."""


class DiscoveryError(WGEError):
    """Interchange discovery failed."""


class ValidationFailure(WGEError):
    """Authority validation failed."""


class GateClosedError(WGEError):
    """A blocked or unknown request was rejected."""

    def __init__(self, gate_id: str, error_code: str, message: str) -> None:
        self.gate_id = gate_id
        self.error_code = error_code
        super().__init__(f"{error_code}: {message}")
