#!/usr/bin/env python3
"""Validate action-specific SoFunny animation contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops

from sofunny_anim.profiles import get_path, load_profile, phases_for as profile_phases_for


SMALL_JOG_PHASES = [
    "left_contact_down",
    "left_push_off",
    "flight_passing_left_to_right",
    "right_contact_down",
    "right_push_off",
    "flight_recover_to_left_contact",
]

COIN_FLIP_DEAL_NOD_PHASES = [
    "ready",
    "anticipation",
    "toss_release",
    "coin_rise",
    "coin_peak",
    "deal_nod_down",
    "catch_receive",
    "present",
    "settle",
    "loop_return",
]

COIN_REQUIRED_GROUPS = {
    "head",
    "torso",
    "arm",
    "leg",
    "tail",
    "coin_prop",
}

TAIL_WAVE_REQUIRED_PHASE_KEYWORDS = [
    "idle",
    "anticipation",
    "tail",
    "wave",
    "peak",
    "settle",
    "loop",
]


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    return image.convert("RGBA").getbbox()


def lower_body_crop(image: Image.Image) -> Image.Image | None:
    rgba = image.convert("RGBA")
    bbox = alpha_bbox(rgba)
    if bbox is None:
        return None
    left, top, right, bottom = bbox
    height = bottom - top
    # Exclude top/body/head and focus on lower body. Keep a margin wide enough to include legs.
    lower_top = bottom - max(24, int(height * 0.32))
    crop = rgba.crop((left, lower_top, right, bottom))
    # Ignore soft shadow/motion accents by dropping low alpha pixels.
    alpha = crop.getchannel("A")
    mask = Image.new("L", crop.size, 0)
    src = alpha.load()
    dst = mask.load()
    for y in range(crop.height):
        for x in range(crop.width):
            if src[x, y] >= 96:
                dst[x, y] = 255
    normalized = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    normalized.putalpha(mask)
    return normalized


def lower_body_diversity(frames: list[Image.Image]) -> dict:
    crops = [lower_body_crop(frame) for frame in frames]
    valid = [crop for crop in crops if crop is not None]
    if len(valid) < 2:
        return {"pair_count": 0, "max_delta": 0, "mean_delta": 0, "deltas": []}

    deltas: list[int] = []
    # Resize to same box for coarse pose-diversity comparison.
    max_w = max(crop.width for crop in valid)
    max_h = max(crop.height for crop in valid)
    normalized = []
    for crop in valid:
        canvas = Image.new("RGBA", (max_w, max_h), (0, 0, 0, 0))
        canvas.alpha_composite(crop, ((max_w - crop.width) // 2, max_h - crop.height))
        normalized.append(canvas)
    for a, b in zip(normalized, normalized[1:]):
        diff = ImageChops.difference(a.getchannel("A"), b.getchannel("A"))
        deltas.append(sum(1 for px in diff.getdata() if px > 32))
    return {
        "pair_count": len(deltas),
        "max_delta": max(deltas) if deltas else 0,
        "mean_delta": round(sum(deltas) / len(deltas), 2) if deltas else 0,
        "deltas": deltas,
    }


def part_group(part_name: str) -> str:
    name = str(part_name).lower()
    if "coin" in name and "prop" in name:
        return "coin_prop"
    if "head" in name or "face" in name or "eye" in name or "glasses" in name:
        return "head"
    if "torso" in name or "body" in name or "trunk" in name:
        if name == "full_character":
            return "full_character"
        return "torso"
    if "arm" in name or "hand" in name:
        return "arm"
    if "leg" in name or "foot" in name:
        return "leg"
    if "tail" in name:
        return "tail"
    return "other"


def phase_names(action_plan: dict) -> list[str]:
    return [str(phase.get("name", "")).lower() for phase in action_plan.get("phases", []) if isinstance(phase, dict)]


def transform_part_groups(action_plan: dict) -> set[str]:
    groups: set[str] = set()
    for phase in action_plan.get("phases", []):
        if not isinstance(phase, dict):
            continue
        for part in (phase.get("transforms") or {}):
            groups.add(part_group(part))
    return groups


def part_map_groups(part_map: dict) -> set[str]:
    return {part_group(entry.get("name", "")) for entry in part_map.get("parts", []) if isinstance(entry, dict)}


def has_required_visual_change(action_plan: dict, keywords: list[str]) -> bool:
    text = " ".join(
        str(phase.get("required_visual_change", "")).lower()
        for phase in action_plan.get("phases", [])
        if isinstance(phase, dict)
    )
    return any(keyword in text for keyword in keywords)


def validate_coin_flip_deal_nod(run_dir: Path, profile: dict, action: str) -> dict:
    manifest = load_json(run_dir / "sofunny-run-manifest.json")
    candidate = load_json(run_dir / "candidate_manifest.json")
    route_report = load_json(run_dir / "source_route_selection_report.json") or load_json(run_dir / "route_selection_report.json")
    part_map = load_json(run_dir / "part_map.json")
    action_plan = load_json(run_dir / "action_component_plan.json")
    part_consistency = load_json(run_dir / "part_consistency_report.json")
    component_integrity = load_json(run_dir / "component_integrity_report.json")
    lively_motion = load_json(run_dir / "lively_motion_report.json")
    prop_contact = load_json(run_dir / "prop_action_contact_report.json")

    failures: list[str] = []
    warnings: list[str] = []
    route = (
        route_report.get("recommended_route")
        or candidate.get("route")
        or manifest.get("generation", {}).get("route")
        or ""
    )
    route_action = route_report.get("action")
    if route_action and not str(route_action).startswith("coin_flip_deal_nod"):
        failures.append(f"route_selection_report.action must be coin_flip_deal_nod*, got {route_action}")
    if route != "prop_action_component_route":
        failures.append(f"coin_flip_deal_nod requires prop_action_component_route, got {route or 'missing'}")

    map_groups = part_map_groups(part_map)
    transform_groups = transform_part_groups(action_plan)
    available_groups = map_groups | transform_groups
    missing_groups = sorted(COIN_REQUIRED_GROUPS - available_groups)
    if missing_groups:
        failures.append("missing required component groups: " + ", ".join(missing_groups))
    if available_groups.issubset({"full_character", "coin_prop"}):
        failures.append("full_character + coin_prop only is not enough for coin_flip_deal_nod production")

    names = phase_names(action_plan)
    missing_phases = [
        phase for phase in COIN_FLIP_DEAL_NOD_PHASES
        if not any(phase in name for name in names)
    ]
    if missing_phases:
        failures.append("missing required coin action phases: " + ", ".join(missing_phases))

    for field in [
        "body_y",
        "head_y",
        "head_rotation",
        "arm_rotation",
        "leg_phase",
        "tail_rotation",
        "tail_lag",
        "squash_stretch",
    ]:
        if any(isinstance(phase, dict) and field not in phase for phase in action_plan.get("phases", [])):
            failures.append(f"action_component_plan phases must include {field}")
            break

    if not has_required_visual_change(action_plan, ["coin", "toss", "catch", "present", "release"]):
        failures.append("required_visual_change must describe coin release/rise/catch/present semantics")
    if part_consistency.get("status") != "pass":
        failures.append(f"part_consistency_report.status must be pass, got {part_consistency.get('status', 'missing')}")
    if component_integrity.get("status") != "pass":
        failures.append(f"component_integrity_report.status must be pass, got {component_integrity.get('status', 'missing')}")
    if lively_motion.get("status") != "pass":
        failures.append(f"lively_motion_report.status must be pass, got {lively_motion.get('status', 'missing')}")
    if prop_contact.get("status") != "pass":
        failures.append(f"prop_action_contact_report.status must be pass, got {prop_contact.get('status', 'missing')}")

    report = {
        "schema_version": "sofunny-action-validation.v2",
        "action": action,
        "profile": profile.get("profile_name"),
        "status": "fail" if failures else "pass",
        "route": route,
        "route_action": route_action,
        "required_route": "prop_action_component_route",
        "required_phases": COIN_FLIP_DEAL_NOD_PHASES,
        "required_component_groups": sorted(COIN_REQUIRED_GROUPS),
        "present_component_groups": sorted(available_groups),
        "part_consistency_status": part_consistency.get("status", "missing"),
        "component_integrity_status": component_integrity.get("status", "missing"),
        "lively_motion_status": lively_motion.get("status", "missing"),
        "prop_action_contact_status": prop_contact.get("status", "missing"),
        "failures": failures,
        "warnings": warnings,
        "notes": [
            "This action cannot be approved as a full_character plus coin_prop transform.",
            "It needs component-level head/torso/arm/leg/tail/coin acting before freeze.",
        ],
    }
    return report


def transform_ranges(action_plan: dict) -> dict[str, dict[str, float]]:
    values: dict[str, dict[str, list[float]]] = {}
    for phase in action_plan.get("phases", []):
        for part, transform in (phase.get("transforms") or {}).items():
            group = part_group(part)
            bucket = values.setdefault(group, {"x": [], "y": [], "rotate": []})
            translate = transform.get("translate", [0, 0])
            if isinstance(translate, list) and len(translate) >= 2:
                bucket["x"].append(float(translate[0]))
                bucket["y"].append(float(translate[1]))
            bucket["rotate"].append(float(transform.get("rotate", 0) or 0))
    out: dict[str, dict[str, float]] = {}
    for group, bucket in values.items():
        out[group] = {
            key: round(max(items) - min(items), 3) if items else 0.0
            for key, items in bucket.items()
        }
    return out


def validate_tail_wave_greeting(run_dir: Path, profile: dict, action: str) -> dict:
    route_report = load_json(run_dir / "source_route_selection_report.json") or load_json(run_dir / "route_selection_report.json")
    action_plan = load_json(run_dir / "action_component_plan.json")
    lively_motion = load_json(run_dir / "lively_motion_report.json")
    ranges = transform_ranges(action_plan)
    names = phase_names(action_plan)
    failures: list[str] = []
    warnings: list[str] = []
    route = route_report.get("recommended_route", "")

    allowed_routes = {"provider_keypose_candidate", "clean_layer_component_route", "component_pseudo_rig_action_component_plan"}
    if route and route not in allowed_routes:
        failures.append(f"tail wave greeting requires provider keyposes or clean layer component route, got {route}")
    if route == "component_pseudo_rig_action_component_plan":
        component_integrity = load_json(run_dir / "component_integrity_report.json")
        if component_integrity.get("status") != "pass":
            failures.append("component pseudo-rig for tail wave greeting requires clean component_integrity_report.status pass")
    if len(action_plan.get("phases", [])) < 8:
        failures.append("tail wave greeting requires at least 8 component phases")
    missing_keywords = [keyword for keyword in TAIL_WAVE_REQUIRED_PHASE_KEYWORDS if not any(keyword in name for name in names)]
    if missing_keywords:
        failures.append("missing tail wave phase keywords: " + ", ".join(missing_keywords))
    if ranges.get("tail", {}).get("rotate", 0.0) < 18.0:
        failures.append("tail rotation range must be at least 18 degrees for tail wave greeting")
    if ranges.get("arm", {}).get("rotate", 0.0) < 25.0:
        failures.append("greeting arm rotation range must be at least 25 degrees")
    if max(ranges.get("head", {}).get("y", 0.0), ranges.get("head", {}).get("rotate", 0.0)) < 2.0:
        failures.append("head follow must be readable for tail wave greeting")
    if lively_motion and lively_motion.get("status") != "pass":
        failures.append(f"lively_motion_report.status must be pass, got {lively_motion.get('status', 'missing')}")

    return {
        "schema_version": "sofunny-action-validation.v2",
        "action": action,
        "profile": profile.get("profile_name"),
        "status": "fail" if failures else "pass",
        "route": route,
        "required_route": "provider_keypose_candidate_or_clean_layer_component_route",
        "transform_ranges": ranges,
        "required_phase_keywords": TAIL_WAVE_REQUIRED_PHASE_KEYWORDS,
        "lively_motion_status": lively_motion.get("status", "missing") if lively_motion else "missing",
        "failures": failures,
        "warnings": warnings,
        "notes": [
            "Legs are grounded support for this action; tail wave and greeting arm are the primary readable motion.",
            "Do not expand weak keyposes to 40 frames before tail and arm motion are readable.",
        ],
    }


def validate_catch_falling_petal(run_dir: Path, profile: dict, action: str) -> dict:
    route_report = load_json(run_dir / "source_route_selection_report.json") or load_json(run_dir / "route_selection_report.json")
    action_plan = load_json(run_dir / "action_component_plan.json")
    manual_override = load_json(run_dir / "manual_route_override.json")
    part_consistency = load_json(run_dir / "part_consistency_report.json")
    component_integrity = load_json(run_dir / "component_integrity_report.json")
    provider_preflight = load_json(run_dir / "provider_preflight_report.json")
    failures: list[str] = []
    warnings: list[str] = []
    route = route_report.get("recommended_route") or route_report.get("proposed_route") or action_plan.get("route") or ""

    allowed_routes = {"provider_keypose_candidate", "local_redraw_keypose_candidate", "clean_layer_component_route"}
    if route not in allowed_routes:
        failures.append(f"catch_falling_petal requires provider/local-redraw keypose candidate or clean component layers, got {route or 'missing'}")
    if route in {"component_pseudo_rig_action_component_plan", "source_animation_component_plan_with_local_hand_redraw"} or "pseudo_rig" in str(route):
        failures.append("single-image hard-split pseudo-rig cannot satisfy hand/petal contact semantics")
    if manual_override.get("status") == "manual_override_required":
        failures.append("manual_route_override.status manual_override_required cannot approve catch_falling_petal route selection")
    if part_consistency and part_consistency.get("status") != "pass":
        failures.append(f"part_consistency_report.status must be pass, got {part_consistency.get('status')}")
    if route == "clean_layer_component_route" and component_integrity.get("status") != "pass":
        failures.append(f"clean_layer_component_route requires component_integrity_report.status pass, got {component_integrity.get('status', 'missing')}")
    if route == "provider_keypose_candidate" and provider_preflight and provider_preflight.get("status") != "pass":
        failures.append(f"provider_preflight_report.status must be pass when present, got {provider_preflight.get('status')}")

    names = phase_names(action_plan)
    required_keywords = ["notice", "anticipation", "hand", "palm", "contact", "caught", "settle", "loop"]
    missing_keywords = [keyword for keyword in required_keywords if action_plan and not any(keyword in name for name in names)]
    if missing_keywords:
        failures.append("missing catch-falling-petal phase keywords: " + ", ".join(missing_keywords))
    if action_plan and not has_required_visual_change(action_plan, ["petal", "palm", "contact", "occlud", "caught"]):
        failures.append("required_visual_change must describe petal/palm/contact/occlusion semantics")

    return {
        "schema_version": "sofunny-action-validation.v2",
        "action": action,
        "profile": profile.get("profile_name"),
        "status": "fail" if failures else "pass",
        "route": route,
        "required_route": "provider_keypose_candidate_or_local_redraw_keypose_candidate",
        "part_consistency_status": part_consistency.get("status", "missing"),
        "component_integrity_status": component_integrity.get("status", "missing"),
        "provider_preflight_status": provider_preflight.get("status", "missing"),
        "failures": failures,
        "warnings": warnings,
        "notes": [
            "The admission-critical frame is real hand/petal occlusion.",
            "A flattened PNG split into head/torso/arm boxes is diagnostic-only for this action.",
        ],
    }


def validate_small_jog(run_dir: Path, profile: dict) -> dict:
    manifest = load_json(run_dir / "sofunny-run-manifest.json")
    candidate = load_json(run_dir / "candidate_manifest.json")
    visual_stability = load_json(run_dir / "visual_stability_report.json")
    body_tail = load_json(run_dir / "body_tail_consistency_report.json")
    phase_review = load_json(run_dir / "action_phase_review.json")
    frame_paths = sorted((run_dir / "sequence_frames").glob("*.png"))
    frames = [Image.open(path).convert("RGBA") for path in frame_paths]

    failures: list[str] = []
    route = candidate.get("route") or manifest.get("generation", {}).get("route", "")
    admission_eligible = manifest.get("generation", {}).get("admission_eligible")
    if admission_eligible is None:
        admission_eligible = candidate.get("admission_eligible")
    if admission_eligible is not True:
        failures.append("candidate route is not admission-eligible")
    if "pipeline_smoke" in route or "fallback" in route:
        failures.append("pipeline-smoke/fallback route cannot satisfy small_jog_front action contract")

    if len(frames) < 6:
        failures.append("small_jog_front requires at least 6 frames")

    diversity = lower_body_diversity(frames)
    # This threshold is deliberately conservative. It blocks static-leg bounce while allowing true pose changes.
    min_delta = int(get_path(profile, "thresholds.action_contract.small_jog_front.min_lower_body_pose_delta", 120))
    max_delta_ratio = float(get_path(profile, "thresholds.action_contract.small_jog_front.max_lower_body_delta_ratio", 3.0))
    if diversity["max_delta"] < min_delta:
        failures.append("lower-body pose diversity is too low for small jog")
    deltas = [value for value in diversity.get("deltas", []) if value > 0]
    if len(frames) <= 8 and len(deltas) >= 2 and max(deltas) / max(1, min(deltas)) > max_delta_ratio:
        failures.append("lower-body pose changes are uneven; jog rhythm reads as jumpy")
    visual_warnings = visual_stability.get("warnings", [])
    visual_ok = visual_stability.get("status") in {None, "pass"} or (
        visual_stability.get("status") == "warn"
        and body_tail.get("status") == "pass"
        and set(visual_warnings).issubset({"alpha area changes by more than 8%", "alpha area changes by more than threshold"})
    )
    if not visual_ok:
        failures.append("visual stability fails; body/head shake makes the jog read as jitter")
    if phase_review.get("status") != "pass":
        failures.append("manual action_phase_review.json pass is required for small_jog_front")

    report = {
        "schema_version": "sofunny-action-validation.v2",
        "action": "small_jog_front",
        "status": "fail" if failures else "pass",
        "profile": profile.get("profile_name"),
        "route": route,
        "admission_eligible": admission_eligible,
        "required_phases": profile_phases_for(profile, 6, "small_jog_front", SMALL_JOG_PHASES),
        "thresholds": {
            "min_lower_body_pose_delta": min_delta,
            "max_lower_body_delta_ratio": max_delta_ratio,
        },
        "phase_validation": {
            "status": phase_review.get("status", "manual_required"),
            "review_path": "action_phase_review.json",
            "note": "Frames must visually satisfy left/right contact, push-off, flight, recover, arm-leg opposition, tail lag, and contact/flight shadow logic.",
        },
        "lower_body_pose_diversity": diversity,
        "visual_stability_status": visual_stability.get("status", "missing"),
        "failures": failures,
        "notes": [
            "Whole-body translation, squash, shadow, speed lines, or tail arcs do not count as leg motion.",
            "Automatic lower-body diversity can reject bad candidates, but cannot approve small_jog_front without manual phase review.",
            "Use a visual provider, SoFunny-adapted sprite generator, or localized redraw for true alternating leg poses.",
        ],
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--action", required=True)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    profile = load_profile(args.profile)
    if args.action == "small_jog_front":
        report = validate_small_jog(run_dir, profile)
    elif args.action == "sherry_tail_wave_greeting":
        report = validate_tail_wave_greeting(run_dir, profile, args.action)
    elif args.action == "catch_falling_petal":
        report = validate_catch_falling_petal(run_dir, profile, args.action)
    elif args.action.startswith("coin_flip_deal_nod"):
        report = validate_coin_flip_deal_nod(run_dir, profile, args.action)
    else:
        phases = profile_phases_for(profile, 6, args.action, [])
        report = {
            "schema_version": "sofunny-action-validation.v1",
            "action": args.action,
            "profile": profile.get("profile_name"),
            "status": "manual_required",
            "failures": ["no automatic action contract validator for this action"],
            "required_phases": phases,
        }
    write_json(run_dir / "action_validation_report.json", report)
    print(json.dumps({"status": report["status"], "failures": report.get("failures", [])}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
