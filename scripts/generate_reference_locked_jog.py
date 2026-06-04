#!/usr/bin/env python3
"""Generate a reference-locked local composite small-jog candidate."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sofunny_anim.profiles import load_profile

from PIL import Image, ImageDraw

from sofunny_anim.frame_layout import write_sequence
from sofunny_anim.manifests import write_json
from sofunny_anim.motion_metrics import audit_frames
from sofunny_anim.previews import save_checker_gif, save_contact_sheet, save_transparent_gif, save_transparent_sheet, save_webp
from sofunny_anim.visual_stability import audit_visual_stability


PHASES = [
    ("left_contact_down", -1, "left", "right"),
    ("left_push_off", 0, "left", "right"),
    ("flight_passing_left_to_right", 4, None, "right"),
    ("right_contact_down", -1, "right", "left"),
    ("right_push_off", 0, "right", "left"),
    ("flight_recover_to_left_contact", 3, None, "left"),
]


def parse_canvas(value: str) -> tuple[int, int]:
    width, height = (int(part) for part in value.lower().split("x"))
    return width, height


def prepare_static_layer(reference: Image.Image, scale: float, canvas: tuple[int, int], margin: int) -> tuple[Image.Image, dict]:
    source = reference.convert("RGBA")
    bbox = source.getbbox()
    if bbox is None:
        raise ValueError("reference has no visible foreground")
    crop = source.crop(bbox)
    scaled = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.Resampling.LANCZOS)
    canvas_w, canvas_h = canvas
    paste_x = round((canvas_w - scaled.width) / 2)
    paste_y = canvas_h - margin - scaled.height
    layer = Image.new("RGBA", canvas, (0, 0, 0, 0))
    layer.alpha_composite(scaled, (paste_x, paste_y))

    # Remove center lower-leg pixels from the original so local legs can carry the jog phase.
    alpha = layer.getchannel("A")
    pix = alpha.load()
    visible = layer.getbbox()
    if visible is None:
        raise ValueError("scaled reference has no visible foreground")
    left, top, right, bottom = visible
    cut_y = top + round((bottom - top) * 0.69)
    center = (left + right) // 2
    for y in range(cut_y, bottom + 1):
        for x in range(center - 46, center + 28):
            if 0 <= x < alpha.width and 0 <= y < alpha.height:
                pix[x, y] = 0
    layer.putalpha(alpha)
    return layer, {
        "visible_bbox": visible,
        "paste": [paste_x, paste_y],
        "scale": scale,
        "center_x": center,
        "cut_y": cut_y,
        "bottom": bottom,
    }


def draw_leg(draw: ImageDraw.ImageDraw, hip: tuple[int, int], knee: tuple[int, int], foot: tuple[int, int], phase_lift: int) -> None:
    dark = (35, 39, 45, 255)
    outline = (10, 12, 14, 255)
    shoe = (22, 24, 27, 255)
    draw.line((*hip, *knee), fill=outline, width=16)
    draw.line((*knee, *foot), fill=outline, width=15)
    draw.line((*hip, *knee), fill=dark, width=10)
    draw.line((*knee, *foot), fill=dark, width=9)
    draw.ellipse((foot[0] - 18, foot[1] - 7 + phase_lift, foot[0] + 18, foot[1] + 8 + phase_lift), fill=outline)
    draw.ellipse((foot[0] - 15, foot[1] - 5 + phase_lift, foot[0] + 15, foot[1] + 5 + phase_lift), fill=shoe)


def draw_arm_overlay(draw: ImageDraw.ImageDraw, center_x: int, body_y: int, forward: str) -> None:
    suit = (35, 39, 45, 235)
    skin = (226, 172, 95, 255)
    outline = (15, 16, 18, 255)
    if forward == "right":
        left_hand = (center_x - 46, body_y + 18)
        right_hand = (center_x + 42, body_y + 4)
    else:
        left_hand = (center_x - 42, body_y + 4)
        right_hand = (center_x + 46, body_y + 18)
    draw.line((center_x - 25, body_y, *left_hand), fill=outline, width=12)
    draw.line((center_x + 22, body_y, *right_hand), fill=outline, width=12)
    draw.line((center_x - 25, body_y, *left_hand), fill=suit, width=8)
    draw.line((center_x + 22, body_y, *right_hand), fill=suit, width=8)
    for x, y in (left_hand, right_hand):
        draw.ellipse((x - 11, y - 11, x + 11, y + 11), fill=outline)
        draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=skin)


def generate_frames(reference: Image.Image, canvas: tuple[int, int], frames: int, margin: int) -> list[Image.Image]:
    source_bbox = reference.getbbox()
    if source_bbox is None:
        raise ValueError("reference has no visible foreground")
    source_h = source_bbox[3] - source_bbox[1]
    scale = min((canvas[1] - margin * 2) / source_h, 2.45)
    static_layer, metrics = prepare_static_layer(reference, scale, canvas, margin)
    center_x = metrics["center_x"]
    ground = metrics["bottom"]
    hip_y = metrics["cut_y"] - 4
    out: list[Image.Image] = []
    phases = PHASES if frames == 6 else [PHASES[i % len(PHASES)] for i in range(frames)]
    for index, (phase, body_offset, support, swing) in enumerate(phases):
        frame = Image.new("RGBA", canvas, (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame, "RGBA")
        airborne = 1 if support is None else 0
        shadow_w = 112 - airborne * 22
        shadow_alpha = 42 - airborne * 14
        draw.ellipse((center_x - shadow_w // 2, ground - 11, center_x + shadow_w // 2, ground + 7), fill=(0, 0, 0, shadow_alpha))

        hip_left = (center_x - 19, hip_y + body_offset)
        hip_right = (center_x + 13, hip_y + body_offset)
        if phase.startswith("left_contact"):
            left_foot = (center_x - 25, ground)
            right_foot = (center_x + 28, ground - 28)
            left_knee = (center_x - 22, hip_y + 44 + body_offset)
            right_knee = (center_x + 24, hip_y + 36 + body_offset)
        elif phase.startswith("left_push"):
            left_foot = (center_x - 18, ground)
            right_foot = (center_x + 30, ground - 18)
            left_knee = (center_x - 15, hip_y + 46 + body_offset)
            right_knee = (center_x + 20, hip_y + 40 + body_offset)
        elif phase.startswith("flight_passing"):
            left_foot = (center_x - 24, ground - 18)
            right_foot = (center_x + 28, ground - 34)
            left_knee = (center_x - 20, hip_y + 42 + body_offset)
            right_knee = (center_x + 15, hip_y + 34 + body_offset)
        elif phase.startswith("right_contact"):
            left_foot = (center_x - 28, ground - 28)
            right_foot = (center_x + 25, ground)
            left_knee = (center_x - 23, hip_y + 36 + body_offset)
            right_knee = (center_x + 21, hip_y + 44 + body_offset)
        elif phase.startswith("right_push"):
            left_foot = (center_x - 30, ground - 18)
            right_foot = (center_x + 18, ground)
            left_knee = (center_x - 20, hip_y + 40 + body_offset)
            right_knee = (center_x + 15, hip_y + 46 + body_offset)
        else:
            left_foot = (center_x - 29, ground - 30)
            right_foot = (center_x + 24, ground - 16)
            left_knee = (center_x - 21, hip_y + 35 + body_offset)
            right_knee = (center_x + 20, hip_y + 42 + body_offset)
        draw_leg(draw, hip_left, left_knee, left_foot, 0)
        draw_leg(draw, hip_right, right_knee, right_foot, 0)
        # Keep original arms from the canonical layer; local arm redrawing is too crude for identity-lock proof.
        frame.alpha_composite(static_layer, (0, body_offset))
        out.append(frame)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--reference", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--character-name", required=True)
    parser.add_argument("--action", default="small_jog_front")
    parser.add_argument("--frames", type=int, default=6)
    parser.add_argument("--canvas", type=parse_canvas, default=parse_canvas("384x384"))
    parser.add_argument("--duration-ms", type=int, default=90)
    parser.add_argument("--margin", type=int, default=28)
    args = parser.parse_args()
    profile = load_profile(args.profile)

    if args.action != "small_jog_front":
        raise ValueError("currently supports --action small_jog_front")
    run_dir = Path(args.run_dir).expanduser().resolve()
    reference_path = Path(args.reference).expanduser().resolve()
    for rel in ["source", "sequence_frames"]:
        (run_dir / rel).mkdir(parents=True, exist_ok=True)
    source_copy = run_dir / "source" / reference_path.name
    shutil.copy2(reference_path, source_copy)
    frames = generate_frames(Image.open(reference_path).convert("RGBA"), args.canvas, args.frames, args.margin)
    write_sequence(frames, run_dir / "sequence_frames")
    save_contact_sheet(frames, run_dir / "contact_sheet.png", 256)
    save_contact_sheet(frames, run_dir / "contact_sheet_full_canvas.png", 192)
    save_transparent_sheet(frames, run_dir / "sheet-transparent.png")
    save_transparent_gif(frames, run_dir / "animation.gif", args.duration_ms)
    save_checker_gif(frames, run_dir / "animation_checker.gif", args.duration_ms)
    save_webp(frames, run_dir / "animation.webp", args.duration_ms)
    write_json(run_dir / "candidate_manifest.json", {
        "schema_version": "sofunny-candidate-sheet.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "character_name": args.character_name,
        "action": args.action,
        "route": "reference_locked_local_composite",
        "admission_eligible": False,
        "reference": str(source_copy),
        "frames": args.frames,
        "canvas": {"width": args.canvas[0], "height": args.canvas[1]},
        "limitations": [
            "Uses the canonical character as fixed identity layer.",
            "Local composite verifies stability and phase design, but drawn limbs need art pass before production.",
        ],
    })
    write_json(run_dir / "jitter_diagnostics.json", audit_frames(frames, args.duration_ms))
    write_json(run_dir / "visual_stability_report.json", audit_visual_stability(frames))
    print(str(run_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
