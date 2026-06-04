#!/usr/bin/env python3
"""Validate source-animation part-map contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def part_entries(part_map: dict) -> dict[str, dict]:
    parts = part_map.get("parts")
    if not isinstance(parts, list) or not parts:
        fail("part_map.json must contain a non-empty parts list")
    out = {}
    for entry in parts:
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            fail("each part entry needs a non-empty name")
        if name in out:
            fail(f"duplicate part in part_map.json: {name}")
        out[name] = entry
    return out


def validate_part_map(run_dir: Path) -> list[str]:
    errors: list[str] = []
    part_map_path = run_dir / "part_map.json"
    if not part_map_path.exists():
        return ["missing part_map.json"]
    try:
        part_map = read_json(part_map_path)
    except Exception as exc:
        return [f"part_map.json is not valid JSON: {exc}"]

    if part_map.get("schema_version") != "sofunny-part-map.v1":
        errors.append("part_map.json.schema_version must be sofunny-part-map.v1")
    canvas = part_map.get("canvas")
    if not isinstance(canvas, dict) or not isinstance(canvas.get("width"), int) or not isinstance(canvas.get("height"), int):
        errors.append("part_map.json.canvas must include integer width and height")
        width = height = None
    else:
        width, height = canvas["width"], canvas["height"]
        if width <= 0 or height <= 0:
            errors.append("part_map.json canvas width and height must be positive")

    entries = {}
    try:
        entries = part_entries(part_map)
    except SystemExit:
        raise
    except Exception as exc:
        errors.append(str(exc))

    for name, entry in entries.items():
        file_value = entry.get("file")
        if not isinstance(file_value, str) or not file_value:
            errors.append(f"{name}: missing file")
            continue
        path = run_dir / file_value
        if not path.exists():
            errors.append(f"{name}: missing file {file_value}")
            continue
        try:
            image = Image.open(path).convert("RGBA")
        except Exception as exc:
            errors.append(f"{name}: cannot load image: {exc}")
            continue
        if width is not None and image.size != (width, height):
            errors.append(f"{name}: image size {image.size} does not match canvas {(width, height)}")
        if image.getbbox() is None:
            errors.append(f"{name}: image has no visible alpha")
        bbox = entry.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4 or not all(isinstance(v, int) for v in bbox):
            errors.append(f"{name}: bbox must be four integers")

    render_order = part_map.get("render_order")
    if not isinstance(render_order, list) or not render_order:
        errors.append("part_map.json.render_order must be a non-empty list")
    else:
        for name in render_order:
            if name not in entries:
                errors.append(f"render_order references unknown part: {name}")

    for contract_name, key, list_key in (
        ("identity_parts_contract.json", "part", "fixed_identity_parts"),
        ("movable_parts_contract.json", "part", "movable_parts"),
    ):
        path = run_dir / contract_name
        if not path.exists():
            continue
        try:
            contract = read_json(path)
        except Exception as exc:
            errors.append(f"{contract_name} is not valid JSON: {exc}")
            continue
        items = contract.get(list_key)
        if not isinstance(items, list):
            errors.append(f"{contract_name}.{list_key} must be a list")
            continue
        for item in items:
            part = item.get(key)
            if part not in entries:
                errors.append(f"{contract_name} references unknown part: {part}")

    action_plan_path = run_dir / "action_component_plan.json"
    if action_plan_path.exists():
        try:
            action_plan = read_json(action_plan_path)
        except Exception as exc:
            errors.append(f"action_component_plan.json is not valid JSON: {exc}")
        else:
            phases = action_plan.get("phases")
            if not isinstance(phases, list) or not phases:
                errors.append("action_component_plan.json.phases must be a non-empty list")
            else:
                for phase in phases:
                    if not phase.get("required_visual_change"):
                        errors.append(f"phase {phase.get('name', '<unknown>')} missing required_visual_change")
                    transforms = phase.get("transforms")
                    if not isinstance(transforms, dict):
                        errors.append(f"phase {phase.get('name', '<unknown>')} transforms must be an object")
                        continue
                    for part in transforms:
                        if part not in entries:
                            errors.append(f"phase {phase.get('name', '<unknown>')} references unknown part: {part}")
            loop = action_plan.get("loop")
            if not isinstance(loop, dict) or "max_loop_delta_px" not in loop:
                errors.append("action_component_plan.json.loop.max_loop_delta_px is required")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    run_dir = Path(args.run_dir).expanduser().resolve()
    errors = validate_part_map(run_dir)
    if errors:
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS: part map validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

