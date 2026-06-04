from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PASS_VALUES = {"pass", "approved", "manual_approved", "gate_passed"}
HARD_ENFORCEMENT_KEYS = {
    "route_selection",
    "retry_tax",
    "part_map",
    "identity_parts_contract",
    "movable_parts_contract",
    "action_component_plan",
    "part_consistency",
    "component_integrity",
    "lively_motion",
    "prop_action_contact",
    "adapter_selection",
    "tooncrafter_audit",
    "video_provider_audit",
    "ipadapter_import",
    "ipadapter_part_consistency",
}

SOURCE_ANIMATION_ROUTES = {
    "component_pseudo_rig_action_component_plan",
    "prop_action_component_route",
    "local_part_transform_or_masked_edit",
    "part_transform_with_local_hand_glasses_repair",
    "lora_ipadapter_or_component_rig_candidate",
}

ROUTE_SELECTION_FILENAMES = (
    "source_route_selection_report.json",
    "route_selection_report.json",
)


def read_json(path: str | Path, default: Any | None = None) -> Any:
    target = Path(path)
    if not target.exists():
        return default
    return json.loads(target.read_text(encoding="utf-8"))


def report_status(run_dir: str | Path, filename: str) -> str:
    payload = read_json(Path(run_dir) / filename, {})
    value = payload.get("status")
    return str(value).lower() if value is not None else "missing"


def read_first_json(run_dir: str | Path, filenames: tuple[str, ...]) -> tuple[str | None, dict[str, Any]]:
    run = Path(run_dir)
    for filename in filenames:
        path = run / filename
        if path.exists():
            return filename, read_json(path, {})
    return None, {}


def normalize_status(value: Any) -> str:
    return str(value).lower() if value is not None else "missing"


def route_selection_report(run_dir: str | Path) -> tuple[str | None, dict[str, Any]]:
    return read_first_json(run_dir, ROUTE_SELECTION_FILENAMES)


def route_requires_source_animation(route: str | None) -> bool:
    normalized = str(route or "").strip().lower().replace("-", "_")
    return normalized in SOURCE_ANIMATION_ROUTES or "source_animation" in normalized or "component_pseudo_rig" in normalized


def production_source_animation_route(run_dir: str | Path) -> bool:
    _, route_report = route_selection_report(run_dir)
    return (
        normalize_status(route_report.get("run_type")) == "production"
        and route_requires_source_animation(route_report.get("recommended_route"))
    )


def prop_action_route(run_dir: str | Path) -> bool:
    _, route_report = route_selection_report(run_dir)
    route = str(route_report.get("recommended_route", "")).strip().lower().replace("-", "_")
    action = str(route_report.get("action", "")).strip().lower().replace("-", "_")
    return route == "prop_action_component_route" or action.startswith("coin_flip_deal_nod")


def route_retry_enforcement_statuses(run_dir: str | Path) -> dict[str, str]:
    run = Path(run_dir)
    statuses: dict[str, str] = {}

    _, route_report = route_selection_report(run)
    route_status = normalize_status(route_report.get("status"))
    statuses["route_selection"] = route_status

    retry_report = read_json(run / "retry_tax_report.json", {})
    if not retry_report:
        statuses["retry_tax"] = "missing"
    elif retry_report.get("pivot_required") is True:
        statuses["retry_tax"] = "pivot_required"
    else:
        statuses["retry_tax"] = normalize_status(retry_report.get("status"))

    recommended_route = route_report.get("recommended_route")
    if route_requires_source_animation(recommended_route):
        for key, filename in (
            ("part_map", "part_map.json"),
            ("identity_parts_contract", "identity_parts_contract.json"),
            ("movable_parts_contract", "movable_parts_contract.json"),
            ("action_component_plan", "action_component_plan.json"),
        ):
            statuses[key] = "pass" if (run / filename).exists() else "missing"
        statuses["part_consistency"] = report_status(run, "part_consistency_report.json")
        statuses["component_integrity"] = report_status(run, "component_integrity_report.json")
        statuses["lively_motion"] = report_status(run, "lively_motion_report.json")
        if prop_action_route(run):
            statuses["prop_action_contact"] = report_status(run, "prop_action_contact_report.json")
    return statuses


