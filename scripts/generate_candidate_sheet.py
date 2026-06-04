#!/usr/bin/env python3
"""Generate a local SoFunny pipeline-smoke candidate sheet from one reference PNG.

This is the skill's deterministic fallback candidate generator. It preserves the
source character art and creates a candidate sheet that can be passed into
normalize_candidate_sheet.py. It is intentionally NOT admission-eligible for
actions that require new limb poses, such as small_jog_front. For production
motion, use a visual provider or SoFunny-adapted game-character-sprites workflow.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sofunny_anim.profiles import load_profile

from PIL import Image, ImageDraw


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


def make_checker(size: tuple[int, int], step: int = 24) -> Image.Image:
    image = Image.new("RGBA", size, (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    width, height = size
    for y in range(0, height, step):
        for x in range(0, width, step):
            if ((x // step) + (y // step)) % 2 == 0:
                draw.rectangle((x, y, min(width - 1, x + step - 1), min(height - 1, y + step - 1)), fill=(232, 232, 232, 255))
    return image


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def small_jog_params(frames: int) -> list[dict]:
    if frames < 4:
        raise ValueError("small_jog_front needs at least 4 frames")
    params: list[dict] = []
    for index in range(frames):
        phase = index / frames
        sin = math.sin(2 * math.pi * phase)
        cos = math.cos(2 * math.pi * phase)
        contact = 0.5 + 0.5 * cos
        airborne = 1.0 - contact
        params.append(
            {
                "frame": index,
                "x_shift": round(5 * sin),
                "y_shift": round(-10 * airborne),
                "scale_x": 1.0 + 0.030 * contact - 0.012 * airborne,
                "scale_y": 1.0 - 0.026 * contact + 0.018 * airborne,
                "tail_lag": round(5 * math.sin(2 * math.pi * (phase - 0.16))),
                "speed_alpha": int(95 * airborne),
                "shadow_scale": 1.0 - 0.18 * airborne,
            }
        )
    return params


def draw_motion_accents(canvas: Image.Image, params: dict, bbox: tuple[int, int, int, int], paste: tuple[int, int]) -> None:
    draw = ImageDraw.Draw(canvas, "RGBA")
    left, top, right, bottom = bbox
    px, py = paste
    char_left = px + left
    char_right = px + right
    char_bottom = py + bottom
    char_mid_y = py + (top + bottom) // 2

    if params["speed_alpha"] > 0:
        alpha = params["speed_alpha"]
        for offset in (0, 18, 36):
            y = char_mid_y + offset - 18
            draw.line(
                [(char_left - 34 - offset // 3, y), (char_left - 10 - offset // 5, y - 4)],
                fill=(80, 60, 42, max(20, alpha - offset)),
                width=2,
            )

    tail_lag = params["tail_lag"]
    if abs(tail_lag) > 0:
        draw.arc(
            (char_right - 58, char_bottom - 58 + tail_lag, char_right + 15, char_bottom + 5 + tail_lag),
            205,
            326,
            fill=(64, 43, 25, 58),
            width=4,
        )


def generate_small_jog(reference: Image.Image, canvas_size: tuple[int, int], frames: int, margin: int) -> list[Image.Image]:
    source = reference.convert("RGBA")
    bbox = source.getbbox()
    if bbox is None:
        raise ValueError("reference has no visible foreground")

    canvas_w, canvas_h = canvas_size
    visible_w = bbox[2] - bbox[0]
    visible_h = bbox[3] - bbox[1]
    base_scale = min((canvas_w - margin * 2) / visible_w, (canvas_h - margin * 2) / visible_h, 2.0)
    base_bottom = canvas_h - margin
    base_center_x = canvas_w / 2
    params = small_jog_params(frames)
    output: list[Image.Image] = []

    for frame_params in params:
        frame = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        sx = base_scale * frame_params["scale_x"]
        sy = base_scale * frame_params["scale_y"]
        scaled = source.resize((max(1, round(source.width * sx)), max(1, round(source.height * sy))), Image.Resampling.BICUBIC)
        scaled_bbox = scaled.getbbox()
        if scaled_bbox is None:
            raise ValueError("scaled frame has no visible foreground")

        # Keep contact stable while allowing a subtle run-cycle center sway.
        anchor_x = (scaled_bbox[0] + scaled_bbox[2]) / 2
        anchor_bottom = scaled_bbox[3]
        paste_x = round(base_center_x - anchor_x + frame_params["x_shift"])
        paste_y = round(base_bottom - anchor_bottom + frame_params["y_shift"])

        # Soft shadow is drawn before character; it makes the jog read without changing identity.
        draw = ImageDraw.Draw(frame, "RGBA")
        shadow_w = round((scaled_bbox[2] - scaled_bbox[0]) * 0.62 * frame_params["shadow_scale"])
        shadow_h = max(8, round(shadow_w * 0.16))
        shadow_cx = round(base_center_x + frame_params["x_shift"] * 0.4)
        shadow_y = base_bottom - 8
        draw.ellipse(
            (shadow_cx - shadow_w // 2, shadow_y - shadow_h // 2, shadow_cx + shadow_w // 2, shadow_y + shadow_h // 2),
            fill=(0, 0, 0, 38),
        )
        frame.alpha_composite(scaled, (paste_x, paste_y))
        draw_motion_accents(frame, frame_params, scaled_bbox, (paste_x, paste_y))
        output.append(frame)
    return output


def bake_checker_sheet(frames: list[Image.Image], output: Path) -> None:
    if not frames:
        raise ValueError("no frames to export")
    frame_w, frame_h = frames[0].size
    sheet = Image.new("RGBA", (frame_w * len(frames), frame_h), (255, 255, 255, 255))
    for index, frame in enumerate(frames):
        cell = make_checker(frame.size, 24)
        cell.alpha_composite(frame)
        sheet.alpha_composite(cell, (index * frame_w, 0))
    sheet.convert("RGB").save(output)


def export_contact_sheet(frames: list[Image.Image], output: Path, cell_size: int = 192) -> None:
    columns = min(6, len(frames))
    rows = math.ceil(len(frames) / columns)
    sheet = Image.new("RGBA", (columns * cell_size, rows * cell_size), (245, 245, 245, 255))
    for i, frame in enumerate(frames):
        cell = make_checker((cell_size, cell_size), 16)
        cell.alpha_composite(frame.resize((cell_size, cell_size), Image.Resampling.LANCZOS))
        draw = ImageDraw.Draw(cell)
        draw.rectangle((0, 0, cell_size - 1, cell_size - 1), outline=(180, 180, 180, 255), width=1)
        draw.text((6, 6), f"{i:02d}", fill=(20, 20, 20, 255))
        sheet.alpha_composite(cell, ((i % columns) * cell_size, (i // columns) * cell_size))
    sheet.save(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--reference", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--action", default="small_jog_front")
    parser.add_argument("--character-name", required=True)
    parser.add_argument("--frames", type=int, default=6)
    parser.add_argument("--canvas", type=parse_canvas, default=parse_canvas("384x384"))
    parser.add_argument("--margin", type=int, default=42)
    args = parser.parse_args()
    profile = load_profile(args.profile)

    if args.action != "small_jog_front":
        raise ValueError("deterministic fallback currently supports --action small_jog_front")

    reference_path = Path(args.reference).expanduser().resolve()
    run_dir = Path(args.run_dir).expanduser().resolve()
    source_dir = run_dir / "source"
    candidate_dir = run_dir / "candidate_sheets"
    preview_dir = run_dir / "candidate_previews"
    for directory in [source_dir, candidate_dir, preview_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    source_copy = source_dir / reference_path.name
    shutil.copy2(reference_path, source_copy)
    reference = Image.open(reference_path).convert("RGBA")
    frames = generate_small_jog(reference, args.canvas, args.frames, args.margin)

    candidate_sheet = candidate_dir / f"{args.action}-candidate-sheet.png"
    bake_checker_sheet(frames, candidate_sheet)
    export_contact_sheet(frames, preview_dir / f"{args.action}-candidate-contact-sheet.png", 192)

    manifest = {
        "schema_version": "sofunny-candidate-sheet.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "character_name": args.character_name,
        "action": args.action,
        "route": "local_component_rig_pipeline_smoke",
        "admission_eligible": False,
        "reference": str(source_copy),
        "candidate_sheet": str(candidate_sheet),
        "frames": args.frames,
        "canvas": {"width": args.canvas[0], "height": args.canvas[1]},
        "limitations": [
            "Preserves original character art and simulates jog motion; does not redraw legs into true run poses.",
            "Not valid for admission on small_jog_front because it lacks alternating leg contact/passing/recovery poses.",
            "Use a visual provider or SoFunny-adapted game-character-sprites workflow for stronger production limb poses.",
        ],
    }
    write_json(run_dir / "candidate_manifest.json", manifest)
    print(json.dumps({"candidate_sheet": str(candidate_sheet), "manifest": str(run_dir / "candidate_manifest.json")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
