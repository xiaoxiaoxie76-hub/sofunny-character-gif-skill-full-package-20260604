#!/usr/bin/env python3
"""Generate a local reference-locked bow candidate with stable atlas safety."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

from sofunny_anim.frame_layout import write_sequence
from sofunny_anim.image_io import parse_canvas, remove_background
from sofunny_anim.manifests import write_json
from sofunny_anim.previews import save_checker_gif, save_contact_sheet, save_matte_gif, save_transparent_gif, save_transparent_sheet, save_webp


def bow_amount(index: int, frames: int) -> float:
    if frames <= 1:
        return 0.0
    def smoothstep(value: float) -> float:
        value = max(0.0, min(1.0, value))
        return value * value * (3.0 - 2.0 * value)

    phase = index / (frames - 1)
    if phase < 0.42:
        return smoothstep(phase / 0.42)
    if phase < 0.55:
        return 1.0
    return 1.0 - smoothstep((phase - 0.55) / 0.45)


def prepare_reference(reference: Image.Image) -> Image.Image:
    rgba = remove_background(reference.convert("RGBA"), "white")
    pix = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            r, g, b, a = pix[x, y]
            if a == 0:
                continue
            hi = max(r, g, b)
            lo = min(r, g, b)
            if r >= 238 and g >= 238 and b >= 238:
                pix[x, y] = (r, g, b, 0)
            elif hi >= 225 and hi - lo <= 18:
                pix[x, y] = (r, g, b, 0)
    bbox = rgba.getbbox()
    if bbox is None:
        raise ValueError("reference has no visible foreground")
    return rgba.crop(bbox)


def build_bow_layer(crop: Image.Image, amount: float, scale: float) -> Image.Image:
    scaled = crop.resize(
        (max(1, round(crop.width * scale)), max(1, round(crop.height * scale))),
        Image.Resampling.LANCZOS,
    )
    split_y = round(scaled.height * 0.58)
    overlap = max(12, round(scaled.height * 0.08))
    upper = scaled.crop((0, 0, scaled.width, min(scaled.height, split_y + overlap)))
    lower = scaled.crop((0, split_y, scaled.width, scaled.height))

    canvas = Image.new("RGBA", (round(scaled.width * 1.22), round(scaled.height * 1.10)), (0, 0, 0, 0))
    base_x = round((canvas.width - scaled.width) / 2)
    base_y = round(canvas.height - scaled.height)
    canvas.alpha_composite(lower, (base_x, base_y + split_y))

    angle = -round(amount * 7.5, 2)
    rotated_upper = upper.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    upper_x = base_x + round((upper.width - rotated_upper.width) / 2 - amount * scaled.width * 0.035)
    upper_y = base_y + round(amount * scaled.height * 0.16)
    canvas.alpha_composite(rotated_upper, (upper_x, upper_y))

    bbox = canvas.getbbox()
    if bbox is None:
        raise ValueError("empty bow layer")
    return canvas.crop(bbox)


def draw_joined_hand_hint(frame: Image.Image, bbox: tuple[int, int, int, int], amount: float) -> None:
    if amount < 0.25:
        return
    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    cx = round((left + right) / 2)
    cy = top + round(height * (0.55 + amount * 0.06))
    draw = ImageDraw.Draw(frame, "RGBA")
    sleeve = (92, 166, 132, round(120 * min(1.0, amount)))
    skin = (250, 206, 170, round(160 * min(1.0, amount)))
    outline = (45, 80, 62, round(120 * min(1.0, amount)))
    hand_gap = round(width * (0.08 - min(0.05, amount * 0.04)))
    draw.ellipse((cx - hand_gap - 14, cy - 10, cx - hand_gap + 14, cy + 12), fill=sleeve, outline=outline, width=2)
    draw.ellipse((cx + hand_gap - 14, cy - 10, cx + hand_gap + 14, cy + 12), fill=sleeve, outline=outline, width=2)
    draw.ellipse((cx - 10, cy - 7, cx + 10, cy + 9), fill=skin, outline=outline, width=1)


def align_bottom(frame: Image.Image, baseline: int, canvas: tuple[int, int]) -> Image.Image:
    bbox = frame.getbbox()
    if bbox is None:
        raise ValueError("cannot align empty frame")
    crop = frame.crop(bbox)
    out = Image.new("RGBA", canvas, (0, 0, 0, 0))
    paste_x = round((canvas[0] - crop.width) / 2)
    paste_y = baseline - crop.height
    out.alpha_composite(crop, (paste_x, paste_y))
    return out


def align_center(frame: Image.Image, canvas: tuple[int, int]) -> Image.Image:
    bbox = frame.getbbox()
    if bbox is None:
        raise ValueError("cannot center empty frame")
    crop = frame.crop(bbox)
    out = Image.new("RGBA", canvas, (0, 0, 0, 0))
    paste_x = round((canvas[0] - crop.width) / 2)
    paste_y = round((canvas[1] - crop.height) / 2)
    out.alpha_composite(crop, (paste_x, paste_y))
    return out


def save_grid_sheet(frames: list[Image.Image], output: Path, rows: int, columns: int) -> None:
    if rows * columns < len(frames):
        raise ValueError("grid does not have enough cells")
    cell_w, cell_h = frames[0].size
    sheet = Image.new("RGBA", (cell_w * columns, cell_h * rows), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        row, col = divmod(index, columns)
        sheet.alpha_composite(frame.convert("RGBA"), (col * cell_w, row * cell_h))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def generate_frames(reference: Image.Image, canvas: tuple[int, int], frames: int, margin: int) -> tuple[list[Image.Image], dict]:
    crop = prepare_reference(reference)
    canvas_w, canvas_h = canvas
    min_scale = min((canvas_w - margin * 2) / crop.width / 1.18, (canvas_h - margin * 2) / crop.height / 1.02)
    if min_scale <= 0:
        raise ValueError("canvas and margin leave no room for character")
    baseline = canvas_h - margin
    output: list[Image.Image] = []
    metrics: list[dict] = []
    for index in range(frames):
        amount = bow_amount(index, frames)
        layer = build_bow_layer(crop, amount, min_scale)
        frame = Image.new("RGBA", canvas, (0, 0, 0, 0))
        paste_x = round((canvas_w - layer.width) / 2)
        paste_y = round((canvas_h - layer.height) / 2)
        frame.alpha_composite(layer, (paste_x, paste_y))
        bbox = frame.getbbox()
        if bbox is None:
            raise ValueError("generated empty bow frame")
        draw_joined_hand_hint(frame, bbox, amount)
        frame = align_center(frame, canvas)
        bbox = frame.getbbox()
        output.append(frame)
        metrics.append({
            "frame": index,
            "bow_amount": round(amount, 4),
            "bbox": list(bbox),
            "bottom": bbox[3],
            "height": bbox[3] - bbox[1],
            "min_margin": min(bbox[0], bbox[1], canvas_w - bbox[2], canvas_h - bbox[3]),
        })
    return output, {
        "scale": min_scale,
        "baseline": baseline,
        "margin": margin,
        "frames": metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--character-name", required=True)
    parser.add_argument("--action", default="gentle_bow_flower_sway")
    parser.add_argument("--frames", type=int, default=16)
    parser.add_argument("--canvas", type=parse_canvas, default=parse_canvas("512x512"))
    parser.add_argument("--duration-ms", type=int, default=90)
    parser.add_argument("--margin", type=int, default=56)
    parser.add_argument("--rows", type=int, default=4)
    parser.add_argument("--columns", type=int, default=4)
    args = parser.parse_args()
    if args.action != "gentle_bow_flower_sway":
        raise ValueError("local bow fallback supports --action gentle_bow_flower_sway")
    run_dir = Path(args.run_dir).expanduser().resolve()
    reference_path = Path(args.reference).expanduser().resolve()
    for rel in ["source", "sequence_frames"]:
        (run_dir / rel).mkdir(parents=True, exist_ok=True)
    source_copy = run_dir / "source" / reference_path.name
    shutil.copy2(reference_path, source_copy)
    frames, generation_report = generate_frames(Image.open(reference_path).convert("RGBA"), args.canvas, args.frames, args.margin)
    write_sequence(frames, run_dir / "sequence_frames")
    save_grid_sheet(frames, run_dir / "local_generated_sheet.png", args.rows, args.columns)
    save_contact_sheet(frames, run_dir / "contact_sheet.png", 256)
    save_contact_sheet(frames, run_dir / "contact_sheet_full_canvas.png", 192)
    save_transparent_sheet(frames, run_dir / "sheet-transparent.png")
    save_matte_gif(frames, run_dir / "animation.gif", args.duration_ms)
    save_transparent_gif(frames, run_dir / "animation-transparent.gif", args.duration_ms)
    save_checker_gif(frames, run_dir / "animation_checker.gif", args.duration_ms)
    save_webp(frames, run_dir / "animation.webp", args.duration_ms)
    write_json(run_dir / "local_bow_generation_report.json", generation_report)
    write_json(run_dir / "candidate_manifest.json", {
        "schema_version": "sofunny-candidate-sheet.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "character_name": args.character_name,
        "action": args.action,
        "route": "reference_locked_local_bow",
        "admission_eligible": False,
        "reference": str(source_copy),
        "frames": args.frames,
        "placement_mode": "fit-ground",
        "canvas": {"width": args.canvas[0], "height": args.canvas[1]},
        "generated_sheet": str(run_dir / "local_generated_sheet.png"),
        "limitations": [
            "Local deterministic fallback preserves stability and completeness.",
            "It does not replace a real pose-conditioned redraw for production-quality hand anatomy.",
        ],
    })
    print(str(run_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
