#!/usr/bin/env python3
"""Retarget official SoFunny walk phases onto one canonical character image."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sofunny_anim.profiles import load_profile

from PIL import Image, ImageDraw, ImageFilter

from sofunny_anim.frame_layout import write_sequence
from sofunny_anim.image_io import parse_canvas
from sofunny_anim.manifests import write_json
from sofunny_anim.motion_metrics import audit_frames
from sofunny_anim.previews import save_checker_gif, save_contact_sheet, save_transparent_gif, save_transparent_sheet, save_webp
from sofunny_anim.visual_stability import audit_visual_stability


PHASES = [
    "left_contact_down",
    "left_push_off",
    "flight_passing_left_to_right",
    "right_contact_down",
    "right_push_off",
    "flight_recover_to_left_contact",
]


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    bbox = image.convert("RGBA").getbbox()
    if bbox is None:
        raise ValueError("image has no visible foreground")
    return bbox


def resize_to_height(image: Image.Image, target_height: int) -> Image.Image:
    if image.height <= 0:
        raise ValueError("image height must be positive")
    scale = target_height / image.height
    return image.resize((round(image.width * scale), target_height), Image.Resampling.LANCZOS)


def prepare_canonical_layer(reference: Image.Image, canvas: tuple[int, int], margin: int) -> tuple[Image.Image, dict]:
    source = reference.convert("RGBA")
    bbox = alpha_bbox(source)
    crop = source.crop(bbox)
    target_h = canvas[1] - margin * 2
    scaled = resize_to_height(crop, target_h)
    paste_x = round((canvas[0] - scaled.width) / 2)
    paste_y = canvas[1] - margin - scaled.height
    layer = Image.new("RGBA", canvas, (0, 0, 0, 0))
    layer.alpha_composite(scaled, (paste_x, paste_y))
    visible = alpha_bbox(layer)
    return layer, {
        "source_bbox": bbox,
        "visible_bbox": visible,
        "scale": scaled.height / crop.height,
        "paste": [paste_x, paste_y],
        "center_x": round((visible[0] + visible[2]) / 2),
        "ground_y": visible[3],
    }


def erase_original_lower_limbs(layer: Image.Image, metrics: dict) -> Image.Image:
    out = layer.copy()
    alpha = out.getchannel("A")
    pix = alpha.load()
    left, top, right, bottom = metrics["visible_bbox"]
    width = right - left
    height = bottom - top
    cut_top = top + round(height * 0.90)
    # Keep the suit body intact. Only clear a narrow original-foot zone so no torso holes appear.
    erase_left = left + round(width * 0.41)
    erase_right = left + round(width * 0.54)
    for y in range(cut_top, bottom + 1):
        for x in range(erase_left, erase_right):
            if 0 <= x < alpha.width and 0 <= y < alpha.height:
                pix[x, y] = 0
    out.putalpha(alpha)
    return out


def donor_lower_mask(donor: Image.Image) -> Image.Image:
    rgba = donor.convert("RGBA")
    bbox = alpha_bbox(rgba)
    crop = rgba.crop(bbox)
    alpha = crop.getchannel("A")
    out_alpha = Image.new("L", crop.size, 0)
    src_a = alpha.load()
    src = crop.load()
    dst = out_alpha.load()
    w, h = crop.size
    # Central lower-body region: keep legs and feet, reject tail and shadow blobs.
    y_min = round(h * 0.58)
    x_min = round(w * 0.25)
    x_max = round(w * 0.70)
    for y in range(y_min, h):
        for x in range(x_min, x_max):
            a = src_a[x, y]
            if a < 80:
                continue
            r, g, b, _ = src[x, y]
            if y > h - 34 and r < 45 and g < 45 and b < 45:
                continue
            dst[x, y] = a
    return out_alpha.filter(ImageFilter.GaussianBlur(0.35))


def recolor_limb_mask(mask: Image.Image) -> Image.Image:
    # Solid SoFunny suit/shoe colors. A little vertical split keeps shoes readable.
    out = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    pix = out.load()
    src = mask.load()
    h = mask.height
    for y in range(mask.height):
        for x in range(mask.width):
            a = src[x, y]
            if a == 0:
                continue
            if y > h * 0.82:
                color = (18, 20, 24, a)
            else:
                color = (35, 39, 45, a)
            pix[x, y] = color
    return out


def fit_limb_layer(mask: Image.Image, canonical_metrics: dict, canvas: tuple[int, int]) -> Image.Image:
    left, top, right, bottom = canonical_metrics["visible_bbox"]
    target_h = round((bottom - top) * 0.31)
    resized_mask = resize_to_height(mask.convert("L"), target_h)
    limb = recolor_limb_mask(resized_mask)
    layer = Image.new("RGBA", canvas, (0, 0, 0, 0))
    center_x = canonical_metrics["center_x"]
    paste_x = round(center_x - resized_mask.width * 0.50)
    paste_y = bottom - resized_mask.height + 1
    layer.alpha_composite(limb, (paste_x, paste_y))
    return layer


def draw_shadow(draw: ImageDraw.ImageDraw, center_x: int, ground_y: int, phase_index: int) -> None:
    airborne = phase_index in {2, 5}
    width = 112 if not airborne else 92
    alpha = 42 if not airborne else 26
    draw.ellipse((center_x - width // 2, ground_y - 9, center_x + width // 2, ground_y + 7), fill=(0, 0, 0, alpha))


def draw_arm_overlay(draw: ImageDraw.ImageDraw, metrics: dict, phase_index: int) -> None:
    left, top, right, bottom = metrics["visible_bbox"]
    width = right - left
    height = bottom - top
    cx = metrics["center_x"]
    shoulder_y = top + round(height * 0.58)
    # Alternate arm opposition with support-foot phases.
    if phase_index in {0, 1, 5}:
        left_hand = (cx - round(width * 0.23), shoulder_y + 22)
        right_hand = (cx + round(width * 0.21), shoulder_y + 4)
    else:
        left_hand = (cx - round(width * 0.21), shoulder_y + 4)
        right_hand = (cx + round(width * 0.23), shoulder_y + 22)
    suit = (35, 39, 45, 240)
    outline = (12, 14, 16, 255)
    skin = (226, 174, 101, 255)
    anchors = [(cx - round(width * 0.15), shoulder_y - 2, left_hand), (cx + round(width * 0.13), shoulder_y - 2, right_hand)]
    for sx, sy, hand in anchors:
        draw.line((sx, sy, hand[0], hand[1]), fill=outline, width=13)
        draw.line((sx, sy, hand[0], hand[1]), fill=suit, width=8)
        draw.ellipse((hand[0] - 11, hand[1] - 11, hand[0] + 11, hand[1] + 11), fill=outline)
        draw.ellipse((hand[0] - 8, hand[1] - 8, hand[0] + 8, hand[1] + 8), fill=skin)


def load_donor_frames(atlas: Path, donor_rank: int) -> list[Image.Image]:
    payload = json.loads(atlas.read_text(encoding="utf-8"))
    donors = payload.get("donors", [])
    donor = next((item for item in donors if item.get("rank") == donor_rank), None)
    if donor is None:
        raise ValueError(f"no donor rank {donor_rank} in {atlas}")
    frames = []
    for item in donor.get("frames", [])[: len(PHASES)]:
        frames.append(Image.open(item["frame_path"]).convert("RGBA"))
    if len(frames) != len(PHASES):
        raise ValueError("donor does not have six phase frames")
    return frames


def generate(reference: Image.Image, donor_frames: list[Image.Image], canvas: tuple[int, int], margin: int) -> tuple[list[Image.Image], dict]:
    canonical, metrics = prepare_canonical_layer(reference, canvas, margin)
    canonical_cut = erase_original_lower_limbs(canonical, metrics)
    frames = []
    for index, donor in enumerate(donor_frames):
        frame = Image.new("RGBA", canvas, (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame, "RGBA")
        draw_shadow(draw, metrics["center_x"], metrics["ground_y"], index)
        frame.alpha_composite(fit_limb_layer(donor_lower_mask(donor), metrics, canvas))
        frame.alpha_composite(canonical_cut)
        draw = ImageDraw.Draw(frame, "RGBA")
        draw_arm_overlay(draw, metrics, index)
        frames.append(frame)
    return frames, metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--reference", required=True)
    parser.add_argument("--motion-atlas", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--character-name", required=True)
    parser.add_argument("--action", default="small_jog_front")
    parser.add_argument("--donor-rank", type=int, default=1)
    parser.add_argument("--canvas", type=parse_canvas, default=parse_canvas("384x384"))
    parser.add_argument("--margin", type=int, default=28)
    parser.add_argument("--duration-ms", type=int, default=90)
    args = parser.parse_args()
    profile = load_profile(args.profile)

    if args.action != "small_jog_front":
        raise ValueError("currently supports --action small_jog_front")

    run_dir = Path(args.run_dir).expanduser().resolve()
    reference_path = Path(args.reference).expanduser().resolve()
    atlas_path = Path(args.motion_atlas).expanduser().resolve()
    for rel in ["source", "sequence_frames"]:
        (run_dir / rel).mkdir(parents=True, exist_ok=True)
    shutil.copy2(reference_path, run_dir / "source" / reference_path.name)
    donor_frames = load_donor_frames(atlas_path, args.donor_rank)
    frames, metrics = generate(Image.open(reference_path).convert("RGBA"), donor_frames, args.canvas, args.margin)

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
        "route": "official_motion_atlas_retarget",
        "admission_eligible": False,
        "reference": str(reference_path),
        "motion_atlas": str(atlas_path),
        "donor_rank": args.donor_rank,
        "frames": len(frames),
        "canvas": {"width": args.canvas[0], "height": args.canvas[1]},
        "identity_strategy": "Canonical character is reused as the stable upper identity layer; official SoFunny donor frames provide lower-body motion masks only.",
        "limits": [
            "This is a local retarget candidate, not a provider redraw.",
            "Arms and lower-body recolor still require direct visual review before production approval.",
        ],
        "canonical_metrics": metrics,
    })
    write_json(run_dir / "jitter_diagnostics.json", audit_frames(frames, args.duration_ms))
    write_json(run_dir / "visual_stability_report.json", audit_visual_stability(frames))
    write_json(run_dir / "action_phase_review.json", {
        "schema_version": "sofunny-action-phase-review.v1",
        "status": "manual_required",
        "action": args.action,
        "phases": PHASES,
        "note": "Official donor lower-body masks were retargeted locally. Direct visual review must confirm each phase before admission.",
    })
    print(json.dumps({"run_dir": str(run_dir), "frames": len(frames)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
