from .registry import GateRegistry


def evaluate_request(registry: GateRegistry, request_id: str) -> None:
    registry.reject(request_id)
