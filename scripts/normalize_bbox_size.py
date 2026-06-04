#!/usr/bin/env python3
"""Normalize frame bbox size while preserving accepted pose order."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from sofunny_anim.profiles import load_profile

from PIL import Image

from sofunny_anim.frame_layout import read_sequence, write_sequence
from sofunny_anim.freeze_gate import require_freeze_gate
from sofunny_anim.manifests import write_json
from sofunny_anim.motion_metrics import audit_frames
from sofunny_anim.previews import save_checker_gif, save_contact_sheet, save_transparent_gif, save_transparent_sheet, save_webp
from sofunny_anim.visual_stability import audit_visual_stability, median


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-run-dir", required=True)
    parser.add_argument("--duration-ms", type=int, default=100)
    parser.add_argument("--target-width")
    parser.add_argument("--target-height")
    parser.add_argument("--allow-non-uniform", action="store_true")
    parser.add_argument("--max-aspect-distortion", type=float, default=0.08)
    parser.add_argument("--allow-unfrozen", action="store_true")
    args = parser.parse_args()
    profile = load_profile(args.profile)

    source_run = Path(args.run_dir).expanduser().resolve()
    freeze_manifest = require_freeze_gate(source_run, args.allow_unfrozen)
    output_run = Path(args.output_run_dir).expanduser().resolve()
    if output_run.exists() and output_run != source_run:
        shutil.rmtree(output_run)
    if output_run != source_run:
        shutil.copytree(source_run, output_run)

    keypose_dir = source_run / "accepted_keyposes"
    frames = read_sequence(keypose_dir if keypose_dir.exists() else output_run / "sequence_frames")
    bboxes = [frame.convert("RGBA").getbbox() for frame in frames]
    if any(bbox is None for bbox in bboxes):
        raise ValueError("all frames must have foreground")
    widths = [bbox[2] - bbox[0] for bbox in bboxes if bbox]
    heights = [bbox[3] - bbox[1] for bbox in bboxes if bbox]
    target_width = int(args.target_width) if args.target_width else round(median([float(v) for v in widths]))
    target_height = int(args.target_height) if args.target_height else round(median([float(v) for v in heights]))
    canvas_w, canvas_h = frames[0].size
    target_bottom = round(median([float(bbox[3]) for bbox in bboxes if bbox]))
    target_x = round((canvas_w - target_width) / 2)
    normalized: list[Image.Image] = []
    transforms: list[dict] = []
    for index, (frame, bbox) in enumerate(zip(frames, bboxes)):
        assert bbox is not None
        crop = frame.crop(bbox)
        x_scale = target_width / max(1, crop.width)
        y_scale = target_height / max(1, crop.height)
        aspect_distortion = abs((x_scale / max(0.0001, y_scale)) - 1.0)
        if aspect_distortion > args.max_aspect_distortion and not args.allow_non_uniform:
            raise ValueError(
                "refusing non-uniform bbox resize for frame "
                f"{index:02d}: source={crop.width}x{crop.height}, "
                f"target={target_width}x{target_height}, "
                f"x_scale={x_scale:.4f}, y_scale={y_scale:.4f}, "
                f"aspect_distortion={aspect_distortion:.4f}. "
                "Use --allow-non-uniform only for diagnostic metric experiments, "
                "not production art."
            )
        resized = crop.resize((target_width, target_height), Image.Resampling.LANCZOS)
        paste_y = target_bottom - target_height
        canvas = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        canvas.alpha_composite(resized, (target_x, paste_y))
        normalized.append(canvas)
        transforms.append({
            "frame": index,
            "source_bbox": bbox,
            "source_size": [crop.width, crop.height],
            "target_size": [target_width, target_height],
            "x_scale": round(x_scale, 4),
            "y_scale": round(y_scale, 4),
            "aspect_distortion": round(aspect_distortion, 4),
            "paste": [target_x, paste_y],
        })

    write_sequence(normalized, output_run / "sequence_frames")
    save_contact_sheet(normalized, output_run / "contact_sheet.png", 192)
    save_contact_sheet(normalized[: min(12, len(normalized))], output_run / "contact_sheet_first_12.png", 192)
    save_transparent_sheet(normalized, output_run / "sheet-transparent.png")
    save_transparent_gif(normalized, output_run / "animation.gif", args.duration_ms)
    save_checker_gif(normalized, output_run / "animation_checker.gif", args.duration_ms)
    save_webp(normalized, output_run / "animation.webp", args.duration_ms)
    write_json(output_run / "visual_stability_report.json", audit_visual_stability(normalized))
    write_json(output_run / "jitter_diagnostics.json", audit_frames(normalized, args.duration_ms))
    write_json(output_run / "bbox_size_normalization_report.json", {
        "status": "pass",
        "source_run": str(source_run),
        "output_run": str(output_run),
        "freeze_gate": freeze_manifest,
        "target_width": target_width,
        "target_height": target_height,
        "allow_non_uniform": args.allow_non_uniform,
        "max_aspect_distortion": args.max_aspect_distortion,
        "transforms": transforms,
    })
    print(str(output_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
