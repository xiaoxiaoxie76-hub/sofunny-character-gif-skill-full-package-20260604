#!/usr/bin/env python3
"""Add bounded secondary motion to an action component plan without full-frame redraw."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_LIMITS = {
    "head": {"max_translation_px": 8.0, "max_rotation_deg": 4.0},
    "torso": {"max_translation_px": 8.0, "max_rotation_deg": 2.0},
    "arm": {"max_translation_px": 8.0, "max_rotation_deg": 18.0},
    "leg": {"max_translation_px": 8.0, "max_rotation_deg": 10.0},
    "tail": {"max_translation_px": 8.0, "max_rotation_deg": 14.0},
    "hair_ear": {"max_translation_px": 4.0, "max_rotation_deg": 6.0},
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
    if "hair" in name or "ear" in name:
        return "hair_ear"
    return "other"


def clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def movable_limits(contract: dict[str, Any]) -> dict[str, dict[str, float]]:
    limits: dict[str, dict[str, float]] = {}
    for entry in contract.get("movable_parts", []):
        if isinstance(entry, str):
            part = entry
            group = part_group(part)
            default = DEFAULT_LIMITS.get(group, {"max_translation_px": 4.0, "max_rotation_deg": 4.0})
            limits[part] = dict(default)
            continue
        if isinstance(entry, dict) and entry.get("part"):
            part = str(entry["part"])
            group = part_group(part)
            default = DEFAULT_LIMITS.get(group, {"max_translation_px": 4.0, "max_rotation_deg": 4.0})
            limits[part] = {
                "max_translation_px": float(entry.get("max_translation_px", default["max_translation_px"]) or default["max_translation_px"]),
                "max_rotation_deg": float(entry.get("max_rotation_deg", default["max_rotation_deg"]) or default["max_rotation_deg"]),
            }
    return limits


def ensure_transform(phase: dict[str, Any], part: str) -> dict[str, Any]:
    transforms = phase.setdefault("transforms", {})
    transform = transforms.setdefault(part, {})
    transform.setdefault("translate", [0.0, 0.0])
    transform.setdefault("rotate", 0.0)
    transform.setdefault("scale", [1.0, 1.0])
    if transform.get("local_redraw_allowed"):
        raise ValueError(f"{phase.get('name')} {part}: local_redraw_allowed is forbidden in secondary motion pass")
    return transform


def add_translate_y(transform: dict[str, Any], delta: float, max_translation: float) -> float:
    tx, ty = transform.get("translate", [0.0, 0.0])
    new_y = clamp(float(ty) + delta, max_translation)
    transform["translate"] = [float(tx), round(new_y, 3)]
    return round(new_y, 3)


def add_rotation(transform: dict[str, Any], delta: float, max_rotation: float) -> float:
    new_rotation = clamp(float(transform.get("rotate", 0.0) or 0.0) + delta, max_rotation)
    transform["rotate"] = round(new_rotation, 3)
    return round(new_rotation, 3)


def add_scale(transform: dict[str, Any], sx_delta: float, sy_delta: float) -> list[float]:
    sx, sy = transform.get("scale", [1.0, 1.0])
    new_sx = max(0.9, min(1.1, float(sx) + sx_delta))
    new_sy = max(0.9, min(1.1, float(sy) + sy_delta))
    transform["scale"] = [round(new_sx, 4), round(new_sy, 4)]
    return transform["scale"]


def multiply_scale(transform: dict[str, Any], scale: list[Any]) -> list[float]:
    sx, sy = transform.get("scale", [1.0, 1.0])
    curve_sx, curve_sy = scale
    transform["scale"] = [round(float(sx) * float(curve_sx), 4), round(float(sy) * float(curve_sy), 4)]
    return transform["scale"]


def first_part_by_group(limits: dict[str, dict[str, float]], group: str) -> str | None:
    for part in limits:
        if part_group(part) == group:
            return part
    return None


def parts_by_group(limits: dict[str, dict[str, float]], group: str) -> list[str]:
    return [part for part in limits if part_group(part) == group]


def apply_curve_record(phase: dict[str, Any], part: str, record: dict[str, Any], limits: dict[str, dict[str, float]]) -> None:
    if part not in limits:
        raise ValueError(f"part_motion_curves references undeclared movable part {part}")
    transform = ensure_transform(phase, part)
    tx, ty = transform.get("translate", [0.0, 0.0])
    curve_tx, curve_ty = record.get("translate", [0.0, 0.0])
    transform["translate"] = [
        round(clamp(float(tx) + float(curve_tx), limits[part]["max_translation_px"]), 3),
        round(clamp(float(ty) + float(curve_ty), limits[part]["max_translation_px"]), 3),
    ]
    transform["rotate"] = round(
        clamp(float(transform.get("rotate", 0.0) or 0.0) + float(record.get("rotate", 0.0) or 0.0), limits[part]["max_rotation_deg"]),
        3,
    )
    if "scale" in record:
        multiply_scale(transform, record["scale"])


def apply_part_motion_curves(action_plan: dict[str, Any], limits: dict[str, dict[str, float]], curves_payload: dict[str, Any]) -> set[str]:
    if curves_payload.get("status") != "pass":
        raise ValueError("part_motion_curves.json status must be pass before secondary motion pass")
    curves = curves_payload.get("curves", {})
    if not isinstance(curves, dict) or not curves:
        raise ValueError("part_motion_curves.json curves must be a non-empty object")
    phases = action_plan.get("phases", [])
    changed_parts: set[str] = set()
    for part, records in curves.items():
        if not isinstance(records, list):
            raise ValueError(f"part_motion_curves.{part} must be a list")
        for index, record in enumerate(records):
            if index >= len(phases):
                break
            if not isinstance(record, dict):
                raise ValueError(f"part_motion_curves.{part}[{index}] must be an object")
            apply_curve_record(phases[index], part, record, limits)
            changed_parts.add(part)

    for index, phase in enumerate(phases):
        transforms = phase.get("transforms", {})
        torso = next((part for part in transforms if part_group(part) == "torso"), None)
        head = next((part for part in transforms if part_group(part) == "head"), None)
        tail = next((part for part in transforms if part_group(part) == "tail"), None)
        arm = next((part for part in transforms if part_group(part) == "arm"), None)
        leg = next((part for part in transforms if part_group(part) == "leg"), None)
        if torso:
            _, body_y = transforms[torso].get("translate", [0.0, 0.0])
            phase["body_y"] = round(float(body_y), 3)
            phase["squash_stretch"] = transforms[torso].get("scale", [1.0, 1.0])
        else:
            phase.setdefault("body_y", 0.0)
            phase.setdefault("squash_stretch", [1.0, 1.0])
        if head:
            _, head_y = transforms[head].get("translate", [0.0, 0.0])
            phase["head_y"] = round(float(head_y), 3)
            phase["head_rotation"] = round(float(transforms[head].get("rotate", 0.0) or 0.0), 3)
        else:
            phase.setdefault("head_y", 0.0)
            phase.setdefault("head_rotation", 0.0)
        phase["arm_rotation"] = round(float(transforms.get(arm, {}).get("rotate", 0.0) or 0.0), 3) if arm else 0.0
        if leg:
            _, leg_y = transforms[leg].get("translate", [0.0, 0.0])
            phase["leg_phase"] = "contact" if float(leg_y) <= -1.0 else "lift" if float(leg_y) >= 1.0 else "passing"
        else:
            phase.setdefault("leg_phase", "passing")
        if tail:
            phase["tail_rotation"] = round(float(transforms[tail].get("rotate", 0.0) or 0.0), 3)
            sources = []
            for records in curves.values():
                if index < len(records):
                    sources.extend(records[index].get("sources", []))
            phase["tail_lag"] = 0.25 if "tail_lag" in sources else phase.get("tail_lag", 0.0)
        else:
            phase.setdefault("tail_rotation", 0.0)
            phase.setdefault("tail_lag", 0.0)
        phase.setdefault("optional_expression_variant", None)
        phase.setdefault("acting_intent", "readable primary action with secondary follow-through")
        phase.setdefault("primary_driver", "declared source-animation parts")
        phase.setdefault("motion_reason", "secondary motion follows primary action with offset timing")
        phase.setdefault("spacing_curve", "part_motion_curves")
        phase.setdefault("overlap_group", "head/tail/arms offset from torso")
        phase.setdefault("required_visual_change", "primary action plus parameter-driven secondary part motion")
    return changed_parts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--action-plan", default="action_component_plan.json")
    parser.add_argument("--movable-contract", default="movable_parts_contract.json")
    parser.add_argument("--part-motion-curves", default="part_motion_curves.json")
    parser.add_argument("--output", default="action_component_plan.json")
    parser.add_argument("--report", default="secondary_motion_pass_report.json")
    parser.add_argument("--blink-frames", default="")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    action_plan = read_json(run_dir / args.action_plan)
    limits = movable_limits(read_json(run_dir / args.movable_contract))
    curves_payload = read_json(run_dir / args.part_motion_curves, {})
    phases = action_plan.get("phases", [])
    if not isinstance(phases, list) or len(phases) < 4:
        raise ValueError("action_component_plan.phases must contain at least four phase objects")

    head = first_part_by_group(limits, "head")
    torso = first_part_by_group(limits, "torso")
    tail = first_part_by_group(limits, "tail")
    hair_ear_parts = parts_by_group(limits, "hair_ear")
    arm_parts = parts_by_group(limits, "arm")
    leg_parts = parts_by_group(limits, "leg")
    changed_parts: set[str] = set()
    blink_frames = {int(item) for item in args.blink_frames.split(",") if item.strip().isdigit()}

    if curves_payload:
        for phase in phases:
            if not isinstance(phase, dict):
                raise ValueError("each action_component_plan phase must be an object before secondary motion pass")
        changed_parts = apply_part_motion_curves(action_plan, limits, curves_payload)
        curve_mode = True
    else:
        curve_mode = False
        denominator = max(1, len(phases) - 1)
        for index, phase in enumerate(phases):
            if not isinstance(phase, dict):
                raise ValueError("each action_component_plan phase must be an object before secondary motion pass")
            cycle = (index / denominator) * math.tau
            primary = math.sin(cycle)
            delayed = math.sin(cycle - 0.55)
            overshoot = math.sin(cycle + 0.35)

            if torso:
                transform = ensure_transform(phase, torso)
                body_y = add_translate_y(transform, primary * 2.0, limits[torso]["max_translation_px"])
                squash = add_scale(transform, -primary * 0.012, primary * 0.018)
                phase["body_y"] = body_y
                phase["squash_stretch"] = squash
                changed_parts.add(torso)
            else:
                phase.setdefault("body_y", 0.0)
                phase.setdefault("squash_stretch", [1.0, 1.0])

            if head:
                transform = ensure_transform(phase, head)
                head_y = add_translate_y(transform, delayed * 2.8, limits[head]["max_translation_px"])
                head_rotation = add_rotation(transform, delayed * 2.2, limits[head]["max_rotation_deg"])
                phase["head_y"] = head_y
                phase["head_rotation"] = head_rotation
                changed_parts.add(head)
            else:
                phase.setdefault("head_y", 0.0)
                phase.setdefault("head_rotation", 0.0)

            arm_rotation = 0.0
            for arm_index, part in enumerate(arm_parts):
                direction = -1.0 if arm_index % 2 else 1.0
                transform = ensure_transform(phase, part)
                arm_rotation = add_rotation(transform, direction * overshoot * 8.0, limits[part]["max_rotation_deg"])
                changed_parts.add(part)
            phase["arm_rotation"] = arm_rotation

            leg_phase = "contact" if primary <= -0.35 else "passing" if abs(primary) < 0.35 else "lift"
            for leg_index, part in enumerate(leg_parts):
                direction = -1.0 if leg_index % 2 else 1.0
                transform = ensure_transform(phase, part)
                add_translate_y(transform, direction * primary * 3.0, limits[part]["max_translation_px"])
                changed_parts.add(part)
            phase["leg_phase"] = leg_phase

            if tail:
                transform = ensure_transform(phase, tail)
                tail_rotation = add_rotation(transform, math.sin(cycle - 0.9) * 7.0, limits[tail]["max_rotation_deg"])
                phase["tail_rotation"] = tail_rotation
                phase["tail_lag"] = round(-0.9, 3)
                changed_parts.add(tail)
            else:
                phase.setdefault("tail_rotation", 0.0)
                phase.setdefault("tail_lag", 0.0)

            for part in hair_ear_parts:
                transform = ensure_transform(phase, part)
                add_rotation(transform, math.sin(cycle - 1.1) * 3.5, limits[part]["max_rotation_deg"])
                changed_parts.add(part)

            if index in blink_frames:
                phase["optional_expression_variant"] = "approved_blink"
            else:
                phase.setdefault("optional_expression_variant", None)
            phase.setdefault("required_visual_change", "primary action plus secondary part motion")

    action_plan["secondary_motion_pass"] = {
        "schema_version": "sofunny-secondary-motion-pass.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "full_frame_redraw": False,
        "parameter_driven": curve_mode,
        "part_motion_curves": args.part_motion_curves if curve_mode else None,
        "changed_parts": sorted(changed_parts),
        "allowed_only_by_movable_parts_contract": True,
    }
    write_json(run_dir / args.output, action_plan)
    report = {
        "schema_version": "sofunny-secondary-motion-pass-report.v1",
        "generated_at": action_plan["secondary_motion_pass"]["generated_at"],
        "status": "pass",
        "action_plan": args.output,
        "changed_parts": sorted(changed_parts),
        "full_frame_redraw": False,
        "parameter_driven": curve_mode,
        "part_motion_curves": args.part_motion_curves if curve_mode else None,
    }
    write_json(run_dir / args.report, report)
    print(json.dumps({"status": "pass", "changed_parts": sorted(changed_parts)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
