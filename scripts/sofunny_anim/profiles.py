from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[2]
PROFILES_DIR = SKILL_ROOT / "profiles"
DEFAULT_PROFILE = "sofunny"

REQUIRED_FIELDS = [
    "schema_version",
    "profile_name",
    "profile_type",
    "unknown_keys_policy",
    "default_canvas",
    "default_background",
    "default_keypose_count",
    "style_rules",
    "identity_features",
    "motion_defaults",
    "thresholds",
    "asset_paths",
]

ALLOWED_TOP_LEVEL_FIELDS = set(REQUIRED_FIELDS) | {"_profile_path"}
ALLOWED_PROFILE_TYPES = {"production", "generic"}
ALLOWED_UNKNOWN_KEYS_POLICIES = {"fail", "warn", "ignore"}
EXPECTED_SCHEMA_VERSION = "sofunny-profile.v1"

THRESHOLD_SCHEMA: dict[str, tuple[type, float | int | None, float | int | None]] = {
    "provider_preflight.green_tolerance": (int, 0, 255),
    "provider_preflight.max_bbox_bottom_range_px": ((int, float), 0, None),
    "provider_preflight.max_bbox_width_range_px": ((int, float), 0, None),
    "provider_preflight.max_bbox_height_range_px": ((int, float), 0, None),
    "provider_preflight.edge_margin_px": (int, 0, None),
    "jitter.max_bbox_bottom_range_px": ((int, float), 0, None),
    "jitter.max_anchor_center_x_range_px": ((int, float), 0, None),
    "visual_stability.max_bbox_top_range_px": ((int, float), 0, None),
    "visual_stability.max_bbox_height_range_px": ((int, float), 0, None),
    "visual_stability.max_bbox_width_range_px": ((int, float), 0, None),
    "visual_stability.max_top_centroid_x_range_px": ((int, float), 0, None),
    "visual_stability.max_mid_centroid_x_range_px": ((int, float), 0, None),
    "visual_stability.max_top_centroid_y_range_px": ((int, float), 0, None),
    "visual_stability.max_mid_centroid_y_range_px": ((int, float), 0, None),
    "visual_stability.max_alpha_area_range_ratio": ((int, float), 0, 1),
    "body_tail.max_bbox_width_range_px": ((int, float), 0, None),
    "body_tail.max_bbox_height_range_px": ((int, float), 0, None),
    "body_tail.max_alpha_area_ratio": ((int, float), 0, 1),
    "body_tail.min_right_margin_px": (int, 0, None),
    "body_tail.min_tail_region_width_px": (int, 0, None),
    "body_tail.min_tail_region_alpha_area": (int, 0, None),
    "body_tail.alpha_threshold": (int, 0, 255),
    "identity_consistency.min_pair_ssim": ((int, float), 0, 1),
    "identity_consistency.max_pair_color_distance": ((int, float), 0, 1),
    "identity_consistency.max_bbox_width_range_px": ((int, float), 0, None),
    "identity_consistency.max_bbox_height_range_px": ((int, float), 0, None),
    "identity_consistency.max_alpha_area_range_ratio": ((int, float), 0, 1),
    "identity_consistency.max_bbox_aspect_range": ((int, float), 0, None),
    "identity_consistency.min_reference_ssim": ((int, float), 0, 1),
}


def profile_path(profile: str | None = None) -> Path:
    value = profile or DEFAULT_PROFILE
    path = Path(value).expanduser()
    if path.exists():
        return path.resolve()
    if path.suffix != ".json":
        path = PROFILES_DIR / f"{value}.json"
    else:
        path = PROFILES_DIR / path.name
    return path.resolve()


