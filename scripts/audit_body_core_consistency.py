#!/usr/bin/env python3
"""Audit stable lower/core body volume without treating raised hands as body drift."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sofunny_anim.profiles import load_profile

from PIL import Image, ImageDraw


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_frames(run_dir: Path) -> list[Image.Image]:
    frame_paths = sorted((run_dir / "sequence_frames").glob("*.png"))
    if not frame_paths:
        raise ValueError(f"no sequence frames found in {run_dir / 'sequence_frames'}")
    return [Image.open(path).convert("RGBA") for path in frame_paths]


def alpha_area(alpha: Image.Image, threshold: int = 96) -> int:
    return sum(1 for value in alpha.getdata() if value >= threshold)


def metric_range(values: list[float]) -> float:
    return max(values) - min(values) if values else 0.0


def core_metrics(frame: Image.Image, bbox: tuple[int, int, int, int], core_start_ratio: float, alpha_threshold: int) -> dict:
    left, top, right, bottom = bbox
    height = bottom - top
    core_top = top + round(height * core_start_ratio)
    alpha = frame.getchannel("A")
    core_alpha = alpha.crop((0, core_top, frame.width, bottom))
    core_bbox = core_alpha.getbbox()
    if core_bbox is None:
        return {
            "core_region": [0, core_top, frame.width, bottom],
            "core_bbox": None,
            "core_width": 0,
            "core_height": 0,
            "core_alpha_area": 0,
        }
    cl, ct, cr, cb = core_bbox
    return {
        "core_region": [0, core_top, frame.width, bottom],
        "core_bbox": [cl, core_top + ct, cr, core_top + cb],
        "core_width": cr - cl,
        "core_height": cb - ct,
        "core_alpha_area": alpha_area(core_alpha, alpha_threshold),
    }


def make_debug_sheet(frames: list[Image.Image], reports: list[dict], output: Path) -> None:
    cell = 192
    sheet = Image.new("RGBA", (cell * len(frames), cell), (245, 245, 245, 255))
    for index, (frame, report) in enumerate(zip(frames, reports)):
        img = frame.resize((cell, cell), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(img)
        sx = cell / frame.width
        sy = cell / frame.height
        bbox = report["bbox"]
        draw.rectangle([round(v * (sx if i % 2 == 0 else sy)) for i, v in enumerate(bbox)], outline=(255, 0, 0, 255), width=2)
        core_bbox = report.get("core_bbox")
        if core_bbox:
            draw.rectangle([round(v * (sx if i % 2 == 0 else sy)) for i, v in enumerate(core_bbox)], outline=(0, 140, 80, 255), width=2)
        draw.text((6, 6), f"{index:02d}", fill=(20, 20, 20, 255))
        sheet.alpha_composite(img, (index * cell, 0))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--core-start-ratio", type=float, default=0.46)
    parser.add_argument("--alpha-threshold", type=int, default=96)
    parser.add_argument("--max-core-width-range", type=float, default=24.0)
    parser.add_argument("--max-core-height-range", type=float, default=10.0)
    parser.add_argument("--max-core-alpha-ratio", type=float, default=0.10)
    parser.add_argument("--max-full-height-range", type=float, default=10.0)
    args = parser.parse_args()
    profile = load_profile(args.profile)

    run_dir = Path(args.run_dir).expanduser().resolve()
    frames = load_frames(run_dir)
    failures: list[str] = []
    frame_reports: list[dict] = []
    for index, frame in enumerate(frames):
        bbox = frame.getbbox()
        if bbox is None:
            failures.append(f"frame {index:02d} has no foreground")
            continue
        left, top, right, bottom = bbox
        report = {
            "frame": index,
            "bbox": [left, top, right, bottom],
            "full_width": right - left,
            "full_height": bottom - top,
            "full_alpha_area": alpha_area(frame.getchannel("A"), args.alpha_threshold),
            **core_metrics(frame, bbox, args.core_start_ratio, args.alpha_threshold),
        }
        frame_reports.append(report)

    full_widths = [item["full_width"] for item in frame_reports]
    full_heights = [item["full_height"] for item in frame_reports]
    core_widths = [item["core_width"] for item in frame_reports]
    core_heights = [item["core_height"] for item in frame_reports]
    core_areas = [item["core_alpha_area"] for item in frame_reports]
    core_width_range = metric_range(core_widths)
    core_height_range = metric_range(core_heights)
    core_alpha_ratio = round(metric_range(core_areas) / max(1, max(core_areas)), 4) if core_areas else 0
    full_height_range = metric_range(full_heights)

    if core_width_range > args.max_core_width_range:
        failures.append(f"core body width range {core_width_range:.1f}px exceeds {args.max_core_width_range:.1f}px")
    if core_height_range > args.max_core_height_range:
        failures.append(f"core body height range {core_height_range:.1f}px exceeds {args.max_core_height_range:.1f}px")
    if core_alpha_ratio > args.max_core_alpha_ratio:
        failures.append(f"core body alpha area ratio {core_alpha_ratio:.4f} exceeds {args.max_core_alpha_ratio:.4f}")
    if full_height_range > args.max_full_height_range:
        failures.append(f"full foreground height range {full_height_range:.1f}px exceeds {args.max_full_height_range:.1f}px")

    debug_sheet = run_dir / "body_core_debug_sheet.png"
    make_debug_sheet(frames, frame_reports, debug_sheet)
    status = "pass" if not failures else "fail"
    report = {
        "schema_version": "sofunny-body-core-consistency.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "frame_count": len(frames),
        "thresholds": {
            "core_start_ratio": args.core_start_ratio,
            "alpha_threshold": args.alpha_threshold,
            "max_core_width_range_px": args.max_core_width_range,
            "max_core_height_range_px": args.max_core_height_range,
            "max_core_alpha_ratio": args.max_core_alpha_ratio,
            "max_full_height_range_px": args.max_full_height_range,
        },
        "metrics": {
            "full_width_range_px": metric_range(full_widths),
            "full_height_range_px": full_height_range,
            "core_width_range_px": core_width_range,
            "core_height_range_px": core_height_range,
            "core_alpha_area_ratio": core_alpha_ratio,
        },
        "failures": failures,
        "frames": frame_reports,
        "debug_sheet": str(debug_sheet),
        "notes": [
            "This gate is for actions where hands, sleeves, petals, or props legitimately widen the full foreground.",
            "It checks stable lower/core body volume and full-height consistency while reporting full foreground width separately.",
            "It must not be used to excuse actual torso/skirt deformation, clipping, or identity drift.",
        ],
    }
    write_json(run_dir / "body_core_consistency_report.json", report)
    print(json.dumps({"status": status, "failures": failures, "debug_sheet": str(debug_sheet)}, ensure_ascii=False, indent=2))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
