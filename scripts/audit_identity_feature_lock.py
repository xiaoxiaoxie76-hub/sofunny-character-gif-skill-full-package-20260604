#!/usr/bin/env python3
"""Create a feature-level identity review packet for a SoFunny candidate."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sofunny_anim.profiles import load_profile

from PIL import Image, ImageDraw


FEATURE_CHECKS = [
    "same compact original head/face silhouette",
    "small thin black glasses placed low over half-lidded eyes",
    "small symbolic nose/mouth/teeth, no large white muzzle redesign",
    "original swept brown hair tuft shape and hairline direction",
    "small ears embedded into the head silhouette",
    "narrow charcoal suit body with white shirt and blue tie",
    "tail attached from character right rear hip with same size range and stripe rhythm",
    "clean SoFunny mobile-game outline, no heavier generic provider redraw",
]


def read_json(path: Path, default: dict | None = None) -> dict:
    if not path.exists():
        return default or {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    return image.convert("RGBA").getbbox()


def bbox_metrics(image: Image.Image) -> dict:
    bbox = alpha_bbox(image)
    if bbox is None:
        return {"bbox": None}
    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    return {
        "bbox": [left, top, right, bottom],
        "bbox_width": width,
        "bbox_height": height,
        "bbox_aspect": round(width / height, 4) if height else 0,
        "bbox_center": [round((left + right) / 2, 2), round((top + bottom) / 2, 2)],
        "alpha_area": sum(1 for value in image.convert("RGBA").getchannel("A").getdata() if value > 0),
    }


def resize_into_cell(image: Image.Image, cell: tuple[int, int], label: str) -> Image.Image:
    out = Image.new("RGBA", cell, (255, 255, 255, 255))
    draw = ImageDraw.Draw(out)
    step = 16
    for y in range(0, cell[1], step):
        for x in range(0, cell[0], step):
            if ((x // step) + (y // step)) % 2 == 0:
                draw.rectangle((x, y, min(cell[0] - 1, x + step - 1), min(cell[1] - 1, y + step - 1)), fill=(232, 232, 232, 255))
    rgba = image.convert("RGBA")
    bbox = alpha_bbox(rgba)
    if bbox:
        crop = rgba.crop(bbox)
        crop.thumbnail((cell[0] - 36, cell[1] - 42), Image.Resampling.LANCZOS)
        out.alpha_composite(crop, ((cell[0] - crop.width) // 2, cell[1] - 18 - crop.height))
    draw.rectangle((0, 0, cell[0] - 1, cell[1] - 1), outline=(180, 180, 180, 255), width=1)
    draw.text((6, 6), label, fill=(20, 20, 20, 255))
    return out


def make_comparison_sheet(reference: Image.Image, frames: list[Image.Image], output: Path) -> None:
    cell = (192, 220)
    columns = 1 + len(frames)
    sheet = Image.new("RGBA", (columns * cell[0], cell[1]), (245, 245, 245, 255))
    sheet.alpha_composite(resize_into_cell(reference, cell, "canonical"), (0, 0))
    for index, frame in enumerate(frames):
        sheet.alpha_composite(resize_into_cell(frame, cell, f"frame {index:02d}"), ((index + 1) * cell[0], 0))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def load_frames(run_dir: Path) -> list[Image.Image]:
    frame_paths = sorted((run_dir / "sequence_frames").glob("*.png"))
    if not frame_paths:
        raise ValueError(f"no sequence frames found in {run_dir / 'sequence_frames'}")
    return [Image.open(path).convert("RGBA") for path in frame_paths]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--reference", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--status", choices=["pass", "warn", "fail", "manual_required"], default="manual_required")
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--required-fix", action="append", default=[])
    parser.add_argument("--note", action="append", default=[])
    args = parser.parse_args()
    profile = load_profile(args.profile)

    reference_path = Path(args.reference).expanduser().resolve()
    run_dir = Path(args.run_dir).expanduser().resolve()
    reference = Image.open(reference_path).convert("RGBA")
    frames = load_frames(run_dir)
    output_sheet = run_dir / "identity_feature_comparison.png"
    make_comparison_sheet(reference, frames, output_sheet)

    frame_metrics = [bbox_metrics(frame) | {"frame": index} for index, frame in enumerate(frames)]
    widths = [item["bbox_width"] for item in frame_metrics if item.get("bbox_width")]
    heights = [item["bbox_height"] for item in frame_metrics if item.get("bbox_height")]
    aspects = [item["bbox_aspect"] for item in frame_metrics if item.get("bbox_aspect")]
    centers_x = [item["bbox_center"][0] for item in frame_metrics if item.get("bbox_center")]
    ref_metrics = bbox_metrics(reference)
    report = {
        "schema_version": "sofunny-identity-feature-lock.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": args.status,
        "reviewer": args.reviewer,
        "reference": str(reference_path),
        "run_dir": str(run_dir),
        "comparison_sheet": str(output_sheet),
        "mode": "feature identity lock, not static-pose lock",
        "reference_metrics": ref_metrics,
        "candidate_metrics": {
            "frame_count": len(frames),
            "bbox_width_range_px": max(widths) - min(widths) if widths else 0,
            "bbox_height_range_px": max(heights) - min(heights) if heights else 0,
            "bbox_aspect_range": round(max(aspects) - min(aspects), 4) if aspects else 0,
            "bbox_center_x_range_px": round(max(centers_x) - min(centers_x), 2) if centers_x else 0,
            "frames": frame_metrics,
        },
        "manual_feature_checks": [
            {"feature": feature, "status": "unchecked"} for feature in FEATURE_CHECKS
        ],
        "required_fixes": args.required_fix,
        "notes": args.note,
        "pass_rule": "Set status=pass only after direct visual review confirms every feature remains the same character while allowing action pose changes.",
    }
    write_json(run_dir / "identity_feature_lock_report.json", report)

    markdown = [
        "# Identity Feature Lock Review",
        "",
        "This review checks character identity features, not pixel similarity to the source pose.",
        "",
        f"- Status: `{args.status}`",
        f"- Comparison sheet: `{output_sheet}`",
        "",
        "## Required Checks",
        "",
    ]
    markdown.extend(f"- [ ] {feature}" for feature in FEATURE_CHECKS)
    if args.required_fix:
        markdown.extend(["", "## Required Fixes", ""])
        markdown.extend(f"- {fix}" for fix in args.required_fix)
    if args.note:
        markdown.extend(["", "## Notes", ""])
        markdown.extend(f"- {note}" for note in args.note)
    (run_dir / "identity_feature_lock_review.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print(json.dumps({"status": args.status, "comparison_sheet": str(output_sheet)}, ensure_ascii=False, indent=2))
    return 0 if args.status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
