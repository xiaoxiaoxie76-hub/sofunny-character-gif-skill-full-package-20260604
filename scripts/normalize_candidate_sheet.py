#!/usr/bin/env python3
"""Normalize offsets in a generated SoFunny candidate sheet.

This is an intake tool for high-value animation candidates produced by tools like
game-character-sprites. It preserves the candidate pose art and fixes packaging
instability: baked checker backgrounds, inconsistent frame offsets, unstable
bottom anchors, and uneven body centers.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sofunny_anim.profiles import load_profile
from typing import Iterable

from PIL import Image, ImageChops, ImageDraw


@dataclass
class AnchorMetrics:
    frame: int
    bbox: tuple[int, int, int, int]
    foreground_center_x: float
    lower_body_anchor_x: float
    anchor_bottom: int
    foreground_width: int
    foreground_height: int


def parse_canvas(value: str) -> tuple[int, int]:
    parts = value.lower().split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("canvas must use WIDTHxHEIGHT, e.g. 384x384")
    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("canvas width and height must be integers") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("canvas width and height must be positive")
    return width, height


def is_checker_bg_pixel(pixel: tuple[int, int, int, int]) -> bool:
    r, g, b, a = pixel
    if a == 0:
        return True
    hi = max(r, g, b)
    lo = min(r, g, b)
    return hi >= 225 and (hi - lo) <= 28


def edge_connected_background_mask(image: Image.Image) -> set[tuple[int, int]]:
    """Find bright low-saturation background pixels connected to the frame edge."""

    rgba = image.convert("RGBA")
    width, height = rgba.size
    pix = rgba.load()
    visited: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int]] = deque()

    def maybe_add(x: int, y: int) -> None:
        if (x, y) in visited:
            return
        if is_checker_bg_pixel(pix[x, y]):
            visited.add((x, y))
            queue.append((x, y))

    for x in range(width):
        maybe_add(x, 0)
        maybe_add(x, height - 1)
    for y in range(height):
        maybe_add(0, y)
        maybe_add(width - 1, y)

    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                maybe_add(nx, ny)
    return visited


def remove_baked_background(image: Image.Image, background: str) -> Image.Image:
    rgba = image.convert("RGBA")
    if background == "transparent":
        return rgba
    if background != "checker":
        raise ValueError(f"unsupported background mode: {background}")

    bg = edge_connected_background_mask(rgba)
    pix = rgba.load()
    for x, y in bg:
        r, g, b, _ = pix[x, y]
        pix[x, y] = (r, g, b, 0)
    return rgba


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    bbox = image.getbbox()
    if bbox is None:
        raise ValueError("frame has no foreground after background removal")
    return bbox


def alpha_points(image: Image.Image) -> Iterable[tuple[int, int]]:
    alpha = image.getchannel("A")
    pix = alpha.load()
    width, height = alpha.size
    for y in range(height):
        for x in range(width):
            if pix[x, y] > 0:
                yield x, y


def median(values: list[float]) -> float:
    if not values:
        raise ValueError("cannot compute median of empty list")
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def compute_anchor(image: Image.Image, frame_index: int) -> AnchorMetrics:
    bbox = alpha_bbox(image)
    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    all_xs: list[int] = []
    lower_xs: list[int] = []
    lower_start = bottom - max(12, int(height * 0.18))
    for x, y in alpha_points(image):
        if left <= x < right and top <= y < bottom:
            all_xs.append(x)
            if y >= lower_start:
                lower_xs.append(x)
    if not lower_xs:
        lower_xs = all_xs[:]
    return AnchorMetrics(
        frame=frame_index,
        bbox=bbox,
        foreground_center_x=(left + right) / 2,
        lower_body_anchor_x=median([float(x) for x in lower_xs]),
        anchor_bottom=bottom,
        foreground_width=width,
        foreground_height=height,
    )


def split_horizontal_sheet(image: Image.Image, frames: int) -> list[Image.Image]:
    width, height = image.size
    if width % frames != 0:
        raise ValueError(f"input width {width} is not divisible by frames {frames}")
    cell_width = width // frames
    return [image.crop((i * cell_width, 0, (i + 1) * cell_width, height)) for i in range(frames)]


def make_checker(size: tuple[int, int], step: int = 16) -> Image.Image:
    image = Image.new("RGBA", size, (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    width, height = size
    for y in range(0, height, step):
        for x in range(0, width, step):
            if ((x // step) + (y // step)) % 2 == 0:
                draw.rectangle((x, y, min(width - 1, x + step - 1), min(height - 1, y + step - 1)), fill=(226, 226, 226, 255))
    return image


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def range_of(values: list[float]) -> float:
    return max(values) - min(values) if values else 0.0


def export_contact_sheet(frames: list[Image.Image], output: Path, cell_size: int = 192) -> None:
    columns = min(6, len(frames))
    rows = math.ceil(len(frames) / columns)
    sheet = Image.new("RGBA", (columns * cell_size, rows * cell_size), (245, 245, 245, 255))
    for i, frame in enumerate(frames):
        cell = make_checker((cell_size, cell_size), 16)
        thumb = frame.resize((cell_size, cell_size), Image.Resampling.LANCZOS)
        cell.alpha_composite(thumb)
        draw = ImageDraw.Draw(cell)
        draw.rectangle((0, 0, cell_size - 1, cell_size - 1), outline=(180, 180, 180, 255), width=1)
        draw.text((6, 6), f"{i:02d}", fill=(20, 20, 20, 255))
        sheet.alpha_composite(cell, ((i % columns) * cell_size, (i // columns) * cell_size))
    sheet.save(output)


def export_checker_gif(frames: list[Image.Image], output: Path, duration: int) -> None:
    checker_frames = []
    for frame in frames:
        bg = make_checker(frame.size, 24)
        bg.alpha_composite(frame)
        checker_frames.append(bg.convert("P", palette=Image.Palette.ADAPTIVE))
    checker_frames[0].save(output, save_all=True, append_images=checker_frames[1:], duration=duration, loop=0, disposal=2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--input", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--frames", type=int, required=True)
    parser.add_argument("--canvas", type=parse_canvas, default=parse_canvas("384x384"))
    parser.add_argument("--action", required=True)
    parser.add_argument("--character-name", required=True)
    parser.add_argument("--background", choices=["checker", "transparent"], default="checker")
    parser.add_argument("--duration-ms", type=int, default=100)
    parser.add_argument("--margin", type=int, default=24)
    args = parser.parse_args()
    profile = load_profile(args.profile)

    if args.frames <= 0:
        parser.error("--frames must be positive")
    if args.duration_ms <= 0:
        parser.error("--duration-ms must be positive")

    input_path = Path(args.input).expanduser().resolve()
    run_dir = Path(args.run_dir).expanduser().resolve()
    source_dir = run_dir / "source"
    raw_dir = run_dir / "raw_candidate_frames"
    sequence_dir = run_dir / "sequence_frames"
    for directory in [source_dir, raw_dir, sequence_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    briefs_dir = run_dir / "generation_briefs"
    briefs_dir.mkdir(parents=True, exist_ok=True)

    source_copy = source_dir / input_path.name
    shutil.copy2(input_path, source_copy)
    candidate_manifest_path = run_dir / "candidate_manifest.json"
    candidate_manifest = {}
    if candidate_manifest_path.exists():
        try:
            candidate_manifest = json.loads(candidate_manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            candidate_manifest = {"route": "invalid_candidate_manifest", "admission_eligible": False}

    raw_sheet = Image.open(input_path).convert("RGBA")
    raw_frames = split_horizontal_sheet(raw_sheet, args.frames)
    extracted_frames = [remove_baked_background(frame, args.background) for frame in raw_frames]
    before_metrics = [compute_anchor(frame, i) for i, frame in enumerate(extracted_frames)]

    max_width = max(metric.foreground_width for metric in before_metrics)
    max_height = max(metric.foreground_height for metric in before_metrics)
    canvas_w, canvas_h = args.canvas
    scale = min((canvas_w - args.margin * 2) / max_width, (canvas_h - args.margin * 2) / max_height)
    if scale <= 0:
        raise ValueError("canvas and margin leave no room for the character")

    target_center_x = canvas_w / 2
    target_bottom = canvas_h - args.margin
    normalized_frames: list[Image.Image] = []

    for i, frame in enumerate(extracted_frames):
        frame.save(raw_dir / f"{i:03d}.png")
        metric = before_metrics[i]
        crop = frame.crop(metric.bbox)
        crop_w = max(1, round(crop.width * scale))
        crop_h = max(1, round(crop.height * scale))
        scaled = crop.resize((crop_w, crop_h), Image.Resampling.LANCZOS)

        anchor_x_in_crop = (metric.lower_body_anchor_x - metric.bbox[0]) * scale
        anchor_bottom_in_crop = (metric.anchor_bottom - metric.bbox[1]) * scale
        paste_x = round(target_center_x - anchor_x_in_crop)
        paste_y = round(target_bottom - anchor_bottom_in_crop)

        canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        canvas.alpha_composite(scaled, (paste_x, paste_y))
        canvas.save(sequence_dir / f"{i:03d}.png")
        normalized_frames.append(canvas)

    after_metrics = [compute_anchor(frame, i) for i, frame in enumerate(normalized_frames)]
    export_contact_sheet(normalized_frames, run_dir / "contact_sheet_full_canvas.png", 192)
    export_contact_sheet(normalized_frames, run_dir / "contact_sheet.png", 256)
    normalized_frames[0].save(
        run_dir / "animation.gif",
        save_all=True,
        append_images=normalized_frames[1:],
        duration=args.duration_ms,
        loop=0,
        disposal=2,
    )
    export_checker_gif(normalized_frames, run_dir / "animation_checker.gif", args.duration_ms)

    diff = ImageChops.difference(normalized_frames[0], normalized_frames[-1])
    loop_delta_sum = sum(diff.convert("L").getdata()) if diff.getbbox() else 0

    before_bottoms = [metric.anchor_bottom for metric in before_metrics]
    before_centers = [metric.lower_body_anchor_x for metric in before_metrics]
    after_bottoms = [metric.anchor_bottom for metric in after_metrics]
    after_centers = [metric.lower_body_anchor_x for metric in after_metrics]
    after_bottom_range = range_of([float(value) for value in after_bottoms])
    after_center_range = range_of([float(value) for value in after_centers])
    offset_status = "pass" if after_bottom_range <= 1 and after_center_range <= 6 else "warn"
    candidate_route = candidate_manifest.get("route", "external_or_unclassified_candidate_sheet")
    admission_eligible = bool(candidate_manifest.get("admission_eligible", False))
    status = offset_status if admission_eligible else "pipeline_smoke"

    report = {
        "status": status,
        "offset_status": offset_status,
        "candidate_route": candidate_route,
        "admission_eligible": admission_eligible,
        "input": str(input_path),
        "source_copy": str(source_copy),
        "character_name": args.character_name,
        "action": args.action,
        "frame_count": args.frames,
        "canvas": {"width": canvas_w, "height": canvas_h},
        "scale": scale,
        "alignment_strategy": {
            "bottom": "fixed target bottom after foreground extraction",
            "center_x": "median x of lower foreground band, not whole bbox center",
            "background": args.background,
        },
        "before": {
            "bbox_bottom_range_px": range_of([float(value) for value in before_bottoms]),
            "anchor_center_x_range_px": range_of([float(value) for value in before_centers]),
        },
        "after": {
            "bbox_bottom_range_px": after_bottom_range,
            "anchor_center_x_range_px": after_center_range,
            "loop_delta_sum": loop_delta_sum,
        },
        "frame_metrics": [
            {
                "frame": metric.frame,
                "before_bbox": before_metrics[i].bbox,
                "before_anchor_bottom": before_metrics[i].anchor_bottom,
                "before_lower_body_anchor_x": round(before_metrics[i].lower_body_anchor_x, 2),
                "after_bbox": metric.bbox,
                "after_anchor_bottom": metric.anchor_bottom,
                "after_lower_body_anchor_x": round(metric.lower_body_anchor_x, 2),
            }
            for i, metric in enumerate(after_metrics)
        ],
    }
    write_json(run_dir / "offset_normalization_report.json", report)

    jitter = {
        "status": offset_status,
        "frame_count": args.frames,
        "duration_ms": args.duration_ms,
        "bbox_bottom_range_px": after_bottom_range,
        "center_x_range_px": after_center_range,
        "loop_delta_sum": loop_delta_sum,
        "notes": [
            f"Offset-normalized candidate imported from {candidate_route}.",
            "Pose art is preserved; only background removal, uniform scaling, and anchor placement were applied.",
        ],
    }
    write_json(run_dir / "jitter_diagnostics.json", jitter)

    identity_lock = {
        "character_name": args.character_name,
        "canonical_reference": {
            "source_type": "game-character-sprites-candidate-sheet",
            "source": str(source_copy),
            "used_for_generation": True,
        },
        "must_keep": {
            "face": [],
            "body_shape": [],
            "headwear_or_hair": [],
            "tail": [],
            "accessories": [],
            "palette": [],
            "line_style": [],
            "proportions": [],
        },
        "forbidden_drift": [
            "changed face",
            "changed body silhouette",
            "missing accessory",
            "unstable tail",
            "wrong palette",
            "fake transparency",
            "checkerboard artifact",
        ],
        "review_status": "pending_manual_review",
        "notes": [
            "Imported from game-character-sprites candidate; fill must_keep after visual inspection.",
            "Offset normalization preserves pose art and does not redraw identity features.",
        ],
    }
    write_json(run_dir / "identity-lock.json", identity_lock)

    motion_contract = {
        "action_name": args.action,
        "target_frames": args.frames,
        "canvas": {"width": canvas_w, "height": canvas_h, "transparent": True},
        "phases": [
            {"name": "neutral_start", "frames": [0, 0], "description": "initial readable character pose"},
            {"name": "anticipation", "frames": [1, 1], "description": "prepares the action"},
            {"name": "main_action", "frames": [2, max(2, args.frames - 3)], "description": "primary action poses inherited from candidate sheet"},
            {"name": "settle", "frames": [max(0, args.frames - 2), max(0, args.frames - 2)], "description": "returns toward neutral"},
            {"name": "loop_return", "frames": [args.frames - 1, args.frames - 1], "description": "final pose connects back to frame 0"},
        ],
        "anchor_rules": {
            "fixed_ground_contact": True,
            "max_bbox_bottom_range_px": 1,
            "max_anchor_center_x_range_px": 6,
            "measured_bbox_bottom_range_px": after_bottom_range,
            "measured_anchor_center_x_range_px": after_center_range,
        },
        "review_status": "pending_manual_review",
        "notes": [
            "Motion phases are inherited from the candidate sheet and must be inspected in contact_sheet.png.",
        ],
    }
    write_json(run_dir / "motion-contract.json", motion_contract)

    (briefs_dir / "keyposes.md").write_text(
        f"# {args.character_name} {args.action} Candidate Keyposes\n\n"
        "Source: imported `game-character-sprites` candidate sheet.\n\n"
        "The action poses are considered high-value input and should be preserved unless visual QA rejects them.\n\n"
        "Required review:\n\n"
        "- Confirm identity remains the intended SoFunny character.\n"
        "- Confirm action reads clearly after offset normalization.\n"
        "- Mark weak frames explicitly before local redraw; do not regenerate strong frames.\n",
        encoding="utf-8",
    )
    (briefs_dir / "sequence.md").write_text(
        f"# {args.character_name} {args.action} Offset-Normalized Sequence\n\n"
        f"Frame count: {args.frames}\n"
        f"Canvas: {canvas_w}x{canvas_h}\n"
        f"Duration: {args.duration_ms}ms per frame\n"
        "Route: `game-character-sprites-intake -> offset_normalization`.\n\n"
        "Admission target:\n\n"
        "- `bbox_bottom_range_px <= 1`\n"
        "- `anchor_center_x_range_px <= 6`\n"
        "- body center looks stable in `contact_sheet_full_canvas.png`\n"
        "- no pose-art regression from normalization\n",
        encoding="utf-8",
    )

    style_lock_report = {
        "status": "blocked_by_candidate_route" if not admission_eligible else "pending_manual_review",
        "identity_match": "pending",
        "drift_findings": [],
        "notes": [
            "Normalizer does not judge character likeness automatically.",
            "Set status to pass only after contact sheet and animation preview preserve the intended SoFunny character.",
            "Local component-rig pipeline-smoke candidates are not admission-eligible for actions requiring new limb poses.",
        ],
    }
    write_json(run_dir / "style_lock_report.json", style_lock_report)

    visual_review = {
        "status": "blocked_by_candidate_route" if not admission_eligible else "pending_manual_review",
        "contact_sheet_reviewed": False,
        "animation_reviewed": False,
        "identity": "pending",
        "motion": "pending",
        "export_quality": "pending",
        "required_fixes": [
            "Candidate source is not admission-eligible for this action; generate real limb-pose candidate frames."
        ] if not admission_eligible else [],
        "review_notes": [
            "Inspect contact_sheet.png, contact_sheet_full_canvas.png, and animation_checker.gif before admission.",
        ],
    }
    write_json(run_dir / "visual-review.json", visual_review)

    admission_report = (
        "# Admission Report\n\n"
        f"Status: {'PIPELINE_SMOKE_NOT_ADMISSION_ELIGIBLE' if not admission_eligible else 'PENDING_MANUAL_REVIEW'}\n\n"
        "## Candidate Source\n\n"
        f"- Input: `{input_path}`\n"
        f"- Candidate route: `{candidate_route}`\n"
        "- Route: `candidate_sheet -> offset_normalization`\n"
        "- Pose art preserved: true\n\n"
        "## Offset Metrics\n\n"
        f"- Before bbox bottom range: `{report['before']['bbox_bottom_range_px']}`\n"
        f"- Before lower-body anchor center range: `{report['before']['anchor_center_x_range_px']}`\n"
        f"- After bbox bottom range: `{report['after']['bbox_bottom_range_px']}`\n"
        f"- After lower-body anchor center range: `{report['after']['anchor_center_x_range_px']}`\n\n"
        "## Manual Gate\n\n"
        "Set visual/style reports to pass only after direct inspection confirms stable body placement, preserved identity, readable action, and clean export.\n"
        + ("This candidate is not admission-eligible because its source route is pipeline smoke only.\n" if not admission_eligible else "")
    )
    (run_dir / "admission_report.md").write_text(admission_report, encoding="utf-8")

    manifest = {
        "schema_version": "sofunny-character-gif.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "character_name": args.character_name,
        "action_name": args.action,
        "status": "PIPELINE_SMOKE_OFFSET_NORMALIZED" if not admission_eligible else ("OFFSET_NORMALIZED" if offset_status == "pass" else "OFFSET_NORMALIZATION_WARN"),
        "reference": {
            "source_type": "game-character-sprites-candidate-sheet",
            "source": str(source_copy),
            "used_for_generation": True,
        },
        "generation": {
            "route": candidate_route,
            "postprocess": "offset_normalization",
            "pose_art_preserved": True,
            "admission_eligible": admission_eligible,
        },
        "artifacts": {
            "sequence_frames": "sequence_frames/",
            "contact_sheet": "contact_sheet.png",
            "contact_sheet_full_canvas": "contact_sheet_full_canvas.png",
            "animation": "animation.gif",
            "animation_checker": "animation_checker.gif",
            "offset_report": "offset_normalization_report.json",
            "jitter_diagnostics": "jitter_diagnostics.json",
        },
    }
    write_json(run_dir / "sofunny-run-manifest.json", manifest)

    print(json.dumps({"run_dir": str(run_dir), "status": status, "offset_status": offset_status, "candidate_route": candidate_route, "admission_eligible": admission_eligible, "before": report["before"], "after": report["after"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
