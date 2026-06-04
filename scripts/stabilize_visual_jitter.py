#!/usr/bin/env python3
"""Create a visually stabilized copy of a SoFunny candidate run."""

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
from sofunny_anim.visual_stability import audit_visual_stability, measure_frame, median


def clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def phase_height_offsets(frame_count: int, amplitude: int) -> list[int]:
    if frame_count == 6:
        return [0, -amplitude, 0, amplitude, 0, -max(1, amplitude // 2)]
    pattern = [0, -amplitude, 0, amplitude]
    return [pattern[i % len(pattern)] for i in range(frame_count)]


def stabilize_frames(
    frames: list[Image.Image],
    max_x_shift: int,
    amplitude: int,
) -> tuple[list[Image.Image], list[dict]]:
    measured = [measure_frame(frame, index) for index, frame in enumerate(frames)]
    canvas_w, canvas_h = frames[0].size
    target_height_base = median([float(item.bbox_height) for item in measured])
    target_mid_x = canvas_w / 2
    target_bottom = median([float(item.bbox[3]) for item in measured])
    offsets = phase_height_offsets(len(frames), amplitude)
    out: list[Image.Image] = []
    transforms: list[dict] = []

    for frame, item, height_offset in zip(frames, measured, offsets):
        left, top, right, bottom = item.bbox
        crop = frame.crop(item.bbox)
        target_height = max(1, round(target_height_base + height_offset))
        scale = target_height / max(1, crop.height)
        target_width = max(1, round(crop.width * scale))
        resized = crop.resize((target_width, target_height), Image.Resampling.LANCZOS)
        rel_mid_x = (item.mid_centroid_x - left) * scale
        desired_x = target_mid_x - rel_mid_x
        current_x = float(left)
        paste_x = round(current_x + clamp(desired_x - current_x, max_x_shift))
        paste_y = round(target_bottom - target_height)
        canvas = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        canvas.alpha_composite(resized, (paste_x, paste_y))
        out.append(canvas)
        transforms.append(
            {
                "frame": item.frame,
                "source_bbox": item.bbox,
                "target_height": target_height,
                "scale": round(scale, 4),
                "x_shift_px": paste_x - left,
                "paste": [paste_x, paste_y],
            }
        )
    return out, transforms


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-run-dir", required=True)
    parser.add_argument("--duration-ms", type=int, default=90)
    parser.add_argument("--max-x-shift", type=int, default=10)
    parser.add_argument("--height-amplitude", type=int, default=4)
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
    source_frames = read_sequence(keypose_dir if keypose_dir.exists() else output_run / "sequence_frames")
    before_visual = audit_visual_stability(source_frames)
    stabilized, transforms = stabilize_frames(source_frames, args.max_x_shift, args.height_amplitude)
    write_sequence(stabilized, output_run / "sequence_frames")
    save_contact_sheet(stabilized, output_run / "contact_sheet.png", 256)
    save_contact_sheet(stabilized, output_run / "contact_sheet_full_canvas.png", 192)
    save_transparent_sheet(stabilized, output_run / "sheet-transparent.png")
    save_transparent_gif(stabilized, output_run / "animation.gif", args.duration_ms)
    save_checker_gif(stabilized, output_run / "animation_checker.gif", args.duration_ms)
    save_webp(stabilized, output_run / "animation.webp", args.duration_ms)

    after_visual = audit_visual_stability(stabilized)
    write_json(output_run / "visual_stability_report.json", after_visual)
    write_json(output_run / "jitter_diagnostics.json", audit_frames(stabilized, args.duration_ms))
    write_json(
        output_run / "visual_stabilization_report.json",
        {
            "status": "pass" if after_visual["status"] == "pass" else "warn",
            "source_run": str(source_run),
            "output_run": str(output_run),
            "freeze_gate": freeze_manifest,
            "max_x_shift": args.max_x_shift,
            "height_amplitude": args.height_amplitude,
            "before": before_visual,
            "after": after_visual,
            "transforms": transforms,
            "notes": [
                "This is a conservative whole-frame stabilization pass.",
                "It can reduce visible shake, but it cannot repair identity drift or weak leg drawing.",
            ],
        },
    )
    print(str(output_run))
    return 0 if after_visual["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
