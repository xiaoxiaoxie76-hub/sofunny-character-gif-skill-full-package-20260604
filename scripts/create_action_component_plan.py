#!/usr/bin/env python3
"""Create action-specific component plans for source-animation candidate generation."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TAIL_WAVE_PHASES = [
    ("idle_start", 0.00, 0, 0, 0, 0, 0, 0, "neutral pose before greeting"),
    ("anticipation_compress", 0.10, 3, 2, -2, -6, -8, -6, "compress before the wave"),
    ("tail_swing_left", 0.22, 1, 1, -3, 10, 18, -24, "tail swings left while arm starts"),
    ("arm_wave_lift", 0.34, -1, -1, -1, 28, 35, -12, "greeting arm lifts clearly"),
    ("wave_peak", 0.46, -2, -2, 2, 46, 50, 8, "hand wave reaches readable peak"),
    ("tail_overshoot_right", 0.56, -1, -1, 3, 34, 28, 30, "tail follows through to the opposite side"),
    ("wave_return", 0.66, 1, 0, 1, 16, 8, 22, "arm returns while tail still trails"),
    ("tail_rebound_left", 0.75, 2, 1, -1, 4, -8, -16, "tail rebound is delayed"),
    ("settle_down", 0.84, 1, 1, -1, -2, -5, -8, "body settles down"),
    ("settle_up", 0.91, -1, 0, 1, 0, 0, 4, "small settling overshoot"),
    ("loop_prepare", 0.96, 1, 1, -1, 5, 6, 8, "prepare return to idle with a visible final settle"),
    ("loop_return", 1.00, 0, 0, 0, 0, 0, 0, "match first pose for loop"),
]

CLEAN_PART_MAP_STATUSES = {
    "clean_layer_packet",
    "manual_clean_layers_approved",
    "production_clean_components",
}


def read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        if default is None:
            raise FileNotFoundError(str(path))
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def part_group(part_name: str) -> str:
    name = part_name.lower()
    if "head" in name or "face" in name or "glasses" in name:
        return "head"
    if "torso" in name or "body" in name or "trunk" in name:
        return "torso"
    if "arm" in name or "hand" in name:
        return "arm"
    if "leg" in name or "foot" in name:
        return "leg"
    if "tail" in name:
        return "tail"
    return "other"


def choose_parts(part_map: dict[str, Any]) -> dict[str, str | list[str]]:
    names = [str(entry.get("name")) for entry in part_map.get("parts", []) if entry.get("name")]
    by_group: dict[str, list[str]] = {}
    for name in names:
        by_group.setdefault(part_group(name), []).append(name)
    arms = by_group.get("arm", [])
    legs = by_group.get("leg", [])
    return {
        "head": (by_group.get("head") or [None])[0],
        "torso": (by_group.get("torso") or [None])[0],
        "tail": (by_group.get("tail") or [None])[0],
        "left_arm": next((part for part in arms if "left" in part.lower()), arms[0] if arms else None),
        "right_arm": next((part for part in arms if "right" in part.lower()), arms[-1] if arms else None),
        "left_leg": next((part for part in legs if "left" in part.lower()), legs[0] if legs else None),
        "right_leg": next((part for part in legs if "right" in part.lower()), legs[-1] if legs else None),
    }


def require_clean_component_layers(run_dir: Path, part_map: dict[str, Any], allow_diagnostic: bool) -> None:
    if allow_diagnostic:
        return
    integrity = read_json(run_dir / "component_integrity_report.json", {})
    review_status = str(part_map.get("review_status", "")).lower()
    provenance = str(part_map.get("segmentation_provenance", "")).lower()
    if integrity.get("status") == "pass" and (review_status in CLEAN_PART_MAP_STATUSES or "clean" in provenance):
        return
    raise ValueError(
        "single-image auto-split pseudo-rig is diagnostic-only. "
        "Import clean component layers with anchors/backfill and pass component_integrity_report.json, "
        "or rerun with --allow-diagnostic-hard-split for a non-production experiment."
    )


def ensure_movable_limits(run_dir: Path, parts: dict[str, str | list[str]]) -> dict[str, Any]:
    path = run_dir / "movable_parts_contract.json"
    contract = read_json(path, {"schema_version": "sofunny-movable-parts.v1", "movable_parts": []})
    entries: dict[str, dict[str, Any]] = {}
    for entry in contract.get("movable_parts", []):
        if isinstance(entry, dict) and entry.get("part"):
            entries[str(entry["part"])] = dict(entry)

    required = {
        parts.get("head"): {"motion": ["head_follow", "small_rotation"], "max_translation_px": 8, "max_rotation_deg": 8},
        parts.get("torso"): {"motion": ["body_bounce", "squash_stretch"], "max_translation_px": 8, "max_rotation_deg": 4, "max_scale_delta": 0.04},
        parts.get("left_arm"): {"motion": ["counter_swing", "possible_greeting_wave"], "max_translation_px": 10, "max_rotation_deg": 60},
        parts.get("right_arm"): {"motion": ["greeting_wave"], "max_translation_px": 10, "max_rotation_deg": 60},
        parts.get("left_leg"): {"motion": ["grounded_support"], "max_translation_px": 5, "max_rotation_deg": 8},
        parts.get("right_leg"): {"motion": ["grounded_support"], "max_translation_px": 5, "max_rotation_deg": 8},
        parts.get("tail"): {"motion": ["tail_wave", "lag", "overshoot"], "max_translation_px": 12, "max_rotation_deg": 45},
    }
    for part, limits in required.items():
        if not part:
            continue
        current = entries.get(str(part), {"part": str(part), "must_remain_attached": True})
        current["motion"] = sorted(set(current.get("motion", [])) | set(limits.pop("motion")))
        for key, value in limits.items():
            current[key] = max(float(current.get(key, 0) or 0), float(value))
        current.setdefault("must_remain_attached", True)
        entries[str(part)] = current

    contract["movable_parts"] = list(entries.values())
    contract["updated_for_action"] = "sherry_tail_wave_greeting"
    contract["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_json(path, contract)
    return contract


def transform_translate(x: float = 0, y: float = 0) -> list[float]:
    return [round(x, 3), round(y, 3)]


def create_tail_wave_plan(run_dir: Path, frames: int, allow_diagnostic_hard_split: bool = False) -> dict[str, Any]:
    part_map = read_json(run_dir / "part_map.json")
    require_clean_component_layers(run_dir, part_map, allow_diagnostic_hard_split)
    canvas = part_map.get("canvas", {"width": 384, "height": 384})
    parts = choose_parts(part_map)
    missing = [name for name in ("head", "torso", "tail", "right_arm") if not parts.get(name)]
    if missing:
        raise ValueError("tail wave greeting requires parts: " + ", ".join(missing))
    ensure_movable_limits(run_dir, parts)

    phases = []
    source = TAIL_WAVE_PHASES
    if frames != len(source):
        source = []
        for index in range(frames):
            t = index / max(1, frames - 1)
            body_y = round(math.sin(math.tau * t) * 2)
            head_y = round(math.sin(math.tau * (t - 0.12)) * 2)
            head_rot = round(math.sin(math.tau * (t - 0.12)) * 3)
            right_arm = round(math.sin(math.tau * min(1, t * 1.15)) * 42)
            left_arm = round(-right_arm * 0.3)
            tail = round(math.sin(math.tau * (t - 0.25)) * 30)
            source.append((f"phase_{index:02d}", t, body_y, head_y, head_rot, left_arm, right_arm, tail, "tail wave greeting motion"))

    for index, (name, progress, body_y, head_y, head_rot, left_arm_rot, right_arm_rot, tail_rot, visual) in enumerate(source):
        leg_offset = 1 if name in {"anticipation_compress", "settle_down"} else -1 if name == "wave_peak" else 0
        squash = [1.018, 0.982] if body_y > 1 else [0.99, 1.01] if body_y < -1 else [1.0, 1.0]
        transforms: dict[str, dict[str, Any]] = {}
        if parts.get("head"):
            transforms[str(parts["head"])] = {"translate": transform_translate(0, head_y), "rotate": head_rot, "scale": [1.0, 1.0]}
        if parts.get("torso"):
            transforms[str(parts["torso"])] = {"translate": transform_translate(0, body_y), "rotate": 0, "scale": squash}
        if parts.get("left_arm"):
            transforms[str(parts["left_arm"])] = {"translate": [0, 0], "rotate": left_arm_rot, "scale": [1.0, 1.0]}
        if parts.get("right_arm"):
            transforms[str(parts["right_arm"])] = {"translate": [0, 0], "rotate": right_arm_rot, "scale": [1.0, 1.0]}
        if parts.get("left_leg"):
            transforms[str(parts["left_leg"])] = {"translate": transform_translate(-leg_offset, body_y * 0.25), "rotate": 0, "scale": [1.0, 1.0]}
        if parts.get("right_leg"):
            transforms[str(parts["right_leg"])] = {"translate": transform_translate(leg_offset, body_y * 0.25), "rotate": 0, "scale": [1.0, 1.0]}
        if parts.get("tail"):
            transforms[str(parts["tail"])] = {"translate": transform_translate(round(tail_rot / 18, 3), body_y * 0.35), "rotate": tail_rot, "scale": [1.0, 1.0]}
        phases.append({
            "name": name,
            "frame": index,
            "acting_intent": visual,
            "primary_driver": "right_arm+tail" if "wave" in name or "tail" in name else "torso",
            "motion_reason": "tail and greeting arm provide the readable action; head follows with delayed smaller motion",
            "spacing_curve": "anticipation_action_overshoot_settle",
            "overlap_group": "right_arm leads, tail lags and overshoots, head follows torso",
            "body_y": body_y,
            "head_y": head_y,
            "head_rotation": head_rot,
            "arm_rotation": right_arm_rot,
            "leg_phase": "grounded_support",
            "tail_rotation": tail_rot,
            "tail_lag": round(progress - 0.25, 3),
            "squash_stretch": squash,
            "optional_expression_variant": None,
            "transforms": transforms,
            "required_visual_change": visual,
        })
    return {
        "schema_version": "sofunny-action-component-plan.v1",
        "action_name": "sherry_tail_wave_greeting",
        "frames": len(phases),
        "canvas": canvas,
        "background": "#00ff00",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "route_note": "action-specific tail/arm/head source plan; legs are grounded support, not the main action",
        "phases": phases,
        "loop": {"first_last_match": True, "max_loop_delta_px": 6},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--frames", type=int, default=12)
    parser.add_argument("--output", default="action_component_plan.json")
    parser.add_argument("--allow-diagnostic-hard-split", action="store_true")
    args = parser.parse_args()
    run_dir = Path(args.run_dir).expanduser().resolve()
    action = args.action.strip().lower().replace("-", "_")
    if action != "sherry_tail_wave_greeting":
        raise ValueError("create_action_component_plan.py currently supports sherry_tail_wave_greeting")
    plan = create_tail_wave_plan(run_dir, args.frames, args.allow_diagnostic_hard_split)
    write_json(run_dir / args.output, plan)
    print(json.dumps({"status": "pass", "action": action, "output": args.output, "frames": len(plan["phases"])}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