def adapter_enforcement_statuses(run_dir: str | Path) -> dict[str, str]:
    run = Path(run_dir)
    statuses: dict[str, str] = {}
    adapter_report = read_json(run / "route_adapter_report.json", {})
    adapter = str(adapter_report.get("adapter", "")).lower()
    adapter_used = bool(adapter_report)
    if adapter_used:
        statuses["adapter_selection"] = normalize_status(adapter_report.get("status"))

    tooncrafter_used = adapter == "tooncrafter" or (run / "tooncrafter_import_report.json").exists()
    if tooncrafter_used:
        statuses["tooncrafter_audit"] = report_status(run, "interpolated_segment_audit.json")

    video_provider_used = adapter in {"animate_x_wan", "animatex", "wan_animate"} or (run / "animatex_import_report.json").exists()
    if video_provider_used:
        statuses["video_provider_audit"] = report_status(run, "video_provider_frame_audit.json")

    ipadapter_used = adapter == "ipadapter_comfyui" or (run / "ipadapter_part_repair_import_report.json").exists()
    if ipadapter_used:
        statuses["ipadapter_import"] = report_status(run, "ipadapter_part_repair_import_report.json")
        statuses["ipadapter_part_consistency"] = report_status(run, "part_consistency_report.json")
    return statuses


def production_enforcement_statuses(run_dir: str | Path) -> dict[str, str]:
    statuses = route_retry_enforcement_statuses(run_dir)
    statuses.update(adapter_enforcement_statuses(run_dir))
    return statuses


def freeze_manifest_path(run_dir: str | Path) -> Path:
    return Path(run_dir) / "keypose_freeze_manifest.json"


def has_freeze_manifest(run_dir: str | Path) -> bool:
    return freeze_manifest_path(run_dir).exists()


def freeze_prerequisite_statuses(run_dir: str | Path) -> dict[str, str]:
    statuses = {
        "identity": report_status(run_dir, "identity_feature_lock_report.json"),
        "action": report_status(run_dir, "action_validation_report.json"),
        "body_tail": report_status(run_dir, "body_tail_consistency_report.json"),
        "jitter": report_status(run_dir, "jitter_diagnostics.json"),
        "visual_stability": report_status(run_dir, "visual_stability_report.json"),
    }
    statuses.update(production_enforcement_statuses(run_dir))
    return statuses


def freeze_ready(run_dir: str | Path) -> tuple[bool, dict[str, str]]:
    statuses = freeze_prerequisite_statuses(run_dir)
    ok = all(value in PASS_VALUES for value in statuses.values())
    return ok, statuses


def require_freeze_gate(run_dir: str | Path, allow_unfrozen: bool = False) -> dict:
    run = Path(run_dir)
    manifest = freeze_manifest_path(run)
    if manifest.exists():
        return read_json(manifest, {})
    ok, statuses = freeze_ready(run)
    if allow_unfrozen and ok:
        return {
            "schema_version": "sofunny-unfrozen-manual-allow.v1",
            "status": "allowed_without_manifest",
            "reason": "all freeze prerequisite reports pass but manifest is missing",
            "statuses": statuses,
        }
    if allow_unfrozen:
        return {
            "schema_version": "sofunny-unfrozen-manual-allow.v1",
            "status": "allowed_with_failed_or_missing_reports",
            "reason": "explicit --allow-unfrozen override",
            "statuses": statuses,
        }
    raise SystemExit(
        "KEYPOSE_FREEZE_GATE blocks this GIF-stage operation. "
        f"Missing {manifest}. Run freeze_keyposes.py after provider preflight and keypose admission, "
        "or rerun with --allow-unfrozen only for an explicit diagnostic."
    )
