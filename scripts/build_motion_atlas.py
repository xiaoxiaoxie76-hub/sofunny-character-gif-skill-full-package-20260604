#!/usr/bin/env python3
"""Build a phase-level motion atlas from selected SoFunny reference GIFs."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path

from sofunny_anim.profiles import load_profile
from typing import Any

from PIL import Image, ImageDraw, ImageSequence


PHASES = [
    "left_contact_down",
    "left_push_off",
    "flight_passing_left_to_right",
    "right_contact_down",
    "right_push_off",
    "flight_recover_to_left_contact",
]


def read_selection(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["selected"]


def sample_indices(frame_count: int, phase_count: int) -> list[int]:
    if frame_count <= 0:
        return []
    return [round(i * (frame_count - 1) / max(1, phase_count - 1)) for i in range(phase_count)]


def alpha_metrics(frame: Image.Image) -> dict[str, Any]:
    rgba = frame.convert("RGBA")
    bbox = rgba.getbbox()
    if bbox is None:
        return {"bbox": None, "alpha_area": 0}
    alpha = rgba.getchannel("A")
    area = sum(1 for value in alpha.getdata() if value > 0)
    left, top, right, bottom = bbox
    return {
        "bbox": [left, top, right, bottom],
        "bbox_width": right - left,
        "bbox_height": bottom - top,
        "bbox_bottom": bottom,
        "alpha_area": area,
    }


def metric_range(values: list[float]) -> float:
    return max(values) - min(values) if values else 0.0


def sample_gif(path: Path, phase_count: int) -> tuple[list[int], list[Image.Image]]:
    image = Image.open(path)
    frames = [frame.convert("RGBA") for frame in ImageSequence.Iterator(image)]
    indices = sample_indices(len(frames), phase_count)
    return indices, [frames[index] for index in indices]


def trim_and_fit(frame: Image.Image, cell: tuple[int, int]) -> Image.Image:
    canvas = Image.new("RGBA", cell, (0, 0, 0, 0))
    bbox = frame.getbbox()
    if bbox is None:
        return canvas
    crop = frame.crop(bbox)
    crop.thumbnail((cell[0] - 28, cell[1] - 36), Image.Resampling.LANCZOS)
    canvas.alpha_composite(crop, ((cell[0] - crop.width) // 2, cell[1] - 12 - crop.height))
    return canvas


def make_sheet(rows: list[dict[str, Any]], output: Path, cell: tuple[int, int]) -> None:
    if not rows:
        return
    header_h = 28
    row_h = cell[1] + header_h
    sheet = Image.new("RGBA", (cell[0] * len(PHASES), row_h * len(rows)), (248, 248, 248, 255))
    draw = ImageDraw.Draw(sheet)
    for row_index, row in enumerate(rows):
        y = row_index * row_h
        label = f"{row_index + 1}. {row['character_id']} {row['action']} score={row['score']}"
        draw.text((4, y + 4), label, fill=(0, 0, 0, 255))
        for phase_index, frame in enumerate(row["display_frames"]):
            x = phase_index * cell[0]
            checker = Image.new("RGBA", cell, (255, 255, 255, 255))
            checker_draw = ImageDraw.Draw(checker)
            step = 16
            for yy in range(0, cell[1], step):
                for xx in range(0, cell[0], step):
                    if ((xx // step) + (yy // step)) % 2 == 0:
                        checker_draw.rectangle((xx, yy, xx + step - 1, yy + step - 1), fill=(232, 232, 232, 255))
            checker.alpha_composite(frame)
            sheet.alpha_composite(checker, (x, y + header_h))
            draw.text((x + 4, y + header_h + 4), f"{phase_index:02d} {PHASES[phase_index]}", fill=(0, 0, 0, 255))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--selection", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--phase-count", type=int, default=6)
    parser.add_argument("--cell", default="192x220")
    args = parser.parse_args()
    profile = load_profile(args.profile)

    cell = tuple(int(part) for part in args.cell.lower().split("x"))
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = read_selection(Path(args.selection).expanduser().resolve())[: args.top]
    atlas_rows: list[dict[str, Any]] = []
    sheet_rows: list[dict[str, Any]] = []

    for rank, item in enumerate(selected, start=1):
        source_path = Path(item["path"])
        donor_dir = output_dir / f"{rank:02d}_{item['character_id']}_{item.get('action')}_{item.get('direction')}"
        frames_dir = donor_dir / "phase_frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        indices, sampled = sample_gif(source_path, args.phase_count)
        display_frames = []
        metrics = []
        for phase_index, frame in enumerate(sampled):
            phase_name = PHASES[phase_index] if phase_index < len(PHASES) else f"phase_{phase_index:02d}"
            frame_path = frames_dir / f"{phase_index:02d}_{phase_name}.png"
            frame.save(frame_path)
            display_frames.append(trim_and_fit(frame, cell))
            frame_metrics = alpha_metrics(frame)
            frame_metrics.update({"phase": phase_name, "source_frame_index": indices[phase_index], "frame_path": str(frame_path)})
            metrics.append(frame_metrics)
        bottoms = [float(m["bbox_bottom"]) for m in metrics if m.get("bbox_bottom") is not None]
        widths = [float(m["bbox_width"]) for m in metrics if m.get("bbox_width") is not None]
        heights = [float(m["bbox_height"]) for m in metrics if m.get("bbox_height") is not None]
        areas = [float(m["alpha_area"]) for m in metrics]
        donor_payload = {
            "rank": rank,
            "character_id": item["character_id"],
            "species": item.get("species"),
            "variant": item.get("variant"),
            "action": item.get("action"),
            "direction": item.get("direction"),
            "score": item.get("score"),
            "source_path": str(source_path),
            "source_frame_count": item.get("frame_count"),
            "source_duration_ms": item.get("duration_ms"),
            "sampled_source_indices": indices,
            "phase_names": PHASES[: args.phase_count],
            "metrics": {
                "bbox_bottom_range_px": metric_range(bottoms),
                "bbox_width_range_px": metric_range(widths),
                "bbox_height_range_px": metric_range(heights),
                "alpha_area_range_px": metric_range(areas),
            },
            "frames": metrics,
            "selection_reasons": item.get("selection_reasons", []),
        }
        (donor_dir / "motion_donor.json").write_text(json.dumps(donor_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        atlas_rows.append(donor_payload)
        sheet_rows.append({**donor_payload, "display_frames": display_frames})

    make_sheet(sheet_rows, output_dir / "motion_atlas_contact_sheet.png", cell)
    atlas_payload = {
        "schema_version": "sofunny-motion-atlas.v1",
        "selection": str(Path(args.selection).expanduser().resolve()),
        "phase_names": PHASES[: args.phase_count],
        "donor_count": len(atlas_rows),
        "recommended_primary": atlas_rows[0] if atlas_rows else None,
        "donors": atlas_rows,
        "contact_sheet": str(output_dir / "motion_atlas_contact_sheet.png"),
    }
    (output_dir / "motion_atlas.json").write_text(json.dumps(atlas_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), "donor_count": len(atlas_rows), "recommended_primary": atlas_rows[0]["character_id"] if atlas_rows else None}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
