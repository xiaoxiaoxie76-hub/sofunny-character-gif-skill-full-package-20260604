#!/usr/bin/env python3
"""Score SoFunny identity/style consistency for failure routing only."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity

from sofunny_anim.frame_layout import read_sequence
from sofunny_anim.manifests import write_json
from sofunny_anim.profiles import get_path, load_profile


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    return image.convert("RGBA").getbbox()


def normalized_crop(image: Image.Image, size: int = 192) -> Image.Image:
    rgba = image.convert("RGBA")
    bbox = alpha_bbox(rgba)
    canvas = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    if bbox is None:
        return canvas
    crop = rgba.crop(bbox)
    crop.thumbnail((size - 24, size - 24), Image.Resampling.LANCZOS)
    target = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    target.alpha_composite(crop, ((size - crop.width) // 2, size - 12 - crop.height))
    return target


def gray_array(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("L"), dtype=np.float32) / 255.0


def ssim(a: Image.Image, b: Image.Image) -> float:
    arr_a = gray_array(a)
    arr_b = gray_array(b)
    return float(structural_similarity(arr_a, arr_b, data_range=1.0))


def foreground_colors(image: Image.Image) -> np.ndarray:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    mask = rgba[:, :, 3] > 8
    if not np.any(mask):
        return np.zeros((0, 3), dtype=np.uint8)
    return rgba[:, :, :3][mask]


def color_histogram(image: Image.Image, bins: int = 8) -> np.ndarray:
    colors = foreground_colors(image)
    if colors.size == 0:
        return np.zeros((bins * 3,), dtype=np.float32)
    hist_parts = []
    for channel in range(3):
        hist, _ = np.histogram(colors[:, channel], bins=bins, range=(0, 256), density=False)
        hist = hist.astype(np.float32)
        total = float(hist.sum()) or 1.0
        hist_parts.append(hist / total)
    return np.concatenate(hist_parts)


def l1_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a - b).mean())


def bbox_metrics(image: Image.Image) -> dict:
    bbox = alpha_bbox(image)
    if bbox is None:
        return {"bbox": None, "alpha_area": 0}
    left, top, right, bottom = bbox
    alpha = image.convert("RGBA").getchannel("A")
    area = sum(1 for value in alpha.getdata() if value > 8)
    return {
        "bbox": [left, top, right, bottom],
        "bbox_width": right - left,
        "bbox_height": bottom - top,
        "bbox_aspect": round((right - left) / max(1, bottom - top), 4),
        "alpha_area": area,
    }


def metric_range(values: list[float]) -> float:
    return max(values) - min(values) if values else 0.0


def load_frames(run_dir: Path, frame_dir: str | None) -> tuple[Path, list[Image.Image]]:
    if frame_dir:
        source = Path(frame_dir).expanduser().resolve()
    elif (run_dir / "accepted_keyposes").exists():
        source = run_dir / "accepted_keyposes"
    else:
        source = run_dir / "sequence_frames"
    return source, read_sequence(source)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--reference")
    parser.add_argument("--frame-dir")
    parser.add_argument("--output")
    args = parser.parse_args()

    profile = load_profile(args.profile)
    run_dir = Path(args.run_dir).expanduser().resolve()
    frame_dir, frames = load_frames(run_dir, args.frame_dir)
    output = Path(args.output).expanduser().resolve() if args.output else run_dir / "identity_consistency_score.json"
    normalized = [normalized_crop(frame) for frame in frames]
    histograms = [color_histogram(frame) for frame in frames]
    metrics = [bbox_metrics(frame) for frame in frames]

    pair_ssim = [ssim(a, b) for a, b in zip(normalized, normalized[1:])]
    loop_ssim = ssim(normalized[-1], normalized[0]) if len(normalized) > 1 else 1.0
    pair_color_dist = [l1_distance(a, b) for a, b in zip(histograms, histograms[1:])]
    loop_color_dist = l1_distance(histograms[-1], histograms[0]) if len(histograms) > 1 else 0.0

    widths = [float(item["bbox_width"]) for item in metrics if item.get("bbox")]
    heights = [float(item["bbox_height"]) for item in metrics if item.get("bbox")]
    aspects = [float(item["bbox_aspect"]) for item in metrics if item.get("bbox")]
    areas = [float(item["alpha_area"]) for item in metrics if item.get("bbox")]
    median_area = float(np.median(areas)) if areas else 0.0
    area_range_ratio = metric_range(areas) / median_area if median_area else 0.0

    reference_scores = {}
    if args.reference:
        reference = Image.open(Path(args.reference).expanduser().resolve()).convert("RGBA")
        ref_norm = normalized_crop(reference)
        ref_hist = color_histogram(reference)
        reference_scores = {
            "reference": str(Path(args.reference).expanduser().resolve()),
            "ssim_to_reference": [round(ssim(ref_norm, frame), 4) for frame in normalized],
            "color_distance_to_reference": [round(l1_distance(ref_hist, hist), 4) for hist in histograms],
        }

    routing_hints: list[str] = []
    thresholds = get_path(profile, "thresholds.identity_consistency", {})
    min_pair_ssim = float(thresholds.get("min_pair_ssim", 0.58))
    max_pair_color_distance = float(thresholds.get("max_pair_color_distance", 0.11))
    max_bbox_width_range = float(thresholds.get("max_bbox_width_range_px", 18.0))
    max_bbox_height_range = float(thresholds.get("max_bbox_height_range_px", 18.0))
    max_alpha_area_range_ratio = float(thresholds.get("max_alpha_area_range_ratio", 0.12))
    max_bbox_aspect_range = float(thresholds.get("max_bbox_aspect_range", 0.16))
    min_reference_ssim = float(thresholds.get("min_reference_ssim", 0.45))
    if pair_ssim and min(pair_ssim) < min_pair_ssim:
        routing_hints.append("IDENTITY_DRIFT")
    if pair_color_dist and max(pair_color_dist) > max_pair_color_distance:
        routing_hints.append("IDENTITY_DRIFT")
    if metric_range(widths) > max_bbox_width_range or metric_range(heights) > max_bbox_height_range or area_range_ratio > max_alpha_area_range_ratio:
        routing_hints.append("SIZE_DRIFT")
    if metric_range(aspects) > max_bbox_aspect_range:
        routing_hints.append("BODY_SHAPE_DRIFT")
    if reference_scores and min(reference_scores["ssim_to_reference"]) < min_reference_ssim:
        routing_hints.append("IDENTITY_DRIFT")

    payload = {
        "schema_version": "sofunny-identity-consistency-score.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "routing_only",
        "approval_boundary": "Metrics support failure routing only. They do not approve production.",
        "profile": profile.get("profile_name"),
        "run_dir": str(run_dir),
        "frame_dir": str(frame_dir),
        "frame_count": len(frames),
        "scores": {
            "pair_ssim": [round(value, 4) for value in pair_ssim],
            "loop_ssim": round(loop_ssim, 4),
            "pair_color_distance": [round(value, 4) for value in pair_color_dist],
            "loop_color_distance": round(loop_color_dist, 4),
            "bbox_width_range_px": round(metric_range(widths), 2),
            "bbox_height_range_px": round(metric_range(heights), 2),
            "bbox_aspect_range": round(metric_range(aspects), 4),
            "alpha_area_range_ratio": round(area_range_ratio, 4),
        },
        "thresholds": thresholds,
        "reference_scores": reference_scores,
        "routing_hints": sorted(set(routing_hints)),
        "frames": metrics,
    }
    write_json(output, payload)
    print(json.dumps({"status": payload["status"], "output": str(output), "routing_hints": payload["routing_hints"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
