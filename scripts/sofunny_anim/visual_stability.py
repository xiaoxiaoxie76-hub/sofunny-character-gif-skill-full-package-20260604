from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


@dataclass
class VisualStabilityFrame:
    frame: int
    bbox: tuple[int, int, int, int]
    bbox_width: int
    bbox_height: int
    top_centroid_x: float
    top_centroid_y: float
    mid_centroid_x: float
    mid_centroid_y: float
    alpha_area: int


def median(values: list[float]) -> float:
    if not values:
        raise ValueError("cannot compute median of empty list")
    ordered = sorted(values)
    mid = len(ordered) // 2
    return float(ordered[mid]) if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def metric_range(values: list[float]) -> float:
    return max(values) - min(values) if values else 0.0


def centroid(points: list[tuple[int, int]]) -> tuple[float, float]:
    if not points:
        return 0.0, 0.0
    return (
        sum(x for x, _ in points) / len(points),
        sum(y for _, y in points) / len(points),
    )


def measure_frame(frame: Image.Image, index: int) -> VisualStabilityFrame:
    rgba = frame.convert("RGBA")
    bbox = rgba.getbbox()
    if bbox is None:
        raise ValueError(f"frame {index} has no foreground")
    left, top, right, bottom = bbox
    height = bottom - top
    alpha = rgba.getchannel("A")
    pix = alpha.load()
    top_band_bottom = top + int(height * 0.45)
    mid_band_top = top + int(height * 0.20)
    mid_band_bottom = top + int(height * 0.58)
    top_points: list[tuple[int, int]] = []
    mid_points: list[tuple[int, int]] = []
    area = 0
    for y in range(alpha.height):
        for x in range(alpha.width):
            if pix[x, y] == 0:
                continue
            if pix[x, y] >= 96:
                area += 1
            if y <= top_band_bottom:
                top_points.append((x, y))
            if mid_band_top <= y <= mid_band_bottom:
                mid_points.append((x, y))
    top_cx, top_cy = centroid(top_points)
    mid_cx, mid_cy = centroid(mid_points)
    return VisualStabilityFrame(
        frame=index,
        bbox=bbox,
        bbox_width=right - left,
        bbox_height=bottom - top,
        top_centroid_x=top_cx,
        top_centroid_y=top_cy,
        mid_centroid_x=mid_cx,
        mid_centroid_y=mid_cy,
        alpha_area=area,
    )


def audit_visual_stability(frames: list[Image.Image], thresholds: dict | None = None) -> dict:
    thresholds = thresholds or {}
    measured = [measure_frame(frame, index) for index, frame in enumerate(frames)]
    bbox_tops = [float(item.bbox[1]) for item in measured]
    widths = [float(item.bbox_width) for item in measured]
    heights = [float(item.bbox_height) for item in measured]
    top_xs = [float(item.top_centroid_x) for item in measured]
    mid_xs = [float(item.mid_centroid_x) for item in measured]
    top_ys = [float(item.top_centroid_y) for item in measured]
    mid_ys = [float(item.mid_centroid_y) for item in measured]
    areas = [float(item.alpha_area) for item in measured]
    median_area = median(areas)
    warnings: list[str] = []
    status = "pass"

    checks = {
        "bbox_top_range_px": (metric_range(bbox_tops), float(thresholds.get("max_bbox_top_range_px", 14.0)), "bbox top range exceeds threshold"),
        "bbox_height_range_px": (metric_range(heights), float(thresholds.get("max_bbox_height_range_px", 18.0)), "foreground height range exceeds threshold"),
        "bbox_width_range_px": (metric_range(widths), float(thresholds.get("max_bbox_width_range_px", 12.0)), "foreground width range exceeds threshold"),
        "top_centroid_x_range_px": (metric_range(top_xs), float(thresholds.get("max_top_centroid_x_range_px", 8.0)), "upper-body/head x range exceeds threshold"),
        "mid_centroid_x_range_px": (metric_range(mid_xs), float(thresholds.get("max_mid_centroid_x_range_px", 8.0)), "torso/face x range exceeds threshold"),
        "top_centroid_y_range_px": (metric_range(top_ys), float(thresholds.get("max_top_centroid_y_range_px", 18.0)), "upper-body/head y range exceeds threshold"),
        "mid_centroid_y_range_px": (metric_range(mid_ys), float(thresholds.get("max_mid_centroid_y_range_px", 18.0)), "torso/face y range exceeds threshold"),
    }
    for _, (value, threshold, message) in checks.items():
        if value > threshold:
            status = "warn"
            warnings.append(message)
    area_range_ratio = metric_range(areas) / median_area if median_area else 0.0
    max_area_ratio = float(thresholds.get("max_alpha_area_range_ratio", 0.08))
    if area_range_ratio > max_area_ratio:
        status = "warn"
        warnings.append("alpha area changes by more than threshold")

    return {
        "status": status,
        "frame_count": len(frames),
        "thresholds": {
            "max_bbox_top_range_px": checks["bbox_top_range_px"][1],
            "max_bbox_height_range_px": checks["bbox_height_range_px"][1],
            "max_bbox_width_range_px": checks["bbox_width_range_px"][1],
            "max_top_centroid_x_range_px": checks["top_centroid_x_range_px"][1],
            "max_mid_centroid_x_range_px": checks["mid_centroid_x_range_px"][1],
            "max_top_centroid_y_range_px": checks["top_centroid_y_range_px"][1],
            "max_mid_centroid_y_range_px": checks["mid_centroid_y_range_px"][1],
            "max_alpha_area_range_ratio": max_area_ratio,
        },
        "bbox_top_range_px": round(checks["bbox_top_range_px"][0], 2),
        "bbox_height_range_px": round(checks["bbox_height_range_px"][0], 2),
        "bbox_width_range_px": round(checks["bbox_width_range_px"][0], 2),
        "top_centroid_x_range_px": round(checks["top_centroid_x_range_px"][0], 2),
        "mid_centroid_x_range_px": round(checks["mid_centroid_x_range_px"][0], 2),
        "top_centroid_y_range_px": round(checks["top_centroid_y_range_px"][0], 2),
        "mid_centroid_y_range_px": round(checks["mid_centroid_y_range_px"][0], 2),
        "alpha_area_range_ratio": round(area_range_ratio, 4),
        "warnings": warnings,
        "frames": [
            {
                "frame": item.frame,
                "bbox": item.bbox,
                "bbox_width": item.bbox_width,
                "bbox_height": item.bbox_height,
                "top_centroid": [round(item.top_centroid_x, 2), round(item.top_centroid_y, 2)],
                "mid_centroid": [round(item.mid_centroid_x, 2), round(item.mid_centroid_y, 2)],
                "alpha_area": item.alpha_area,
            }
            for item in measured
        ],
    }