def load_profile(profile: str | None = None) -> dict[str, Any]:
    path = profile_path(profile)
    if not path.exists():
        raise FileNotFoundError(f"profile not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["_profile_path"] = str(path)
    return data


def validate_profile_payload(profile: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    policy = profile.get("unknown_keys_policy", "fail")
    unknown = sorted(set(profile) - ALLOWED_TOP_LEVEL_FIELDS)
    if unknown and policy == "fail":
        failures.append("unknown top-level profile fields: " + ", ".join(unknown))
    for field in REQUIRED_FIELDS:
        if field not in profile:
            failures.append(f"missing required field: {field}")
    if profile.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        failures.append(f"schema_version must be {EXPECTED_SCHEMA_VERSION}")
    if profile.get("profile_type") not in ALLOWED_PROFILE_TYPES:
        failures.append(f"profile_type must be one of: {', '.join(sorted(ALLOWED_PROFILE_TYPES))}")
    if policy not in ALLOWED_UNKNOWN_KEYS_POLICIES:
        failures.append(f"unknown_keys_policy must be one of: {', '.join(sorted(ALLOWED_UNKNOWN_KEYS_POLICIES))}")
    if profile.get("profile_type") == "production" and policy != "fail":
        failures.append("production profile unknown_keys_policy must be fail")
    keyposes = profile.get("default_keypose_count", {})
    if not isinstance(keyposes, dict):
        failures.append("default_keypose_count must be an object")
    else:
        for key in ("smoke", "production"):
            if key not in keyposes:
                failures.append(f"default_keypose_count.{key} is required")
            elif not isinstance(keyposes[key], int) or keyposes[key] <= 0:
                failures.append(f"default_keypose_count.{key} must be a positive integer")
    if not isinstance(profile.get("style_rules", []), list):
        failures.append("style_rules must be a list")
    if not isinstance(profile.get("identity_features", []), list):
        failures.append("identity_features must be a list")
    motion_defaults = profile.get("motion_defaults", {})
    if not isinstance(motion_defaults, dict):
        failures.append("motion_defaults must be an object")
    else:
        validate_motion_defaults(motion_defaults, failures)
    thresholds = profile.get("thresholds", {})
    if not isinstance(thresholds, dict):
        failures.append("thresholds must be an object")
    else:
        validate_thresholds(thresholds, motion_defaults if isinstance(motion_defaults, dict) else {}, failures)
    if not isinstance(profile.get("asset_paths", {}), dict):
        failures.append("asset_paths must be an object")
    canvas = profile.get("default_canvas")
    if not isinstance(canvas, str) or "x" not in canvas.lower():
        failures.append("default_canvas must be WIDTHxHEIGHT")
    background = profile.get("default_background")
    if not isinstance(background, str) or not background.startswith("#") or len(background) != 7:
        failures.append("default_background must be #RRGGBB")
    return failures


def validate_motion_defaults(motion_defaults: dict[str, Any], failures: list[str]) -> None:
    default_action = motion_defaults.get("default_action")
    actions = motion_defaults.get("actions")
    if not isinstance(default_action, str) or not default_action:
        failures.append("motion_defaults.default_action must be a non-empty string")
    if not isinstance(motion_defaults.get("duration_ms"), int) or motion_defaults.get("duration_ms", 0) <= 0:
        failures.append("motion_defaults.duration_ms must be a positive integer")
    if not isinstance(actions, dict) or not actions:
        failures.append("motion_defaults.actions must be a non-empty object")
        return
    if default_action and default_action not in actions:
        failures.append("motion_defaults.default_action must exist in motion_defaults.actions")
    for action_name, contract in actions.items():
        if not isinstance(contract, dict):
            failures.append(f"motion_defaults.actions.{action_name} must be an object")
            continue
        if not isinstance(contract.get("requires_manual_phase_review"), bool):
            failures.append(f"motion_defaults.actions.{action_name}.requires_manual_phase_review must be boolean")
        phase_keys = sorted(key for key in contract if key.startswith("phases_"))
        if not phase_keys:
            failures.append(f"motion_defaults.actions.{action_name} must define at least one phases_N list")
        phase_names: set[str] = set()
        for key in phase_keys:
            phases = contract.get(key)
            if not isinstance(phases, list) or not phases or not all(isinstance(item, str) and item for item in phases):
                failures.append(f"motion_defaults.actions.{action_name}.{key} must be a non-empty string list")
            else:
                phase_names.update(phases)
        semantics = contract.get("phase_semantics")
        if not isinstance(semantics, dict) or not semantics:
            failures.append(f"motion_defaults.actions.{action_name}.phase_semantics must be a non-empty object")
        else:
            missing_semantics = sorted(name for name in phase_names if not isinstance(semantics.get(name), str) or not semantics.get(name))
            if missing_semantics:
                failures.append(f"motion_defaults.actions.{action_name}.phase_semantics missing phases: {', '.join(missing_semantics)}")
        required_changes = contract.get("required_visual_changes")
        if not isinstance(required_changes, list) or not required_changes or not all(isinstance(item, str) and item for item in required_changes):
            failures.append(f"motion_defaults.actions.{action_name}.required_visual_changes must be a non-empty string list")
        global_checks = contract.get("required_global_checks")
        if not isinstance(global_checks, list) or not global_checks or not all(isinstance(item, str) and item for item in global_checks):
            failures.append(f"motion_defaults.actions.{action_name}.required_global_checks must be a non-empty string list")


def validate_thresholds(thresholds: dict[str, Any], motion_defaults: dict[str, Any], failures: list[str]) -> None:
    for dotted, (expected_type, min_value, max_value) in THRESHOLD_SCHEMA.items():
        value = get_path({"thresholds": thresholds}, f"thresholds.{dotted}", None)
        if value is None:
            failures.append(f"thresholds.{dotted} is required")
            continue
        if not isinstance(value, expected_type):
            failures.append(f"thresholds.{dotted} must be numeric type {expected_type}")
            continue
        if isinstance(value, bool):
            failures.append(f"thresholds.{dotted} must not be boolean")
            continue
        if min_value is not None and value < min_value:
            failures.append(f"thresholds.{dotted} must be >= {min_value}")
        if max_value is not None and value > max_value:
            failures.append(f"thresholds.{dotted} must be <= {max_value}")

    actions = motion_defaults.get("actions", {}) if isinstance(motion_defaults, dict) else {}
    action_thresholds = thresholds.get("action_contract", {})
    if not isinstance(action_thresholds, dict):
        failures.append("thresholds.action_contract must be an object")
        return
    for action_name in actions:
        action_values = action_thresholds.get(action_name)
        if action_values is None:
            continue
        if not isinstance(action_values, dict):
            failures.append(f"thresholds.action_contract.{action_name} must be an object")
            continue
        for key, value in action_values.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                failures.append(f"thresholds.action_contract.{action_name}.{key} must be numeric")
            elif value < 0:
                failures.append(f"thresholds.action_contract.{action_name}.{key} must be >= 0")


def validate_profile(profile: str | None = None) -> tuple[dict[str, Any], list[str]]:
    data = load_profile(profile)
    return data, validate_profile_payload(data)


def get_path(profile: dict[str, Any], dotted: str, default: Any = None) -> Any:
    current: Any = profile
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def coalesce(cli_value: Any, profile: dict[str, Any], dotted: str, built_in: Any) -> Any:
    if cli_value is not None:
        return cli_value
    value = get_path(profile, dotted, None)
    return built_in if value is None else value


def keypose_count(profile: dict[str, Any], mode: str, built_in: int) -> int:
    value = get_path(profile, f"default_keypose_count.{mode}", None)
    return built_in if value is None else int(value)


def action_config(profile: dict[str, Any], action: str | None = None) -> dict[str, Any]:
    action_name = action or get_path(profile, "motion_defaults.default_action", "")
    return get_path(profile, f"motion_defaults.actions.{action_name}", {})


def phases_for(profile: dict[str, Any], frame_count: int, action: str | None = None, fallback: list[str] | None = None) -> list[str]:
    config = action_config(profile, action)
    value = config.get(f"phases_{frame_count}")
    if isinstance(value, list) and len(value) == frame_count:
        return [str(item) for item in value]
    if fallback and len(fallback) == frame_count:
        return fallback
    return [f"phase_{index:02d}" for index in range(frame_count)]


def parse_hex_color(value: str) -> tuple[int, int, int]:
    raw = value.strip()
    if not raw.startswith("#") or len(raw) != 7:
        raise ValueError(f"color must be #RRGGBB: {value}")
    return tuple(int(raw[index : index + 2], 16) for index in (1, 3, 5))
