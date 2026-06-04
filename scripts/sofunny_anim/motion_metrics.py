from __future__ import annotations

from PIL import Image, ImageChops

from .anchors import AnchorMetrics, compute_anchor, metric_range


def frame_delta(a: Image.Image, b: Image.Image) -> float:
    diff = ImageChops.difference(a.convert("RGBA"), b.convert("RGBA"))
    hist = diff.histogram()
    total = sum(value * (index % 256) for index, value in enumerate(hist))
    return total / (a.width * a.height * 4 * 255)


def edge_touch_counts(frame: Image.Image, margin: int = 1) -> dict[str, int]:
    alpha = frame.getchannel("A")
    width, height = alpha.size
    boxes = {
        "top": (0, 0, width, margin),
        "bottom": (0, height - margin, width, height),
        "left": (0, 0, margin, height),
        "right": (width - margin, 0, width, height),
    }
    return {name: sum(alpha.crop(box).histogram()[1:]) for name, box in boxes.items()}


def audit_frames(frames: list[Image.Image], duration_ms: int = 90, thresholds: dict | None = None) -> dict:
    thresholds = thresholds or {}
    max_bottom_range = float(thresholds.get("max_bbox_bottom_range_px", 1.0))
    max_anchor_center_range = float(thresholds.get("max_anchor_center_x_range_px", 6.0))
    anchors: list[AnchorMetrics] = [compute_anchor(frame, i) for i, frame in enumerate(frames)]
    bottoms = [float(metric.anchor_bottom) for metric in anchors]
    centers = [float(metric.lower_body_anchor_x) for metric in anchors]
    widths = [float(metric.foreground_width) for metric in anchors]
    heights = [float(metric.foreground_height) for metric in anchors]
    areas = [float(metric.alpha_area) for metric in anchors]
    deltas = [frame_delta(a, b) for a, b in zip(frames, frames[1:])]
    loop_delta = frame_delta(frames[-1], frames[0]) if len(frames) > 1 else 0.0
    edge_counts = [edge_touch_counts(frame) for frame in frames]
    near_duplicates = [i + 1 for i, value in enumerate(deltas) if value < 0.012]
    frame_delta_spikes = [i + 1 for i, value in enumerate(deltas) if value > 0.18]
    status = "pass"
    warnings: list[str] = []
    if metric_range(bottoms) > max_bottom_range:
        status = "warn"
        warnings.append("bbox bottom range exceeds threshold")
    if metric_range(centers) > max_anchor_center_range:
        status = "warn"
        warnings.append("lower-body anchor center range exceeds threshold")
    if len(near_duplicates) >= max(2, len(deltas) // 2):
        status = "warn"
        warnings.append("many near-duplicate frame transitions")
    return {
        "status": status,
        "frame_count": len(frames),
        "duration_ms": duration_ms,
        "bbox_bottom_range_px": metric_range(bottoms),
        "anchor_center_x_range_px": metric_range(centers),
        "bbox_width_range_px": metric_range(widths),
        "bbox_height_range_px": metric_range(heights),
        "alpha_area_range_px": metric_range(areas),
        "loop_delta": round(loop_delta, 6),
        "frame_deltas": [round(value, 6) for value in deltas],
        "edge_touch_counts": edge_counts,
        "near_duplicate_frames": near_duplicates,
        "frame_delta_spikes": frame_delta_spikes,
        "warnings": warnings,
        "thresholds": {
            "max_bbox_bottom_range_px": max_bottom_range,
            "max_anchor_center_x_range_px": max_anchor_center_range,
        },
        "frames": [
            {
                "frame": metric.frame,
                "bbox": metric.bbox,
                "anchor_bottom": metric.anchor_bottom,
                "lower_body_anchor_x": round(metric.lower_body_anchor_x, 2),
                "alpha_area": metric.alpha_area,
            }
            for metric in anchors
        ],
    }
