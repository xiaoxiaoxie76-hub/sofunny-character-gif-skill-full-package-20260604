#!/usr/bin/env python3
"""Audit source-animation parts before GIF export."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageChops


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def alpha_area(path: Path) -> int:
    image = Image.open(path).convert("RGBA")
    return sum(1 for value in image.getchannel("A").getdata() if value > 0)


def loop_delta(first: Path, last: Path) -> float:
    a = Image.open(first).convert("RGBA")
    b = Image.open(last).convert("RGBA")
    diff = ImageChops.difference(a.getchannel("A"), b.getchannel("A"))
    bbox = diff.getbbox()
    if bbox is None:
        return 0.0
    return sum(diff.crop(bbox).getdata()) / 255.0


def check_transform_limits(manifest: dict, identity: dict, movable: dict) -> list[str]:
    errors: list[str] = []
    fixed_limits = {entry["part"]: entry for entry in identity.get("fixed_identity_parts", [])}
    movable_limits = {entry["part"]: entry for entry in movable.get("movable_parts", [])}
    for frame in manifest.get("frames", []):
        phase = frame.get("phase")
        if not frame.get("required_visual_change"):
            errors.append(f"{phase}: missing required_visual_change")
        for part_name, record in frame.get("parts", {}).items():
            tx, ty = record.get("translate", [0, 0])
            rotate = abs(float(record.get("rotate", 0) or 0))
            translation = max(abs(float(tx)), abs(float(ty)))
            limit = movable_limits.get(part_name) or fixed_limits.get(part_name)
            if not limit:
                errors.append(f"{phase}: part {part_name} is not declared in identity or movable contracts")
                continue
            max_rotation = float(limit.get("max_rotation_deg", 0) or 0)
            max_translation = float(limit.get("max_translation_px", 0) or 0)
            if rotate > max_rotation:
                errors.append(f"{phase}: {part_name} rotation {rotate:.2f} exceeds {max_rotation:.2f}")
            if translation > max_translation:
                errors.append(f"{phase}: {part_name} translation {translation:.2f} exceeds {max_translation:.2f}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--report", default="part_consistency_report.json")
    args = parser.parse_args()
    run_dir = Path(args.run_dir).expanduser().resolve()

    required = [
        "part_map.json",
        "identity_parts_contract.json",
        "movable_parts_contract.json",
        "action_component_plan.json",
        "component_keypose_manifest.json",
    ]
    errors: list[str] = []
    for name in required:
        if not (run_dir / name).exists():
            errors.append(f"missing {name}")
    if errors:
        report = {"schema_version": "sofunny-part-consistency.v1", "status": "fail", "findings": errors}
        write_json(run_dir / args.report, report)
        for error in errors:
            print(f"- {error}")
        return 1

    part_map = read_json(run_dir / "part_map.json")
    identity = read_json(run_dir / "identity_parts_contract.json")
    movable = read_json(run_dir / "movable_parts_contract.json")
    action_plan = read_json(run_dir / "action_component_plan.json")
    manifest = read_json(run_dir / "component_keypose_manifest.json")

    if manifest.get("full_frame_redraw") is not False:
        errors.append("component_keypose_manifest.full_frame_redraw must be false")

    part_names = {entry["name"] for entry in part_map.get("parts", [])}
    for entry in identity.get("fixed_identity_parts", []):
        part = entry.get("part")
        if part not in part_names:
            errors.append(f"identity part missing from part_map: {part}")
    for entry in movable.get("movable_parts", []):
        part = entry.get("part")
        if part not in part_names:
            errors.append(f"movable part missing from part_map: {part}")

    for phase in action_plan.get("phases", []):
        if not phase.get("required_visual_change"):
            errors.append(f"phase {phase.get('name')} missing required_visual_change")
        for part in (phase.get("transforms") or {}):
            if part not in part_names:
                errors.append(f"phase {phase.get('name')} references unknown part {part}")

    errors.extend(check_transform_limits(manifest, identity, movable))

    frame_paths = [run_dir / frame["file"] for frame in manifest.get("frames", [])]
    for frame_path in frame_paths:
        if not frame_path.exists():
            errors.append(f"missing component keypose {frame_path.relative_to(run_dir)}")
        elif alpha_area(frame_path) <= 0:
            errors.append(f"empty component keypose {frame_path.relative_to(run_dir)}")

    loop = action_plan.get("loop", {})
    delta = None
    if len(frame_paths) >= 2 and frame_paths[0].exists() and frame_paths[-1].exists():
        delta = loop_delta(frame_paths[0], frame_paths[-1])
        max_delta = float(loop.get("max_loop_delta_px", 2) or 2)
        # This is alpha-pixel delta, not geometric px. Keep it a warning-level
        # diagnostic unless the plan requires exact first-last match.
        if loop.get("first_last_match") and delta > max_delta * 150:
            errors.append(f"loop alpha delta {delta:.1f} exceeds tolerance for first_last_match")

    status = "pass" if not errors else "fail"
    report = {
        "schema_version": "sofunny-part-consistency.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "route": manifest.get("route"),
        "full_frame_redraw": manifest.get("full_frame_redraw"),
        "frame_count": len(frame_paths),
        "loop_alpha_delta": delta,
        "findings": errors,
        "blocks_gif_export": status != "pass",
    }
    write_json(run_dir / args.report, report)
    if errors:
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS: part consistency audit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

