#!/usr/bin/env python3
"""Audit frame-to-frame body silhouette and tail completeness."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

from sofunny_anim.profiles import coalesce, load_profile


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_frames(run_dir: Path) -> list[Image.Image]:
    frame_paths = sorted((run_dir / "sequence_frames").glob("*.png"))
    if not frame_paths:
        raise ValueError(f"no sequence frames found in {run_dir / 'sequence_frames'}")
    return [Image.open(path).convert("RGBA") for path in frame_paths]


def alpha_area(alpha: Image.Image, threshold: int = 96) -> int:
    # Ignore soft shadows and antialias haze; this gate is about body/tail silhouette.
    return sum(1 for value in alpha.getdata() if value >= threshold)


def edge_alpha_counts(image: Image.Image) -> dict[str, int]:
    alpha = image.convert("RGBA").getchannel("A")
    width, height = alpha.size
    return {
        "left": sum(1 for y in range(height) if alpha.getpixel((0, y)) > 0),
        "right": sum(1 for y in range(height) if alpha.getpixel((width - 1, y)) > 0),
        "top": sum(1 for x in range(width) if alpha.getpixel((x, 0)) > 0),
        "bottom": sum(1 for x in range(width) if alpha.getpixel((x, height - 1)) > 0),
    }


def tail_region_metrics(image: Image.Image, bbox: tuple[int, int, int, int]) -> dict:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    # Tail should live on character right, roughly lower head/torso to hip height.
    region_left = left + round(width * 0.54)
    region_top = top + round(height * 0.38)
    region = alpha.crop((region_left, region_top, right, bottom))
    region_bbox = region.getbbox()
    area = alpha_area(region)
    if region_bbox is None:
        region_box_abs = None
        region_width = 0
        region_height = 0
    else:
        rl, rt, rr, rb = region_bbox
        region_box_abs = [region_left + rl, region_top + rt, region_left + rr, region_top + rb]
        region_width = rr - rl
        region_height = rb - rt
    return {
        "tail_region_bbox": region_box_abs,
        "tail_region_alpha_area": area,
        "tail_region_width": region_width,
        "tail_region_height": region_height,
    }


def make_tail_debug_sheet(frames: list[Image.Image], output: Path) -> None:
    cell = 192
    sheet = Image.new("RGBA", (cell * len(frames), cell), (245, 245, 245, 255))
    for index, frame in enumerate(frames):
        img = frame.convert("RGBA").resize((cell, cell), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(img)
        bbox = frame.convert("RGBA").getbbox()
        if bbox:
            sx = cell / frame.width
            sy = cell / frame.height
            left, top, right, bottom = bbox
            scaled_bbox = [round(left * sx), round(top * sy), round(right * sx), round(bottom * sy)]
            draw.rectangle(scaled_bbox, outline=(255, 0, 0, 255), width=2)
            t = tail_region_metrics(frame, bbox).get("tail_region_bbox")
            if t:
                draw.rectangle([round(t[0] * sx), round(t[1] * sy), round(t[2] * sx), round(t[3] * sy)], outline=(0, 80, 255, 255), width=2)
        draw.text((6, 6), f"{index:02d}", fill=(20, 20, 20, 255))
        sheet.alpha_composite(img, (index * cell, 0))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def metric_range(values: list[float]) -> float:
    return max(values) - min(values) if values else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--max-bbox-width-range", type=float)
    parser.add_argument("--max-bbox-height-range", type=float)
    parser.add_argument("--max-alpha-area-ratio", type=float)
    parser.add_argument("--min-right-margin", type=int)
    parser.add_argument("--min-tail-region-width", type=int)
    parser.add_argument("--min-tail-region-area", type=int)
    args = parser.parse_args()
    profile = load_profile(args.profile)
    args.max_bbox_width_range = float(coalesce(args.max_bbox_width_range, profile, "thresholds.body_tail.max_bbox_width_range_px", 12.0))
    args.max_bbox_height_range = float(coalesce(args.max_bbox_height_range, profile, "thresholds.body_tail.max_bbox_height_range_px", 10.0))
    args.max_alpha_area_ratio = float(coalesce(args.max_alpha_area_ratio, profile, "thresholds.body_tail.max_alpha_area_ratio", 0.10))
    args.min_right_margin = int(coalesce(args.min_right_margin, profile, "thresholds.body_tail.min_right_margin_px", 24))
    args.min_tail_region_width = int(coalesce(args.min_tail_region_width, profile, "thresholds.body_tail.min_tail_region_width_px", 34))
    args.min_tail_region_area = int(coalesce(args.min_tail_region_area, profile, "thresholds.body_tail.min_tail_region_alpha_area", 2200))

    run_dir = Path(args.run_dir).expanduser().resolve()
    frames = load_frames(run_dir)
    frame_reports = []
    failures: list[str] = []
    for index, frame in enumerate(frames):
        rgba = frame.convert("RGBA")
        bbox = rgba.getbbox()
        if bbox is None:
            failures.append(f"frame {index:02d} has no foreground")
            continue
        left, top, right, bottom = bbox
        alpha = rgba.getchannel("A")
        tail = tail_region_metrics(rgba, bbox)
        edge = edge_alpha_counts(rgba)
        right_margin = rgba.width - right
        if right_margin < args.min_right_margin:
            failures.append(f"frame {index:02d} right margin too small; tail may be clipped")
        if edge["right"] > 0:
            failures.append(f"frame {index:02d} has alpha on right canvas edge; tail/body is clipped")
        if tail["tail_region_width"] < args.min_tail_region_width:
            failures.append(f"frame {index:02d} tail/right-side silhouette width is too small")
        if tail["tail_region_alpha_area"] < args.min_tail_region_area:
            failures.append(f"frame {index:02d} tail/right-side alpha area is too small")
        frame_reports.append({
            "frame": index,
            "bbox": [left, top, right, bottom],
            "bbox_width": right - left,
            "bbox_height": bottom - top,
            "right_margin_px": right_margin,
            "alpha_area": alpha_area(alpha),
            "edge_alpha_counts": edge,
            **tail,
        })

    widths = [item["bbox_width"] for item in frame_reports]
    heights = [item["bbox_height"] for item in frame_reports]
    areas = [item["alpha_area"] for item in frame_reports]
    tail_widths = [item["tail_region_width"] for item in frame_reports]
    tail_areas = [item["tail_region_alpha_area"] for item in frame_reports]
    width_range = metric_range(widths)
    height_range = metric_range(heights)
    alpha_ratio = round(metric_range(areas) / max(1, max(areas)), 4) if areas else 0
    tail_width_range = metric_range(tail_widths)
    tail_area_ratio = round(metric_range(tail_areas) / max(1, max(tail_areas)), 4) if tail_areas else 0

    if width_range > args.max_bbox_width_range:
        failures.append(f"foreground/body width range {width_range:.1f}px exceeds {args.max_bbox_width_range:.1f}px")
    if height_range > args.max_bbox_height_range:
        failures.append(f"foreground/body height range {height_range:.1f}px exceeds {args.max_bbox_height_range:.1f}px")
    if alpha_ratio > args.max_alpha_area_ratio:
        failures.append(f"foreground alpha area ratio {alpha_ratio:.4f} exceeds {args.max_alpha_area_ratio:.4f}")

    debug_sheet = run_dir / "body_tail_debug_sheet.png"
    make_tail_debug_sheet(frames, debug_sheet)
    status = "pass" if not failures else "fail"
    report = {
        "schema_version": "sofunny-body-tail-consistency.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "profile": profile.get("profile_name"),
        "frame_count": len(frames),
        "thresholds": {
            "max_bbox_width_range_px": args.max_bbox_width_range,
            "max_bbox_height_range_px": args.max_bbox_height_range,
            "max_alpha_area_ratio": args.max_alpha_area_ratio,
            "min_right_margin_px": args.min_right_margin,
            "min_tail_region_width_px": args.min_tail_region_width,
            "min_tail_region_alpha_area": args.min_tail_region_area,
        },
        "metrics": {
            "bbox_width_range_px": width_range,
            "bbox_height_range_px": height_range,
            "alpha_area_range_ratio": alpha_ratio,
            "tail_region_width_range_px": tail_width_range,
            "tail_region_alpha_area_ratio": tail_area_ratio,
        },
        "failures": failures,
        "frames": frame_reports,
        "debug_sheet": str(debug_sheet),
        "notes": [
            "This gate checks consistent body silhouette and complete right-side tail visibility.",
            "A visible jog may still fail if body proportions drift between frames or the tail appears chopped.",
        ],
    }
    write_json(run_dir / "body_tail_consistency_report.json", report)
    print(json.dumps({"status": status, "failures": failures, "debug_sheet": str(debug_sheet)}, ensure_ascii=False, indent=2))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
