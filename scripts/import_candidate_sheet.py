#!/usr/bin/env python3
"""Import a SoFunny candidate sheet into a run folder."""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sofunny_anim.profiles import coalesce, get_path, keypose_count, load_profile

from PIL import Image

from sofunny_anim.anchors import metric_range, normalize_offsets
from sofunny_anim.frame_layout import split_grid_sheet, split_horizontal_sheet, write_sequence
from sofunny_anim.image_io import parse_canvas, remove_background, remove_small_alpha_components
from sofunny_anim.manifests import write_json
from sofunny_anim.previews import save_checker_gif, save_contact_sheet, save_transparent_gif, save_transparent_sheet, save_webp


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--input", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--frames", type=int)
    parser.add_argument("--action")
    parser.add_argument("--character-name", required=True)
    parser.add_argument("--canvas", type=parse_canvas)
    parser.add_argument("--layout", choices=["horizontal", "grid"], default="horizontal")
    parser.add_argument("--rows", type=int, default=1)
    parser.add_argument("--columns", type=int)
    parser.add_argument("--background", choices=["transparent", "checker", "green"], default="green")
    parser.add_argument("--duration-ms", type=int)
    parser.add_argument("--admission-eligible", action="store_true")
    parser.add_argument("--route", default="imported_candidate")
    parser.add_argument("--min-component-ratio", type=float, default=0.01)
    args = parser.parse_args()
    profile = load_profile(args.profile)
    args.frames = args.frames if args.frames is not None else keypose_count(profile, "production", 12)
    args.action = args.action or get_path(profile, "motion_defaults.default_action", None)
    args.canvas = parse_canvas(coalesce(args.canvas, profile, "default_canvas", "384x384")) if args.canvas is None else args.canvas
    args.duration_ms = int(coalesce(args.duration_ms, profile, "motion_defaults.duration_ms", 90))
    if not args.action:
        parser.error("--action is required when profile.motion_defaults.default_action is unset")

    run_dir = Path(args.run_dir).expanduser().resolve()
    for rel in ["source", "raw_candidate_frames", "sequence_frames", "generation_briefs"]:
        (run_dir / rel).mkdir(parents=True, exist_ok=True)

    input_path = Path(args.input).expanduser().resolve()
    source_copy = run_dir / "source" / input_path.name
    shutil.copy2(input_path, source_copy)
    sheet = Image.open(input_path).convert("RGBA")
    if args.layout == "horizontal":
        raw_frames = split_horizontal_sheet(sheet, args.frames)
    else:
        columns = args.columns or args.frames
        raw_frames = split_grid_sheet(sheet, args.rows, columns)[: args.frames]
    cleaned = []
    component_reports = []
    for index, frame in enumerate(raw_frames):
        bg_removed = remove_background(frame, args.background)
        component_cleaned, component_report = remove_small_alpha_components(bg_removed, args.min_component_ratio)
        component_report["frame"] = index
        cleaned.append(component_cleaned)
        component_reports.append(component_report)
    write_sequence(cleaned, run_dir / "raw_candidate_frames")
    normalized, before, after = normalize_offsets(cleaned, args.canvas)
    write_sequence(normalized, run_dir / "sequence_frames")

    save_contact_sheet(normalized, run_dir / "contact_sheet.png", 256)
    save_contact_sheet(normalized, run_dir / "contact_sheet_full_canvas.png", 192)
    save_transparent_sheet(normalized, run_dir / "sheet-transparent.png")
    save_transparent_gif(normalized, run_dir / "animation.gif", args.duration_ms)
    save_checker_gif(normalized, run_dir / "animation_checker.gif", args.duration_ms)
    save_webp(normalized, run_dir / "animation.webp", args.duration_ms)

    report = {
        "status": "pass" if metric_range([float(m.anchor_bottom) for m in after]) <= 1 and metric_range([float(m.lower_body_anchor_x) for m in after]) <= 6 else "warn",
        "input": str(input_path),
        "profile": profile.get("profile_name"),
        "source_copy": str(source_copy),
        "route": args.route,
        "admission_eligible": args.admission_eligible,
        "frame_count": args.frames,
        "canvas": {"width": args.canvas[0], "height": args.canvas[1]},
        "before": {
            "bbox_bottom_range_px": metric_range([float(m.anchor_bottom) for m in before]),
            "anchor_center_x_range_px": metric_range([float(m.lower_body_anchor_x) for m in before]),
        },
        "after": {
            "bbox_bottom_range_px": metric_range([float(m.anchor_bottom) for m in after]),
            "anchor_center_x_range_px": metric_range([float(m.lower_body_anchor_x) for m in after]),
        },
    }
    write_json(run_dir / "offset_normalization_report.json", report)
    write_json(run_dir / "component_cleanup_report.json", {
        "status": "pass",
        "min_component_ratio": args.min_component_ratio,
        "frames": component_reports,
    })
    manifest = {
        "schema_version": "sofunny-candidate-sheet.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile.get("profile_name"),
        "character_name": args.character_name,
        "action": args.action,
        "route": args.route,
        "admission_eligible": args.admission_eligible,
        "reference": str(source_copy),
        "candidate_sheet": str(source_copy),
        "frames": args.frames,
        "canvas": {"width": args.canvas[0], "height": args.canvas[1]},
    }
    write_json(run_dir / "candidate_manifest.json", manifest)
    print(str(run_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
