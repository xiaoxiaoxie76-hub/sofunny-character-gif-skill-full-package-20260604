#!/usr/bin/env python3
"""Audit prop-action semantics such as coin release, catch, and present."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_COIN_PHASES = {
    "ready",
    "toss_release",
    "coin_rise",
    "coin_peak",
    "catch_receive",
    "present",
    "loop_return",
}


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def part_group(name: str) -> str:
    lowered = name.lower()
    if "coin" in lowered:
        return "coin_prop"
    if "hand" in lowered:
        return "hand"
    if "arm" in lowered:
        return "arm"
    if "head" in lowered or "face" in lowered:
        return "head"
    return "other"


def pair(value: Any, default: tuple[float, float] = (0.0, 0.0)) -> tuple[float, float]:
    if isinstance(value, list) and len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
        return float(value[0]), float(value[1])
    return default


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def phase_key(name: str) -> str | None:
    lowered = name.lower()
    for required in REQUIRED_COIN_PHASES:
        if required in lowered:
            return required
    if "drop" in lowered:
        return "coin_drop"
    return None


def part_centers(part_map: dict[str, Any]) -> dict[str, tuple[float, float]]:
    centers = {}
    for entry in part_map.get("parts", []):
        bbox = entry.get("bbox")
        name = str(entry.get("name", ""))
        if isinstance(bbox, list) and len(bbox) == 4:
            centers[name] = ((float(bbox[0]) + float(bbox[2])) / 2, (float(bbox[1]) + float(bbox[3])) / 2)
    return centers


def transformed_center(base: tuple[float, float], transform: dict[str, Any]) -> tuple[float, float]:
    tx, ty = pair(transform.get("translate"))
    return (base[0] + tx, base[1] + ty)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--report", default="prop_action_contact_report.json")
    parser.add_argument("--max-contact-distance-px", type=float, default=38.0)
    parser.add_argument("--min-release-distance-px", type=float, default=42.0)
    parser.add_argument("--min-arc-height-px", type=float, default=60.0)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    part_map = read_json(run_dir / "part_map.json", {})
    action_plan = read_json(run_dir / "action_component_plan.json", {})
    findings: list[str] = []
    warnings: list[str] = []

    centers = part_centers(part_map)
    hand_parts = [name for name in centers if part_group(name) == "hand"]
    arm_parts = [name for name in centers if part_group(name) == "arm"]
    coin_parts = [name for name in centers if part_group(name) == "coin_prop"]
    if not coin_parts:
        findings.append("coin_prop part is required for prop action contact audit")
    if not hand_parts:
        findings.append("coin action requires left_hand/right_hand or explicit hand anchors; arm-only parts cannot prove contact")
    contact_parts = hand_parts or arm_parts

    phases: dict[str, dict[str, Any]] = {}
    for phase in action_plan.get("phases", []):
        key = phase_key(str(phase.get("name", "")))
        if key and key not in phases:
            phases[key] = phase
    missing_phases = sorted(REQUIRED_COIN_PHASES - set(phases))
    if missing_phases:
        findings.append("missing required prop contact phases: " + ", ".join(missing_phases))

    phase_metrics = {}
    coin_name = coin_parts[0] if coin_parts else None
    if coin_name and contact_parts:
        coin_base = centers[coin_name]
        for key, phase in phases.items():
            transforms = phase.get("transforms") or {}
            coin_center = transformed_center(coin_base, transforms.get(coin_name, {}))
            nearest = None
            nearest_dist = None
            for part in contact_parts:
                part_center = transformed_center(centers[part], transforms.get(part, {}))
                dist = distance(coin_center, part_center)
                if nearest_dist is None or dist < nearest_dist:
                    nearest = part
                    nearest_dist = dist
            phase_metrics[key] = {
                "coin_center": [round(coin_center[0], 2), round(coin_center[1], 2)],
                "nearest_contact_part": nearest,
                "nearest_contact_distance_px": None if nearest_dist is None else round(nearest_dist, 2),
            }

        for key in ("ready", "catch_receive", "present", "loop_return"):
            dist = phase_metrics.get(key, {}).get("nearest_contact_distance_px")
            if dist is not None and dist > args.max_contact_distance_px:
                findings.append(f"{key} coin-contact distance {dist}px exceeds {args.max_contact_distance_px}px")

        release_dist = phase_metrics.get("toss_release", {}).get("nearest_contact_distance_px")
        peak = phase_metrics.get("coin_peak") or phase_metrics.get("coin_rise")
        ready = phase_metrics.get("ready")
        if release_dist is not None and release_dist < args.min_release_distance_px:
            warnings.append(f"toss_release coin may still be too close to hand/arm: {release_dist}px")
        if ready and peak:
            arc_height = ready["coin_center"][1] - peak["coin_center"][1]
            phase_metrics["arc_height_px"] = round(arc_height, 2)
            if arc_height < args.min_arc_height_px:
                findings.append(f"coin arc height {arc_height:.2f}px is below {args.min_arc_height_px}px")

    report = {
        "schema_version": "sofunny-prop-action-contact-report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not findings else "fail",
        "run_dir": str(run_dir),
        "required_phases": sorted(REQUIRED_COIN_PHASES),
        "hand_parts": hand_parts,
        "arm_parts": arm_parts,
        "coin_parts": coin_parts,
        "phase_metrics": phase_metrics,
        "thresholds": {
            "max_contact_distance_px": args.max_contact_distance_px,
            "min_release_distance_px": args.min_release_distance_px,
            "min_arc_height_px": args.min_arc_height_px,
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
    print("PASS: prop action contact audit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

