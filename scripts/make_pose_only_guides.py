#!/usr/bin/env python3
"""Convert motion references into de-identified pose-only guides."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from sofunny_anim.profiles import coalesce, keypose_count, load_profile, phases_for as profile_phases_for

from PIL import Image, ImageDraw

from sofunny_anim.image_io import parse_canvas


PHASES_6 = ["contact", "push_off", "passing", "contact", "push_off", "recover"]
PHASES_12 = [
    "contact",
    "down",
    "push_off",
    "passing",
    "up",
    "recover",
    "contact",
    "down",
    "push_off",
    "passing",
    "up",
    "recover",
]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_reference_frames(path: Path) -> list[Image.Image]:
    if path.is_dir():
        return [Image.open(item).convert("RGBA") for item in sorted(path.glob("*.png"))]
    image = Image.open(path)
    frames = []
    try:
        index = 0
        while True:
            image.seek(index)
            frames.append(image.convert("RGBA"))
            index += 1
    except EOFError:
        pass
    if not frames:
        frames = [image.convert("RGBA")]
    return frames


def sample_frames(frames: list[Image.Image], count: int) -> list[Image.Image]:
    if not frames:
        raise ValueError("motion reference has no frames")
    return [frames[min(len(frames) - 1, int(index * len(frames) / count))] for index in range(count)]


def bbox_metrics(frame: Image.Image) -> dict:
    rgba = frame.convert("RGBA")
    bbox = rgba.getbbox()
    if bbox is None:
        return {"bbox": None}
    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    alpha = rgba.getchannel("A")
    lower_y = bottom - max(8, int(height * 0.18))
    lower_points = []
    for y in range(lower_y, bottom):
        for x in range(left, right):
            if alpha.getpixel((x, y)) > 0:
                lower_points.append((x, y))
    if lower_points:
        anchor_x = sum(x for x, _ in lower_points) / len(lower_points)
    else:
        anchor_x = (left + right) / 2
    return {
        "bbox": [left, top, right, bottom],
        "center_x": (left + right) / 2,
        "center_y": (top + bottom) / 2,
        "width": width,
        "height": height,
        "anchor_x": anchor_x,
        "anchor_bottom": bottom,
    }


def draw_stick_guide(draw: ImageDraw.ImageDraw, origin_x: int, cell: tuple[int, int], phase: str, metric: dict, index: int) -> dict:
    cell_w, cell_h = cell
    cx = origin_x + cell_w // 2
    ground = cell_h - 36
    if metric.get("bbox"):
        body_scale = max(0.75, min(1.25, metric["height"] / 260))
        lateral = int((metric["anchor_x"] - metric["center_x"]) * 0.18)
        vertical = int((metric["anchor_bottom"] - metric["center_y"]) * 0.05) - 8
    else:
        body_scale = 1.0
        lateral = 0
        vertical = 0
    body_cx = cx + lateral
    head_y = 96 + vertical
    neck_y = int(150 + vertical * 0.4)
    hip_y = int(238 + vertical * 0.25)
    shoulder_w = int(76 * body_scale)
    hip_w = int(48 * body_scale)
    bounce = -8 if "up" in phase or "passing" in phase else (6 if "down" in phase or "contact" in phase else 0)
    head_y += bounce
    neck_y += bounce
    hip_y += bounce

    is_left_contact = index % 6 < 3
    if is_left_contact:
        left_foot = (body_cx - 38, ground)
        right_foot = (body_cx + 34, ground - (24 if "passing" in phase or "up" in phase else 10))
    else:
        left_foot = (body_cx - 34, ground - (24 if "passing" in phase or "up" in phase else 10))
        right_foot = (body_cx + 38, ground)
    arm_bias = -1 if is_left_contact else 1
    left_hand = (body_cx - 74, neck_y + 58 + arm_bias * 14)
    right_hand = (body_cx + 74, neck_y + 58 - arm_bias * 14)

    color = (18, 24, 32, 255)
    muted = (88, 96, 110, 255)
    draw.line((origin_x + 24, ground, origin_x + cell_w - 24, ground), fill=(0, 0, 0, 110), width=2)
    draw.ellipse((body_cx - 34, head_y - 34, body_cx + 34, head_y + 34), outline=color, width=5)
    draw.line((body_cx, head_y + 34, body_cx, hip_y), fill=color, width=6)
    draw.line((body_cx - shoulder_w // 2, neck_y, body_cx + shoulder_w // 2, neck_y), fill=color, width=5)
    draw.line((body_cx - hip_w // 2, hip_y, body_cx + hip_w // 2, hip_y), fill=color, width=5)
    draw.line((body_cx - shoulder_w // 2, neck_y, *left_hand), fill=color, width=5)
    draw.line((body_cx + shoulder_w // 2, neck_y, *right_hand), fill=color, width=5)
    draw.line((body_cx - hip_w // 2, hip_y, *left_foot), fill=color, width=6)
    draw.line((body_cx + hip_w // 2, hip_y, *right_foot), fill=color, width=6)
    for point in [left_hand, right_hand, left_foot, right_foot]:
        draw.ellipse((point[0] - 7, point[1] - 7, point[0] + 7, point[1] + 7), fill=muted)
    tail_tip = (body_cx + 88 - arm_bias * 12, hip_y + 4)
    draw.line((body_cx + hip_w // 2, hip_y - 8, *tail_tip), fill=color, width=5)
    draw.text((origin_x + 8, 8), f"{index:02d} {phase}", fill=(0, 0, 0, 255))
    draw.text((origin_x + 8, cell_h - 22), "POSE ONLY", fill=(0, 0, 0, 180))
    return {
        "frame": index,
        "phase": phase,
        "body_center": [body_cx, round((head_y + hip_y) / 2)],
        "ground_y": ground,
        "left_foot": list(left_foot),
        "right_foot": list(right_foot),
        "identity_removed": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--motion-reference", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--frames", type=int)
    parser.add_argument("--canvas", type=parse_canvas)
    args = parser.parse_args()
    profile = load_profile(args.profile)
    args.frames = args.frames if args.frames is not None else keypose_count(profile, "production", 12)
    args.canvas = parse_canvas(coalesce(args.canvas, profile, "default_canvas", "384x384")) if args.canvas is None else args.canvas

    reference = Path(args.motion_reference).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    frames = sample_frames(read_reference_frames(reference), args.frames)
    fallback_phases = PHASES_12 if args.frames == 12 else PHASES_6 if args.frames == 6 else None
    phases = profile_phases_for(profile, args.frames, fallback=fallback_phases)
    cell_w, cell_h = args.canvas
    columns = min(6, args.frames)
    rows = math.ceil(args.frames / columns)
    sheet = Image.new("RGBA", (columns * cell_w, rows * cell_h), (255, 255, 255, 255))
    reports = []
    for index, frame in enumerate(frames):
        cell = Image.new("RGBA", args.canvas, (255, 255, 255, 255))
        draw = ImageDraw.Draw(cell)
        report = draw_stick_guide(draw, 0, args.canvas, phases[index], bbox_metrics(frame), index)
        reports.append(report)
        x = (index % columns) * cell_w
        y = (index // columns) * cell_h
        sheet.alpha_composite(cell, (x, y))
    output_sheet = output_dir / "pose_only_guide_sheet.png"
    sheet.save(output_sheet)
    write_json(
        output_dir / "pose_only_guide_manifest.json",
        {
            "schema_version": "sofunny-pose-only-guide.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "profile": profile.get("profile_name"),
            "motion_reference": str(reference),
            "output_sheet": str(output_sheet),
            "frame_count": args.frames,
            "canvas": {"width": cell_w, "height": cell_h},
            "identity_removed": True,
            "forbidden_source_traits": ["face", "costume", "color", "donor_identity", "texture"],
            "allowed_traits": ["anchor_points", "phase_labels", "stick_figure", "ground_contact", "motion_timing"],
            "frames": reports,
        },
    )
    print(str(output_sheet))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
