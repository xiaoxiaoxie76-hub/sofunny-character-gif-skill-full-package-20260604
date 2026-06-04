from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


@dataclass
class AnchorMetrics:
    frame: int
    bbox: tuple[int, int, int, int]
    foreground_center_x: float
    lower_body_anchor_x: float
    anchor_bottom: int
    foreground_width: int
    foreground_height: int
    alpha_area: int


def median(values: list[float]) -> float:
    if not values:
        raise ValueError("cannot compute median of empty list")
    ordered = sorted(values)
    mid = len(ordered) // 2
    return float(ordered[mid]) if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def alpha_points(image: Image.Image, threshold: int = 0):
    alpha = image.getchannel("A")
    pix = alpha.load()
    for y in range(alpha.height):
        for x in range(alpha.width):
            if pix[x, y] > threshold:
                yield x, y


def compute_anchor(image: Image.Image, frame_index: int, lower_band_ratio: float = 0.18) -> AnchorMetrics:
    rgba = image.convert("RGBA")
    bbox = rgba.getbbox()
    if bbox is None:
        raise ValueError("frame has no foreground")
    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    lower_start = bottom - max(12, int(height * lower_band_ratio))
    all_xs: list[float] = []
    lower_xs: list[float] = []
    area = 0
    for x, y in alpha_points(rgba):
        all_xs.append(float(x))
        area += 1
        if y >= lower_start:
            lower_xs.append(float(x))
    if not lower_xs:
        lower_xs = all_xs[:]
    return AnchorMetrics(
        frame=frame_index,
        bbox=bbox,
        foreground_center_x=(left + right) / 2,
        lower_body_anchor_x=median(lower_xs),
        anchor_bottom=bottom,
        foreground_width=width,
        foreground_height=height,
        alpha_area=area,
    )


def normalize_offsets(frames: list[Image.Image], canvas: tuple[int, int], margin: int = 24) -> tuple[list[Image.Image], list[AnchorMetrics], list[AnchorMetrics]]:
    before = [compute_anchor(frame, i) for i, frame in enumerate(frames)]
    max_width = max(metric.foreground_width for metric in before)
    max_height = max(metric.foreground_height for metric in before)
    canvas_w, canvas_h = canvas
    scale = min((canvas_w - margin * 2) / max_width, (canvas_h - margin * 2) / max_height)
    if scale <= 0:
        raise ValueError("canvas and margin leave no room for frames")
    target_center_x = canvas_w / 2
    target_bottom = canvas_h - margin
    output: list[Image.Image] = []
    for frame, metric in zip(frames, before):
        crop = frame.crop(metric.bbox)
        scaled = crop.resize((max(1, round(crop.width * scale)), max(1, round(crop.height * scale))), Image.Resampling.LANCZOS)
        anchor_x = (metric.lower_body_anchor_x - metric.bbox[0]) * scale
        anchor_bottom = (metric.anchor_bottom - metric.bbox[1]) * scale
        paste_x = round(target_center_x - anchor_x)
        paste_y = round(target_bottom - anchor_bottom)
        canvas_frame = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        canvas_frame.alpha_composite(scaled, (paste_x, paste_y))
        output.append(canvas_frame)
    after = [compute_anchor(frame, i) for i, frame in enumerate(output)]
    return output, before, after


def normalize_fit_slot(frames: list[Image.Image], canvas: tuple[int, int], margin: int = 48) -> tuple[list[Image.Image], list[AnchorMetrics], list[AnchorMetrics], dict]:
    before = [compute_anchor(frame, i) for i, frame in enumerate(frames)]
    max_width = max(metric.foreground_width for metric in before)
    max_height = max(metric.foreground_height for metric in before)
    canvas_w, canvas_h = canvas
    scale = min((canvas_w - margin * 2) / max_width, (canvas_h - margin * 2) / max_height)
    if scale <= 0:
        raise ValueError("canvas and margin leave no room for frames")
    target_center_x = canvas_w / 2
    target_center_y = canvas_h / 2
    output: list[Image.Image] = []
    margins: list[dict[str, int]] = []
    for frame, metric in zip(frames, before):
        crop = frame.crop(metric.bbox)
        scaled = crop.resize((max(1, round(crop.width * scale)), max(1, round(crop.height * scale))), Image.Resampling.LANCZOS)
        paste_x = round(target_center_x - scaled.width / 2)
        paste_y = round(target_center_y - scaled.height / 2)
        canvas_frame = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        canvas_frame.alpha_composite(scaled, (paste_x, paste_y))
        bbox = canvas_frame.getbbox()
        if bbox is None:
            raise ValueError("fit-slot normalization produced an empty frame")
        margins.append({
            "left": bbox[0],
            "top": bbox[1],
            "right": canvas_w - bbox[2],
            "bottom": canvas_h - bbox[3],
        })
        output.append(canvas_frame)
    after = [compute_anchor(frame, i) for i, frame in enumerate(output)]
    report = {
        "scale": scale,
        "slot_margin_px": margin,
        "max_source_bbox": {"width": max_width, "height": max_height},
        "output_margins": margins,
        "min_output_margin_px": min(min(item.values()) for item in margins),
    }
    return output, before, after, report


def normalize_fit_ground(frames: list[Image.Image], canvas: tuple[int, int], margin: int = 48) -> tuple[list[Image.Image], list[AnchorMetrics], list[AnchorMetrics], dict]:
    before = [compute_anchor(frame, i) for i, frame in enumerate(frames)]
    max_width = max(metric.foreground_width for metric in before)
    max_height = max(metric.foreground_height for metric in before)
    canvas_w, canvas_h = canvas
    scale = min((canvas_w - margin * 2) / max_width, (canvas_h - margin * 2) / max_height)
    if scale <= 0:
        raise ValueError("canvas and margin leave no room for frames")
    target_center_x = canvas_w / 2
    target_bottom = canvas_h - margin
    output: list[Image.Image] = []
    margins: list[dict[str, int]] = []
    for frame, metric in zip(frames, before):
        crop = frame.crop(metric.bbox)
        scaled = crop.resize((max(1, round(crop.width * scale)), max(1, round(crop.height * scale))), Image.Resampling.LANCZOS)
        anchor_x = (metric.lower_body_anchor_x - metric.bbox[0]) * scale
        paste_x = round(target_center_x - anchor_x)
        paste_y = round(target_bottom - scaled.height)
        canvas_frame = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        canvas_frame.alpha_composite(scaled, (paste_x, paste_y))
        bbox = canvas_frame.getbbox()
        if bbox is None:
            raise ValueError("fit-ground normalization produced an empty frame")
        margins.append({
            "left": bbox[0],
            "top": bbox[1],
            "right": canvas_w - bbox[2],
            "bottom": canvas_h - bbox[3],
        })
        output.append(canvas_frame)
    after = [compute_anchor(frame, i) for i, frame in enumerate(output)]
    report = {
        "scale": scale,
        "slot_margin_px": margin,
        "horizontal_anchor": "lower_body_anchor_x",
        "target_bottom_px": target_bottom,
        "max_source_bbox": {"width": max_width, "height": max_height},
        "output_margins": margins,
        "min_output_margin_px": min(min(item.values()) for item in margins),
    }
    return output, before, after, report


def metric_range(values: list[float]) -> float:
    return max(values) - min(values) if values else 0.0
