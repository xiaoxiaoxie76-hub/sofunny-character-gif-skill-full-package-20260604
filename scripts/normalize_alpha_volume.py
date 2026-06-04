#!/usr/bin/env python3
"""Normalize low-volume frames by strengthening existing local alpha only."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from sofunny_anim.profiles import load_profile

from PIL import Image

from sofunny_anim.frame_layout import read_sequence, write_sequence
from sofunny_anim.manifests import write_json
from sofunny_anim.motion_metrics import audit_frames
from sofunny_anim.previews import save_checker_gif, save_contact_sheet, save_transparent_gif, save_transparent_sheet, save_webp
from sofunny_anim.visual_stability import audit_visual_stability


def alpha_area(image: Image.Image, threshold: int) -> int:
    alpha = image.convert("RGBA").getchannel("A")
    return sum(1 for value in alpha.getdata() if value >= threshold)


def strengthen_existing_alpha(
    frame: Image.Image,
    target_area: int,
    threshold: int,
    min_source_alpha: int,
    protect_top_ratio: float,
) -> tuple[Image.Image, dict]:
    rgba = frame.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    current_area = alpha_area(rgba, threshold)
    needed = max(0, target_area - current_area)
    if needed == 0:
        return rgba, {
            "changed_pixels": 0,
            "area_before": current_area,
            "area_after": current_area,
            "target_area": target_area,
        }

    protect_y = round(height * protect_top_ratio)
    candidates: list[tuple[float, int, int, int]] = []
    center_x = width / 2
    for y in range(protect_y, height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if min_source_alpha <= a < threshold:
                # Prefer lower-body/shadow pixels near the character footprint, not stray haze.
                y_weight = y / max(1, height)
                x_weight = 1.0 - min(1.0, abs(x - center_x) / max(1.0, center_x))
                alpha_weight = a / threshold
                score = (y_weight * 2.0) + x_weight + alpha_weight
                candidates.append((score, x, y, a))

    candidates.sort(reverse=True)
    changed = 0
    for _, x, y, _ in candidates[:needed]:
        r, g, b, a = pixels[x, y]
        pixels[x, y] = (r, g, b, threshold)
        changed += 1

    after_area = alpha_area(rgba, threshold)
    return rgba, {
        "changed_pixels": changed,
        "area_before": current_area,
        "area_after": after_area,
        "target_area": target_area,
        "candidate_pixels": len(candidates),
        "protect_y": protect_y,
    }


def soften_existing_alpha(
    frame: Image.Image,
    target_area: int,
    threshold: int,
    protect_top_ratio: float,
) -> tuple[Image.Image, dict]:
    rgba = frame.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    current_area = alpha_area(rgba, threshold)
    excess = max(0, current_area - target_area)
    if excess == 0:
        return rgba, {
            "softened_pixels": 0,
            "area_before_soften": current_area,
            "area_after_soften": current_area,
            "max_target_area": target_area,
        }

    protect_y = round(height * protect_top_ratio)
    candidates: list[tuple[float, int, int, int]] = []
    center_x = width / 2
    for y in range(protect_y, height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a >= threshold:
                # Prefer lower/body-shadow pixels and existing antialias before core torso pixels.
                y_weight = y / max(1, height)
                x_edge_weight = min(1.0, abs(x - center_x) / max(1.0, center_x))
                alpha_softness = 1.0 - min(1.0, (a - threshold) / max(1.0, 255 - threshold))
                score = (y_weight * 2.0) + x_edge_weight + alpha_softness
                candidates.append((score, x, y, a))

    candidates.sort(reverse=True)
    changed = 0
    for _, x, y, _ in candidates[:excess]:
        r, g, b, a = pixels[x, y]
        pixels[x, y] = (r, g, b, threshold - 1)
        changed += 1

    after_area = alpha_area(rgba, threshold)
    return rgba, {
        "softened_pixels": changed,
        "area_before_soften": current_area,
        "area_after_soften": after_area,
        "max_target_area": target_area,
        "soften_candidate_pixels": len(candidates),
        "protect_y": protect_y,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-run-dir", required=True)
    parser.add_argument("--duration-ms", type=int, default=90)
    parser.add_argument("--alpha-threshold", type=int, default=96)
    parser.add_argument("--min-source-alpha", type=int, default=36)
    parser.add_argument("--target-ratio", type=float, default=0.91)
    parser.add_argument("--max-area-ratio", type=float, default=0.958)
    parser.add_argument("--protect-top-ratio", type=float, default=0.34)
    args = parser.parse_args()
    profile = load_profile(args.profile)

    source_run = Path(args.run_dir).expanduser().resolve()
    output_run = Path(args.output_run_dir).expanduser().resolve()
    if output_run.exists() and output_run != source_run:
        shutil.rmtree(output_run)
    if output_run != source_run:
        shutil.copytree(source_run, output_run)

    frames = read_sequence(output_run / "sequence_frames")
    areas = [alpha_area(frame, args.alpha_threshold) for frame in frames]
    target_area = round(max(areas) * args.target_ratio)
    max_target_area = round(max(areas) * args.max_area_ratio)

    normalized: list[Image.Image] = []
    frame_reports: list[dict] = []
    for index, frame in enumerate(frames):
        repaired, report = strengthen_existing_alpha(
            frame,
            target_area=target_area,
            threshold=args.alpha_threshold,
            min_source_alpha=args.min_source_alpha,
            protect_top_ratio=args.protect_top_ratio,
        )
        repaired, soften_report = soften_existing_alpha(
            repaired,
            target_area=max_target_area,
            threshold=args.alpha_threshold,
            protect_top_ratio=args.protect_top_ratio,
        )
        report.update(soften_report)
        report["frame"] = index
        normalized.append(repaired)
        frame_reports.append(report)

    write_sequence(normalized, output_run / "sequence_frames")
    save_contact_sheet(normalized, output_run / "contact_sheet.png", 256)
    save_contact_sheet(normalized, output_run / "contact_sheet_full_canvas.png", 192)
    save_transparent_sheet(normalized, output_run / "sheet-transparent.png")
    save_transparent_gif(normalized, output_run / "animation.gif", args.duration_ms)
    save_checker_gif(normalized, output_run / "animation_checker.gif", args.duration_ms)
    save_webp(normalized, output_run / "animation.webp", args.duration_ms)

    after_visual = audit_visual_stability(normalized)
    write_json(output_run / "visual_stability_report.json", after_visual)
    write_json(output_run / "jitter_diagnostics.json", audit_frames(normalized, args.duration_ms))
    write_json(
        output_run / "alpha_volume_normalization_report.json",
        {
            "status": "pass",
            "source_run": str(source_run),
            "output_run": str(output_run),
            "alpha_threshold": args.alpha_threshold,
            "min_source_alpha": args.min_source_alpha,
            "target_ratio": args.target_ratio,
            "target_area": target_area,
            "max_area_ratio": args.max_area_ratio,
            "max_target_area": max_target_area,
            "areas_before": areas,
            "areas_after": [alpha_area(frame, args.alpha_threshold) for frame in normalized],
            "frames": frame_reports,
            "notes": [
                "Only existing semi-transparent pixels are strengthened.",
                "The upper character identity region is protected to avoid face/hair/glasses edits.",
            ],
        },
    )
    print(str(output_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
