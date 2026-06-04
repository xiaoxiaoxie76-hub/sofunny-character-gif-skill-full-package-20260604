#!/usr/bin/env python3
"""Generate assembled source-animation keyposes from approved parts."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image


REQUIRED_PHASE_FIELDS = [
    "body_y",
    "head_y",
    "head_rotation",
    "arm_rotation",
    "leg_phase",
    "tail_rotation",
    "tail_lag",
    "squash_stretch",
    "optional_expression_variant",
]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_optional_json(path: Path) -> dict:
    try:
        return read_json(path)
    except FileNotFoundError:
        return {}


def route_from_reports(run_dir: Path, part_map: dict, action_plan: dict) -> str:
    route_report = read_optional_json(run_dir / "source_route_selection_report.json") or read_optional_json(run_dir / "route_selection_report.json")
    return str(
        route_report.get("recommended_route")
        or route_report.get("proposed_route")
        or action_plan.get("route")
        or part_map.get("route")
        or ""
    )


def clean_component_status(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {
        "production_clean_components",
        "clean_component_layers",
        "clean_layer_packet",
        "provider_layer_packet",
        "manual_clean_layers",
    }


def route_details(run_dir: Path, part_map: dict, action_plan: dict) -> dict:
    route_report = read_optional_json(run_dir / "source_route_selection_report.json") or read_optional_json(run_dir / "route_selection_report.json")
    return {
        "route_status": str(route_report.get("status") or ""),
        "report_action": str(route_report.get("action") or ""),
        "recommended_route": str(route_report.get("recommended_route") or ""),
        "proposed_route": str(route_report.get("proposed_route") or ""),
        "part_map_route": str(part_map.get("route") or ""),
        "action_plan_route": str(action_plan.get("route") or ""),
        "action_name": str(action_plan.get("action_name") or action_plan.get("action") or ""),
        "has_route_report": bool(route_report),
    }


def reject_dirty_component_source(run_dir: Path, part_map: dict, action_plan: dict) -> None:
    errors: list[str] = []
    route = route_from_reports(run_dir, part_map, action_plan).lower()
    details = route_details(run_dir, part_map, action_plan)
    review_status = str(part_map.get("review_status", "")).lower()
    provenance = str(part_map.get("segmentation_provenance", "")).lower()
    manual_override = read_optional_json(run_dir / "manual_route_override.json")
    part_consistency = read_optional_json(run_dir / "part_consistency_report.json")
    component_integrity = read_optional_json(run_dir / "component_integrity_report.json")
    action_name = details["action_name"].strip().lower().replace("-", "_").replace(" ", "_")
    recommended_route = details["recommended_route"].lower()
    component_routes = {
        "component_pseudo_rig_action_component_plan",
        "source_animation_pseudo_rig_mvp",
        "source_animation_component_plan_with_local_hand_redraw",
        "clean_layer_component_route",
        "prop_action_component_route",
    }

    if manual_override.get("status") == "manual_override_required":
        errors.append("manual_route_override.status manual_override_required cannot feed deterministic component keypose generation")
    elif manual_override:
        errors.append("manual_route_override.json cannot feed deterministic component keypose generation; use route_selection_report with status pass")
    if details["has_route_report"] and details["route_status"] != "pass":
        errors.append(f"route_selection_report.status must be pass before component keypose generation, got {details['route_status'] or 'missing'}")
    if details["has_route_report"] and recommended_route and recommended_route not in component_routes:
        errors.append(f"route_selection_report.recommended_route {recommended_route} cannot feed component keypose generation")
    if action_name == "catch_falling_petal":
        declared_routes = {
            details["recommended_route"].lower(),
            details["proposed_route"].lower(),
            details["part_map_route"].lower(),
            details["action_plan_route"].lower(),
        }
        declared_routes.discard("")
        if "clean_layer_component_route" not in declared_routes:
            errors.append("catch_falling_petal component generation requires clean_layer_component_route; provider/local-redraw candidates must be imported as keyposes")
        if any("pseudo_rig" in item or item == "source_animation_component_plan_with_local_hand_redraw" for item in declared_routes):
            errors.append("catch_falling_petal cannot use pseudo-rig or source_animation_component_plan_with_local_hand_redraw")
    if part_consistency and part_consistency.get("status") != "pass":
        errors.append(f"part_consistency_report.status must be pass before component keypose generation, got {part_consistency.get('status')}")
    if not component_integrity:
        errors.append("component_integrity_report.json is required before component keypose generation")
    elif component_integrity.get("status") != "pass":
        errors.append(f"component_integrity_report.status must be pass for component keypose generation, got {component_integrity.get('status')}")

    dirty_route = "pseudo_rig" in route or "component_pseudo_rig" in route or "source_animation_component_plan_with_local_hand_redraw" in route
    dirty_review = review_status in {"candidate_review_required", "draft_manual_review_required", "manual_required", "diagnostic_only"}
    dirty_provenance = any(token in provenance for token in ("single_image", "auto", "box", "flat", "unknown", "diagnostic"))
    if dirty_route:
        errors.append("pseudo-rig or local-hand-redraw component routes are diagnostic-only and cannot feed deterministic component keypose generation")
    if dirty_review:
        errors.append(f"part_map.review_status {review_status} cannot feed deterministic component keypose generation")
    if not clean_component_status(provenance):
        errors.append(f"part_map.segmentation_provenance must declare clean component layers, got {provenance or 'missing'}")
    if dirty_provenance:
        errors.append("single-image/auto/box/flat/unknown component provenance is diagnostic-only")
    if errors:
        raise ValueError("; ".join(errors))


def transform_part(image: Image.Image, transform: dict) -> tuple[Image.Image, dict]:
    rgba = image.convert("RGBA")
    bbox = rgba.getbbox()
    if bbox is None:
        return rgba, {"bbox": None, "translate": [0, 0], "rotate": 0, "scale": [1, 1]}

    crop = rgba.crop(bbox)
    sx, sy = transform.get("scale", [1.0, 1.0])
    if not isinstance(sx, (int, float)) or not isinstance(sy, (int, float)):
        raise ValueError("scale values must be numbers")
    sx = float(sx)
    sy = float(sy)
    if sx <= 0 or sy <= 0:
        raise ValueError("scale values must be positive")
    if sx != 1.0 or sy != 1.0:
        crop = crop.resize((max(1, round(crop.width * sx)), max(1, round(crop.height * sy))), Image.Resampling.BICUBIC)

    rotate = float(transform.get("rotate", 0) or 0)
    if rotate:
        crop = crop.rotate(rotate, expand=True, resample=Image.Resampling.BICUBIC)

    tx, ty = transform.get("translate", [0, 0])
    if not isinstance(tx, (int, float)) or not isinstance(ty, (int, float)):
        raise ValueError("translate values must be numbers")
    center_x = (bbox[0] + bbox[2]) / 2 + float(tx)
    center_y = (bbox[1] + bbox[3]) / 2 + float(ty)
    paste_x = round(center_x - crop.width / 2)
    paste_y = round(center_y - crop.height / 2)
    out = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    out.alpha_composite(crop, (paste_x, paste_y))
    return out, {
        "bbox": list(out.getbbox() or (0, 0, 0, 0)),
        "translate": [float(tx), float(ty)],
        "rotate": rotate,
        "scale": [sx, sy],
    }


def make_contact_sheet(frames: list[Image.Image], path: Path, cell: int = 192) -> None:
    cols = min(6, len(frames))
    rows = math.ceil(len(frames) / cols)
    sheet = Image.new("RGBA", (cols * cell, rows * cell), (245, 245, 245, 255))
    for index, frame in enumerate(frames):
        thumb = frame.resize((cell, cell), Image.Resampling.LANCZOS)
        sheet.alpha_composite(thumb, ((index % cols) * cell, (index // cols) * cell))
    sheet.save(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--part-map", default="part_map.json")
    parser.add_argument("--identity-contract", default="identity_parts_contract.json")
    parser.add_argument("--movable-contract", default="movable_parts_contract.json")
    parser.add_argument("--action-plan", default="action_component_plan.json")
    parser.add_argument("--output-dir", default="component_keyposes")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    part_map = read_json(run_dir / args.part_map)
    identity_contract = read_json(run_dir / args.identity_contract)
    movable_contract = read_json(run_dir / args.movable_contract)
    action_plan = read_json(run_dir / args.action_plan)
    reject_dirty_component_source(run_dir, part_map, action_plan)

    canvas = part_map.get("canvas", {})
    width, height = int(canvas["width"]), int(canvas["height"])
    part_entries = {entry["name"]: entry for entry in part_map["parts"]}
    render_order = part_map.get("render_order") or [entry["name"] for entry in part_map["parts"] if entry.get("render", True)]
    movable_parts = {entry["part"]: entry for entry in movable_contract.get("movable_parts", [])}
    fixed_parts = {entry["part"]: entry for entry in identity_contract.get("fixed_identity_parts", [])}

    part_images: dict[str, Image.Image] = {}
    for name, entry in part_entries.items():
        part_images[name] = Image.open(run_dir / entry["file"]).convert("RGBA")
        if part_images[name].size != (width, height):
            raise ValueError(f"{name} size {part_images[name].size} does not match canvas {(width, height)}")

    output_dir = run_dir / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Image.Image] = []
    manifest_frames = []
    errors: list[str] = []

    for phase in action_plan.get("phases", []):
        frame_index = int(phase["frame"])
        for field in REQUIRED_PHASE_FIELDS:
            if field not in phase:
                errors.append(f"phase {phase.get('name')} missing lively motion field {field}")
        squash = phase.get("squash_stretch")
        if not (isinstance(squash, list) and len(squash) == 2 and all(isinstance(value, (int, float)) for value in squash)):
            errors.append(f"phase {phase.get('name')} squash_stretch must be [x, y] numbers")
        transforms = phase.get("transforms", {})
        frame = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        frame_record = {
            "frame": frame_index,
            "phase": phase.get("name"),
            "required_visual_change": phase.get("required_visual_change"),
            "body_y": phase.get("body_y"),
            "head_y": phase.get("head_y"),
            "head_rotation": phase.get("head_rotation"),
            "arm_rotation": phase.get("arm_rotation"),
            "leg_phase": phase.get("leg_phase"),
            "tail_rotation": phase.get("tail_rotation"),
            "tail_lag": phase.get("tail_lag"),
            "squash_stretch": phase.get("squash_stretch"),
            "optional_expression_variant": phase.get("optional_expression_variant"),
            "parts": {},
        }
        for part_name in transforms:
            if part_name not in part_entries:
                errors.append(f"phase {phase.get('name')} references unknown part {part_name}")
            if part_name not in movable_parts and part_name not in fixed_parts:
                errors.append(f"phase {phase.get('name')} moves undeclared part {part_name}")

        for part_name in render_order:
            if part_name not in part_images:
                errors.append(f"render_order references missing part {part_name}")
                continue
            transform = transforms.get(part_name, {})
            if transform.get("local_redraw_allowed"):
                errors.append(f"local redraw is not supported in deterministic component generation for {part_name}")
            try:
                transformed, record = transform_part(part_images[part_name], transform)
            except Exception as exc:
                errors.append(f"{phase.get('name')} {part_name}: {exc}")
                continue
            frame.alpha_composite(transformed)
            frame_record["parts"][part_name] = record

        frame_path = output_dir / f"{frame_index:03d}.png"
        frame.save(frame_path)
        frames.append(frame)
        frame_record["file"] = f"{args.output_dir}/{frame_index:03d}.png"
        manifest_frames.append(frame_record)

    if errors:
        raise ValueError("; ".join(errors))

    if not frames:
        raise ValueError("action plan produced no frames")

    make_contact_sheet(frames, run_dir / "component_keypose_contact_sheet.png")
    manifest = {
        "schema_version": "sofunny-component-keyposes.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "route": route_from_reports(run_dir, part_map, action_plan) or "component_keypose_generation",
        "full_frame_redraw": False,
        "part_map": args.part_map,
        "identity_contract": args.identity_contract,
        "movable_contract": args.movable_contract,
        "action_plan": args.action_plan,
        "output_dir": args.output_dir,
        "frame_count": len(frames),
        "frames": sorted(manifest_frames, key=lambda item: item["frame"]),
    }
    write_json(run_dir / "component_keypose_manifest.json", manifest)
    print(str(output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
