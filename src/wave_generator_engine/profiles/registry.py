from pathlib import Path

from .library import load_profile_registry


def validate_profile_scaffold(engine_root: Path) -> None:
    profiles = engine_root / "profiles"
    for name in ("presets", "active", "archived"):
        if not (profiles / name).is_dir():
            raise ValueError(f"Missing profile directory: {name}")
    data = load_profile_registry(profiles / "registry.json")
    source_ids = {item["id"] for item in data["source_profiles"]}
    if source_ids != {"x_alpha_standard_v1"}:
        raise ValueError("WGE-0 must reserve exactly one source profile")
    source = data["source_profiles"][0]
    if source["executable"] is not False or source["implementation_phase"] != "WGE-1":
        raise ValueError("Reserved source profile must remain non-executable")
    presets = data["delivery_presets"]
    if presets["x_alpha25"]["source_profile_id"] != presets["x_alpha45"]["source_profile_id"]:
        raise ValueError("X-Alpha delivery presets must share one source profile")
