#!/usr/bin/env python3
"""Preflight image-provider output before SoFunny candidate import."""

from __future__ import annotations

import argparse
import json
import math
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from sofunny_anim.anchors import compute_anchor, metric_range
from sofunny_anim.image_io import parse_canvas
from sofunny_anim.profiles import coalesce, keypose_count, load_profile, parse_hex_color


BUILT_IN_BACKGROUND = "#00ff00"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_background(pixel: tuple[int, int, int, int], background: tuple[int, int, int], tolerance: int) -> bool:
    r, g, b, a = pixel
    return a >= 250 and abs(r - background[0]) <= tolerance and abs(g - background[1]) <= tolerance and abs(b - background[2]) <= tolerance


def is_checker_like(pixel: tuple[int, int, int, int]) -> bool:
    r, g, b, a = pixel
    if a == 0:
        return False
    hi = max(r, g, b)
    lo = min(r, g, b)
    return hi >= 185 and hi - lo <= 35


def foreground_mask(image: Image.Image, background: tuple[int, int, int], tolerance: int) -> Image.Image:
    rgba = image.convert("RGBA")
    alpha = Image.new("L", rgba.size, 0)
    src = rgba.load()
    dst = alpha.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            dst[x, y] = 0 if is_background(src[x, y], background, tolerance) else 255
    return alpha


def count_components(mask: Image.Image) -> dict:
    pix = mask.load()
    width, height = mask.size
    visited: set[tuple[int, int]] = set()
    sizes: list[int] = []
    for y in range(height):
        for x in range(width):
            if pix[x, y] == 0 or (x, y) in visited:
                continue
            visited.add((x, y))
            queue: deque[tuple[int, int]] = deque([(x, y)])
            area = 0
            while queue:
                cx, cy = queue.popleft()
                area += 1
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if 0 <= nx < width and 0 <= ny < height and pix[nx, ny] > 0 and (nx, ny) not in visited:
                        visited.add((nx, ny))
                        queue.append((nx, ny))
            sizes.append(area)
    sizes.sort(reverse=True)
    largest = sizes[0] if sizes else 0
    detached = [size for size in sizes[1:] if largest and size / largest >= 0.01]
    return {
        "component_count": len(sizes),
        "largest_component_area": largest,
        "large_detached_component_count": len(detached),
        "component_areas": sizes[:10],
    }


def alpha_from_background(frame: Image.Image, background: tuple[int, int, int], tolerance: int) -> Image.Image:
    rgba = frame.convert("RGBA")
    mask = foreground_mask(rgba, background, tolerance)
    out = rgba.copy()
    out.putalpha(mask)
    return out


def edge_touch_counts(alpha: Image.Image, margin: int) -> dict[str, int]:
    boxes = {
        "top": (0, 0, alpha.width, margin),
        "bottom": (0, alpha.height - margin, alpha.width, alpha.height),
        "left": (0, 0, margin, alpha.height),
        "right": (alpha.width - margin, 0, alpha.width, alpha.height),
    }
    return {name: sum(alpha.crop(box).histogram()[1:]) for name, box in boxes.items()}


def split_sheet(path: Path, expected_frames: int, canvas: tuple[int, int], rows: int | None, columns: int | None) -> tuple[str, list[Image.Image], list[str]]:
    image = Image.open(path).convert("RGBA")
    width, height = image.size
    cell_w, cell_h = canvas
    failures: list[str] = []
    if width == cell_w and height == cell_h and expected_frames == 1:
        return "single_frame", [image], failures
    if width % cell_w != 0 or height % cell_h != 0:
        failures.append("PROVIDER_LAYOUT_FAIL")
        return "invalid", [], failures
    inferred_columns = width // cell_w
    inferred_rows = height // cell_h
    if rows is not None and rows != inferred_rows:
        failures.append("PROVIDER_LAYOUT_FAIL")
    if columns is not None and columns != inferred_columns:
        failures.append("PROVIDER_LAYOUT_FAIL")
    if inferred_rows * inferred_columns != expected_frames:
        failures.append("PROVIDER_LAYOUT_FAIL")
    if failures:
        return "invalid", [], failures
    frames = []
    for row in range(inferred_rows):
        for col in range(inferred_columns):
            box = (col * cell_w, row * cell_h, (col + 1) * cell_w, (row + 1) * cell_h)
            frames.append(image.crop(box))
    layout = "horizontal_sheet" if inferred_rows == 1 else "grid_sheet"
    return layout, frames, failures


