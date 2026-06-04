#!/usr/bin/env python3
"""Audit whether source-animation keyposes have production-level lively motion."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops


ROOT_PARTS = {"body", "torso", "trunk", "hips", "pelvis"}


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def status_of(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "missing"
    return str(payload.get("status", "missing")).lower()


def load_frames(frame_dir: Path) -> list[Image.Image]:
    paths = sorted(frame_dir.glob("*.png"))
    return [Image.open(path).convert("RGBA") for path in paths]


def alpha_bbox_center(image: Image.Image) -> tuple[float, float] | None:
    bbox = image.getbbox()
    if bbox is None:
        return None
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def normalized_diff(a: Image.Image, b: Image.Image) -> float:
    if a.size != b.size:
        b = b.resize(a.size, Image.Resampling.BICUBIC)
    diff = ImageChops.difference(a, b)
    bbox = diff.getbbox()
    if bbox is None:
        return 0.0
    data = diff.crop(bbox).getdata()
    total = 0
    count = 0
    for px in data:
        total += sum(px)
        count += 4
    return total / max(1, count * 255)


def unique_pose_count(frames: list[Image.Image], threshold: float) -> int:
    unique: list[Image.Image] = []
    for frame in frames:
        if not unique or all(normalized_diff(frame, other) >= threshold for other in unique):
            unique.append(frame)
    return len(unique)


def consecutive_diffs(frames: list[Image.Image]) -> list[float]:
    return [round(normalized_diff(a, b), 5) for a, b in zip(frames, frames[1:])]


def max_dead_run(near_pairs: list[int]) -> int:
    if not near_pairs:
        return 0
    best = 1
    current = 1
    for prev, item in zip(near_pairs, near_pairs[1:]):
        if item == prev + 1:
            current += 1
        else:
            current = 1
        best = max(best, current)
    return best


def numeric_pair(value: Any, default: tuple[float, float] = (0.0, 0.0)) -> tuple[float, float]:
    if isinstance(value, list) and len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
        return float(value[0]), float(value[1])
    return default


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


def transform_motion_value(record: dict[str, Any]) -> float:
    tx, ty = numeric_pair(record.get("translate"))
    rotate = abs(float(record.get("rotate", 0) or 0))
    sx, sy = numeric_pair(record.get("scale"), (1.0, 1.0))
    scale_motion = (abs(sx - 1.0) + abs(sy - 1.0)) * 30.0
    return math.hypot(tx, ty) + rotate * 0.35 + scale_motion


def part_sequences(manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    frames = manifest.get("frames", [])
    parts = sorted({part for frame in frames for part in (frame.get("parts") or {})})
    sequences: dict[str, list[dict[str, Any]]] = {}
    for part in parts:
        sequences[part] = [(frame.get("parts") or {}).get(part, {}) for frame in frames]
    return sequences


def range_of(values: list[float]) -> float:
    return max(values) - min(values) if values else 0.0


def transform_range(records: list[dict[str, Any]]) -> dict[str, float]:
    tx_values: list[float] = []
    ty_values: list[float] = []
    rot_values: list[float] = []
    sx_values: list[float] = []
    sy_values: list[float] = []
    for record in records:
        tx, ty = numeric_pair(record.get("translate"))
        sx, sy = numeric_pair(record.get("scale"), (1.0, 1.0))
        tx_values.append(tx)
        ty_values.append(ty)
        rot_values.append(float(record.get("rotate", 0) or 0))
        sx_values.append(sx)
        sy_values.append(sy)
    return {
        "x": round(range_of(tx_values), 3),
        "y": round(range_of(ty_values), 3),
        "rotation": round(range_of(rot_values), 3),
        "scale_x": round(range_of(sx_values), 4),
        "scale_y": round(range_of(sy_values), 4),
    }


def sequence_values(records: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for record in records:
        if key == "y":
            _, y = numeric_pair(record.get("translate"))
            values.append(y)
        elif key == "rotation":
            values.append(float(record.get("rotate", 0) or 0))
    return values


def same_sequence(a: list[float], b: list[float], tolerance: float = 0.15) -> bool:
    if not a or not b or len(a) != len(b):
        return False
    return all(abs(x - y) <= tolerance for x, y in zip(a, b))


def center_translation_total(frames: list[Image.Image]) -> float:
    centers = [alpha_bbox_center(frame) for frame in frames]
    total = 0.0
    for a, b in zip(centers, centers[1:]):
        if a is None or b is None:
            continue
        total += math.hypot(b[0] - a[0], b[1] - a[1])
    return total


def root_records(sequences: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    for part, records in sequences.items():
        if part_group(part) == "torso":
            return records
    for part, records in sequences.items():
        if part.lower() in ROOT_PARTS:
            return records
    return []


def root_relative_delta(
    a: dict[str, Any],
    b: dict[str, Any],
    root_a: dict[str, Any] | None,
    root_b: dict[str, Any] | None,
) -> float:
    ax, ay = numeric_pair(a.get("translate"))
    bx, by = numeric_pair(b.get("translate"))
    if root_a and root_b:
        rax, ray = numeric_pair(root_a.get("translate"))
        rbx, rby = numeric_pair(root_b.get("translate"))
        ax -= rax
        ay -= ray
        bx -= rbx
        by -= rby
    ar = float(a.get("rotate", 0) or 0)
    br = float(b.get("rotate", 0) or 0)
    asx, asy = numeric_pair(a.get("scale"), (1.0, 1.0))
    bsx, bsy = numeric_pair(b.get("scale"), (1.0, 1.0))
    return (
        math.hypot(bx - ax, by - ay)
        + abs(br - ar) * 0.35
        + (abs(bsx - asx) + abs(bsy - asy)) * 30.0
    )


def internal_part_movement_total(sequences: dict[str, list[dict[str, Any]]]) -> float:
    roots = root_records(sequences)
    total = 0.0
    for part, records in sequences.items():
        if part.lower() in ROOT_PARTS:
            continue
        for index, (a, b) in enumerate(zip(records, records[1:])):
            root_a = roots[index] if index < len(roots) else None
            root_b = roots[index + 1] if index + 1 < len(roots) else None
            total += root_relative_delta(a, b, root_a, root_b)
    return total


def declared_movable_parts(movable_contract: dict[str, Any]) -> set[str]:
    parts: set[str] = set()
    for entry in movable_contract.get("movable_parts", []):
        if isinstance(entry, str):
            parts.add(entry)
        elif isinstance(entry, dict) and entry.get("part"):
            parts.add(str(entry["part"]))
    return parts


def action_name(run_dir: Path, manifest: dict[str, Any]) -> str:
    plan = read_json(run_dir / "action_component_plan.json", {}) or {}
    route = read_json(run_dir / "route_selection_report.json", {}) or read_json(run_dir / "source_route_selection_report.json", {}) or {}
    return str(plan.get("action_name") or route.get("action") or manifest.get("action") or "").lower().replace("-", "_")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--frame-dir")
    parser.add_argument("--manifest", default="component_keypose_manifest.json")
    parser.add_argument("--part-consistency-report", default="part_consistency_report.json")
    parser.add_argument("--report", default="lively_motion_report.json")
    parser.add_argument("--min-unique-poses", type=int, default=4)
    parser.add_argument("--near-duplicate-threshold", type=float, default=0.012)
    parser.add_argument("--unique-pose-threshold", type=float, default=0.018)
    parser.add_argument("--max-whole-body-ratio", type=float, default=1.25)
    parser.add_argument("--max-loop-diff", type=float, default=0.08)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    frame_dir = Path(args.frame_dir).expanduser().resolve() if args.frame_dir else (
        run_dir / "component_keyposes" if (run_dir / "component_keyposes").exists() else run_dir / "sequence_frames"
    )
    manifest = read_json(run_dir / args.manifest, {})
    movable_contract = read_json(run_dir / "movable_parts_contract.json", {})
    part_consistency = read_json(run_dir / args.part_consistency_report, {})
    secondary_motion = read_json(run_dir / "secondary_motion_pass_report.json", {})
    part_motion_curves = read_json(run_dir / "part_motion_curves.json", {})
    frames = load_frames(frame_dir) if frame_dir.exists() else []

    findings: list[str] = []
    warnings: list[str] = []
    if status_of(part_consistency) != "pass":
        findings.append(f"{args.part_consistency_report}.status must be pass before lively motion audit")
    if not manifest:
        findings.append(f"missing {args.manifest}")
    if len(frames) < 4:
        findings.append("at least four keypose frames are required for lively motion audit")

    diffs = consecutive_diffs(frames) if frames else []
    near_pairs = [index for index, value in enumerate(diffs) if value < args.near_duplicate_threshold]
    end_near_pairs = [index for index in near_pairs if index >= max(0, len(frames) - 4)]
    unique_count = unique_pose_count(frames, args.unique_pose_threshold) if frames else 0
    loop_diff = normalized_diff(frames[0], frames[-1]) if len(frames) >= 2 else None

    sequences = part_sequences(manifest)
    action = action_name(run_dir, manifest)
    grouped_ranges: dict[str, dict[str, float]] = {}
    for group in ("head", "torso", "arm", "leg", "tail", "hair_ear"):
        group_records = [records for part, records in sequences.items() if part_group(part) == group]
        if group_records:
            merged: list[dict[str, Any]] = []
            for frame_index in range(max(len(records) for records in group_records)):
                candidates = [records[frame_index] for records in group_records if frame_index < len(records)]
                merged.append(max(candidates, key=transform_motion_value))
            grouped_ranges[group] = transform_range(merged)

    body_translation = center_translation_total(frames) if frames else 0.0
    internal_motion = internal_part_movement_total(sequences)
    whole_body_ratio = None if internal_motion <= 0 else round(body_translation / internal_motion, 4)

    head_records = next((records for part, records in sequences.items() if part_group(part) == "head"), [])
    torso_records = next((records for part, records in sequences.items() if part_group(part) == "torso"), [])
    head_y = sequence_values(head_records, "y")
    torso_y = sequence_values(torso_records, "y")
    head_phase_offset = {
        "status": "pass",
        "head_y_range": round(range_of(head_y), 3),
        "torso_y_range": round(range_of(torso_y), 3),
        "moves_in_lockstep": same_sequence(head_y, torso_y),
    }

    arm_range = grouped_ranges.get("arm", {})
    leg_range = grouped_ranges.get("leg", {})
    arm_leg = {
        "status": "pass",
        "arm_rotation_range": arm_range.get("rotation", 0.0),
        "arm_y_range": arm_range.get("y", 0.0),
        "leg_y_range": leg_range.get("y", 0.0),
        "leg_x_range": leg_range.get("x", 0.0),
    }

    tail_records = next((records for part, records in sequences.items() if part_group(part) == "tail"), [])
    tail_y = sequence_values(tail_records, "y")
    tail_range = transform_range(tail_records) if tail_records else {}
    tail_declared = any(part_group(part) == "tail" for part in declared_movable_parts(movable_contract)) or bool(tail_records)
    tail_lag_values = [frame.get("tail_lag") for frame in (read_json(run_dir / "action_component_plan.json", {}) or {}).get("phases", [])]
    tail_lag_declared = any(value not in (None, False, 0, 0.0, "") for value in tail_lag_values)
    tail = {
        "status": "pass",
        "declared": tail_declared,
        "rotation_range": tail_range.get("rotation", 0.0),
        "y_range": tail_range.get("y", 0.0),
        "moves_in_lockstep_with_torso": same_sequence(tail_y, torso_y),
        "lag_declared": tail_lag_declared,
    }
    parameter_driven = {
        "status": "missing",
        "secondary_motion_pass_report": status_of(secondary_motion),
        "part_motion_curves_report": status_of(part_motion_curves),
        "parameter_driven": bool(secondary_motion.get("parameter_driven")),
        "curve_families": (part_motion_curves.get("principles") or {}).get("curve_families", []),
    }
    if status_of(secondary_motion) == "pass" and status_of(part_motion_curves) == "pass" and secondary_motion.get("parameter_driven"):
        parameter_driven["status"] = "pass"
    elif secondary_motion or part_motion_curves:
        parameter_driven["status"] = "warn"

    if unique_count < args.min_unique_poses:
        findings.append(f"unique visual pose count {unique_count} is below {args.min_unique_poses}")
    if end_near_pairs:
        findings.append(f"near-duplicate dead frames near loop end: {end_near_pairs}")
    if max_dead_run(near_pairs) >= 2:
        findings.append(f"near-duplicate dead-frame run detected: {near_pairs}")
    if internal_motion <= 0:
        findings.append("internal part movement is zero; candidate reads as whole-body placement motion")
    elif whole_body_ratio is not None and whole_body_ratio > args.max_whole_body_ratio:
        findings.append(
            f"whole-body translation/internal part movement ratio {whole_body_ratio} exceeds {args.max_whole_body_ratio}"
        )
    if head_phase_offset["moves_in_lockstep"] or (
        head_phase_offset["head_y_range"] < 1.0 and grouped_ranges.get("head", {}).get("rotation", 0.0) < 1.0
    ):
        findings.append("head and torso lack readable phase offset")
        head_phase_offset["status"] = "fail"
    is_tail_wave_greeting = "tail_wave_greeting" in action
    if arm_leg["arm_rotation_range"] < 4.0 and arm_leg["arm_y_range"] < 2.0:
        findings.append("arm movement is not readable")
        arm_leg["status"] = "fail"
    if not is_tail_wave_greeting and arm_leg["leg_y_range"] < 2.0 and arm_leg["leg_x_range"] < 2.0:
        findings.append("leg movement is not readable")
        arm_leg["status"] = "fail"
    if tail_declared and (tail["rotation_range"] < 3.0 and (tail["y_range"] < 2.0 or tail["moves_in_lockstep_with_torso"])):
        findings.append("tail is declared but visually locked")
        tail["status"] = "fail"
    if tail_declared and not tail_lag_declared:
        warnings.append("tail lag is not declared in action_component_plan phases")
    if loop_diff is not None and loop_diff > args.max_loop_diff:
        findings.append(f"loop closure diff {loop_diff:.5f} exceeds {args.max_loop_diff}")
    action_specific = {
        "action": action,
        "status": "not_required",
        "checks": [],
    }
    if is_tail_wave_greeting:
        action_specific = {
            "action": action,
            "status": "pass",
            "checks": [
                {"name": "tail_wave_rotation", "value": tail.get("rotation_range", 0.0), "min": 18.0},
                {"name": "greeting_arm_rotation", "value": arm_leg.get("arm_rotation_range", 0.0), "min": 25.0},
                {"name": "head_follow", "value": max(head_phase_offset["head_y_range"], grouped_ranges.get("head", {}).get("rotation", 0.0)), "min": 2.0},
            ],
        }
        for check in action_specific["checks"]:
            if check["value"] < check["min"]:
                findings.append(f"{check['name']} is not readable for tail_wave_greeting")
                action_specific["status"] = "fail"
    if parameter_driven["status"] == "warn":
        warnings.append("parameter-driven secondary motion evidence is incomplete")

    report = {
        "schema_version": "sofunny-lively-motion-report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not findings else "fail",
        "action": action,
        "run_dir": str(run_dir),
        "frame_dir": str(frame_dir),
        "frame_count": len(frames),
        "unique_visual_pose_count": unique_count,
        "near_duplicate_consecutive_frames": near_pairs,
        "consecutive_frame_diffs": diffs,
        "whole_body_translation_vs_internal_part_movement_ratio": whole_body_ratio,
        "whole_body_translation_total": round(body_translation, 4),
        "internal_part_movement_total": round(internal_motion, 4),
        "head_torso_phase_offset": head_phase_offset,
        "arm_leg_movement_readability": arm_leg,
        "tail_lag_and_attachment": tail,
        "action_specific_readability": action_specific,
        "parameter_driven_secondary_motion": parameter_driven,
        "loop_closure": {
            "status": "pass" if loop_diff is not None and loop_diff <= args.max_loop_diff else "fail",
            "first_last_normalized_diff": None if loop_diff is None else round(loop_diff, 5),
            "max_loop_diff": args.max_loop_diff,
        },
        "part_motion_ranges": grouped_ranges,
        "thresholds": {
            "min_unique_poses": args.min_unique_poses,
            "near_duplicate_threshold": args.near_duplicate_threshold,
            "unique_pose_threshold": args.unique_pose_threshold,
            "max_whole_body_ratio": args.max_whole_body_ratio,
            "max_loop_diff": args.max_loop_diff,
        },
        "findings": findings,
        "warnings": warnings,
        "blocks_keypose_freeze": bool(findings),
    }
    write_json(run_dir / args.report, report)
    if findings:
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("PASS: lively motion audit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
