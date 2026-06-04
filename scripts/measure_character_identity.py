#!/usr/bin/env python3
"""Measure a canonical character image into a reusable identity contract."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def alpha_area(image: Image.Image, threshold: int = 8) -> int:
    return sum(1 for value in image.getchannel("A").getdata() if value >= threshold)


def dominant_colors(image: Image.Image, bbox: tuple[int, int, int, int], limit: int = 8) -> list[dict]:
    crop = image.crop(bbox).convert("RGBA").resize((96, 96), Image.Resampling.LANCZOS)
    counts: Counter[tuple[int, int, int]] = Counter()
    for r, g, b, a in crop.getdata():
        if a < 32:
            continue
        if r >= 245 and g >= 245 and b >= 245:
            continue
        key = (round(r / 16) * 16, round(g / 16) * 16, round(b / 16) * 16)
        counts[key] += 1
    total = sum(counts.values()) or 1
    return [
        {
            "rgb": [max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))],
            "ratio": round(count / total, 4),
        }
        for (r, g, b), count in counts.most_common(limit)
    ]


def horizontal_occupancy(alpha: Image.Image, bbox: tuple[int, int, int, int], bands: int) -> list[dict]:
    left, top, right, bottom = bbox
    height = bottom - top
    out = []
    for index in range(bands):
        y0 = top + round(index * height / bands)
        y1 = top + round((index + 1) * height / bands)
        xs = []
        for y in range(y0, y1):
            for x in range(left, right):
                if alpha.getpixel((x, y)) > 8:
                    xs.append(x)
        if xs:
            out.append({
                "band": index,
                "y_range": [y0, y1],
                "left": min(xs),
                "right": max(xs) + 1,
                "width": max(xs) + 1 - min(xs),
                "center_x": round((min(xs) + max(xs) + 1) / 2, 2),
            })
        else:
            out.append({"band": index, "y_range": [y0, y1], "width": 0})
    return out


def measure(reference: Path, character_name: str, identity_notes: list[str]) -> dict:
    image = Image.open(reference).convert("RGBA")
    bbox = image.getbbox()
    if bbox is None:
        raise ValueError("reference image has no visible foreground")
    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    area = alpha_area(image)
    alpha = image.getchannel("A")
    bands = horizontal_occupancy(alpha, bbox, 5)
    return {
        "schema_version": "sofunny-character-identity-measurement.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "character_name": character_name,
        "source": str(reference),
        "image_size": {"width": image.width, "height": image.height},
        "visible_bbox": [left, top, right, bottom],
        "visible_size": {"width": width, "height": height},
        "visible_aspect_ratio": round(width / height, 6),
        "foreground_alpha_area": area,
        "foreground_coverage_ratio": round(area / (image.width * image.height), 6),
        "vertical_band_occupancy": bands,
        "dominant_colors": dominant_colors(image, bbox),
        "identity_notes": identity_notes,
        "must_preserve": [
            "overall silhouette family",
            "head-to-body proportion",
            "main costume shape and color blocks",
            "hair/accessory placement and relative size",
            "line weight and rendering style",
            "dominant palette",
        ],
        "forbid": [
            "frame-to-frame local proportion drift",
            "cropped accessories, hair, hands, clothing, feet, or props",
            "provider-redesigned face or costume",
            "scale changes unrelated to action projection",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--character-name", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--identity-note", action="append", default=[])
    args = parser.parse_args()
    reference = Path(args.reference).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    payload = measure(reference, args.character_name, args.identity_note)
    write_json(output, payload)
    print(json.dumps({"status": "pass", "output": str(output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