def load_frames(input_path: Path, expected_frames: int, canvas: tuple[int, int], rows: int | None, columns: int | None) -> tuple[str, list[Image.Image], list[str]]:
    if input_path.is_dir():
        paths = sorted(input_path.glob("*.png"))
        failures = []
        if len(paths) != expected_frames:
            failures.append("PROVIDER_FRAME_COUNT_FAIL")
        frames = [Image.open(path).convert("RGBA") for path in paths]
        return "separate_png_frames", frames, failures
    return split_sheet(input_path, expected_frames, canvas, rows, columns)


def background_report(frame: Image.Image, background: tuple[int, int, int], tolerance: int) -> dict:
    rgba = frame.convert("RGBA")
    edge_pixels = []
    for x in range(rgba.width):
        edge_pixels.append(rgba.getpixel((x, 0)))
        edge_pixels.append(rgba.getpixel((x, rgba.height - 1)))
    for y in range(rgba.height):
        edge_pixels.append(rgba.getpixel((0, y)))
        edge_pixels.append(rgba.getpixel((rgba.width - 1, y)))
    background_ratio = sum(is_background(pixel, background, tolerance) for pixel in edge_pixels) / len(edge_pixels) if edge_pixels else 0
    checker_ratio = sum(is_checker_like(pixel) for pixel in edge_pixels) / len(edge_pixels) if edge_pixels else 0
    alpha = rgba.getchannel("A")
    hist = alpha.histogram()
    transparent_pixels = sum(hist[:250])
    return {
        "edge_background_ratio": round(background_ratio, 4),
        "edge_checker_like_ratio": round(checker_ratio, 4),
        "non_opaque_pixels": transparent_pixels,
        "background_status": "pass" if background_ratio >= 0.95 and transparent_pixels == 0 and checker_ratio < 0.05 else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--input", required=True)
    parser.add_argument("--run-dir")
    parser.add_argument("--output")
    parser.add_argument("--expected-frames", type=int)
    parser.add_argument("--canvas", type=parse_canvas)
    parser.add_argument("--rows", type=int)
    parser.add_argument("--columns", type=int)
    parser.add_argument("--green-tolerance", type=int)
    parser.add_argument("--max-bbox-bottom-range", type=float)
    parser.add_argument("--max-bbox-width-range", type=float)
    parser.add_argument("--max-bbox-height-range", type=float)
    parser.add_argument("--edge-margin", type=int)
    args = parser.parse_args()
    profile = load_profile(args.profile)
    args.expected_frames = args.expected_frames if args.expected_frames is not None else keypose_count(profile, "production", 12)
    args.canvas = parse_canvas(coalesce(args.canvas, profile, "default_canvas", "384x384")) if args.canvas is None else args.canvas
    args.green_tolerance = int(coalesce(args.green_tolerance, profile, "thresholds.provider_preflight.green_tolerance", 8))
    args.max_bbox_bottom_range = float(coalesce(args.max_bbox_bottom_range, profile, "thresholds.provider_preflight.max_bbox_bottom_range_px", 4.0))
    args.max_bbox_width_range = float(coalesce(args.max_bbox_width_range, profile, "thresholds.provider_preflight.max_bbox_width_range_px", 24.0))
    args.max_bbox_height_range = float(coalesce(args.max_bbox_height_range, profile, "thresholds.provider_preflight.max_bbox_height_range_px", 24.0))
    args.edge_margin = int(coalesce(args.edge_margin, profile, "thresholds.provider_preflight.edge_margin_px", 1))
    background_hex = coalesce(None, profile, "default_background", BUILT_IN_BACKGROUND)
    background_rgb = parse_hex_color(background_hex)

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(str(input_path))
    output_path = Path(args.output).expanduser().resolve() if args.output else (Path(args.run_dir).expanduser().resolve() if args.run_dir else input_path.parent) / "provider_preflight_report.json"

    layout, frames, failures = load_frames(input_path, args.expected_frames, args.canvas, args.rows, args.columns)
    frame_reports: list[dict] = []
    foreground_frames: list[Image.Image] = []

    if not frames:
        status = "fail"
    else:
        for index, frame in enumerate(frames):
            report_failures: list[str] = []
            if frame.size != args.canvas:
                report_failures.append("PROVIDER_CELL_SIZE_FAIL")
            bg = background_report(frame, background_rgb, args.green_tolerance)
            if bg["background_status"] != "pass":
                if bg["non_opaque_pixels"]:
                    report_failures.append("FAKE_TRANSPARENCY")
                if bg["edge_checker_like_ratio"] >= 0.05:
                    report_failures.append("CHECKERBOARD_CONTAMINATION")
                if bg["edge_background_ratio"] < 0.95:
                    report_failures.append("PROVIDER_BACKGROUND_FAIL")
            fg = alpha_from_background(frame, background_rgb, args.green_tolerance)
            bbox = fg.getbbox()
            components = count_components(fg.getchannel("A"))
            if bbox is None:
                report_failures.append("EMPTY_FRAME")
            else:
                touches = edge_touch_counts(fg.getchannel("A"), args.edge_margin)
                if any(value > 0 for value in touches.values()):
                    report_failures.append("EDGE_TOUCHING")
            foreground_frames.append(fg)
            frame_reports.append({
                "frame": index,
                "size": list(frame.size),
                "bbox": list(bbox) if bbox else None,
                "background": bg,
                "components": components,
                "edge_touch_counts": edge_touch_counts(fg.getchannel("A"), args.edge_margin),
                "failures": report_failures,
            })
            failures.extend(report_failures)

        if foreground_frames and all(frame.getbbox() is not None for frame in foreground_frames):
            anchors = [compute_anchor(frame, index) for index, frame in enumerate(foreground_frames)]
            bottom_range = metric_range([float(item.anchor_bottom) for item in anchors])
            width_range = metric_range([float(item.foreground_width) for item in anchors])
            height_range = metric_range([float(item.foreground_height) for item in anchors])
            if bottom_range > args.max_bbox_bottom_range:
                failures.append("PLACEMENT_DRIFT")
            if width_range > args.max_bbox_width_range or height_range > args.max_bbox_height_range:
                failures.append("SIZE_DRIFT")
            aggregate = {
                "bbox_bottom_range_px": bottom_range,
                "bbox_width_range_px": width_range,
                "bbox_height_range_px": height_range,
            }
        else:
            aggregate = {
                "bbox_bottom_range_px": None,
                "bbox_width_range_px": None,
                "bbox_height_range_px": None,
            }

        status = "pass" if not failures else "fail"

    unique_failures = sorted(set(failures))
    payload = {
        "schema_version": "sofunny-provider-preflight.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "input": str(input_path),
        "layout": layout,
        "expected_frames": args.expected_frames,
        "frame_count": len(frames),
        "canvas": {"width": args.canvas[0], "height": args.canvas[1]},
        "profile": profile.get("profile_name"),
        "required_background": background_hex,
        "failures": unique_failures,
        "aggregate": aggregate if frames else {},
        "frames": frame_reports,
        "notes": [
            "Provider output must be separate PNG frames or an exact fixed-cell sheet.",
            "This preflight does not replace identity or action visual review.",
        ],
    }
    write_json(output_path, payload)
    print(json.dumps({"status": status, "report": str(output_path), "failures": unique_failures}, ensure_ascii=False, indent=2))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
