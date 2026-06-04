#!/usr/bin/env python3
"""Index SoFunny character PNGs and official animation GIFs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from sofunny_anim.profiles import load_profile
from typing import Any

from PIL import Image, ImageSequence


IMAGE_EXTS = {".png", ".gif", ".webp"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_character_icon(path: Path) -> dict[str, str | None]:
    stem = path.stem
    if stem.startswith("ui_com_npcicon_"):
        character_id = stem.removeprefix("ui_com_npcicon_")
        parts = character_id.split("_")
        return {
            "asset_type": "character_icon",
            "character_id": character_id,
            "species": parts[0] if parts else None,
            "variant": "_".join(parts[1:]) if len(parts) > 1 else None,
            "gender": None,
        }
    if stem.startswith("playerskin_"):
        parts = stem.split("_")
        return {
            "asset_type": "player_skin",
            "character_id": stem,
            "species": parts[-1] if parts else None,
            "variant": "_".join(parts[2:]) if len(parts) > 2 else None,
            "gender": parts[1] if len(parts) > 1 else None,
        }
    return {
        "asset_type": "character_image",
        "character_id": stem,
        "species": stem.split("_")[0] if "_" in stem else None,
        "variant": None,
        "gender": None,
    }


def parse_gif_name(path: Path) -> dict[str, str | None]:
    stem = path.stem
    character_id = path.parent.name
    action = None
    action_index = None
    direction = None
    expression = None
    category = "unknown"
    match = re.match(r"^(?P<char>.+)-action_(?P<action>.+?)_(?P<idx>\d+)_(?P<direction>front|back)$", stem)
    if match:
        character_id = match.group("char")
        action = match.group("action")
        action_index = match.group("idx")
        direction = match.group("direction")
        category = "action"
    else:
        match = re.match(r"^(?P<char>.+)-avg_(?P<expr>.+)$", stem)
        if match:
            character_id = match.group("char")
            expression = match.group("expr")
            category = "avg"
    parts = character_id.split("_")
    return {
        "asset_type": "animation_gif",
        "category": category,
        "character_id": character_id,
        "species": parts[0] if parts else None,
        "variant": "_".join(parts[1:]) if len(parts) > 1 else None,
        "action": action,
        "action_index": action_index,
        "direction": direction,
        "expression": expression,
    }


def alpha_bbox_metrics(image: Image.Image) -> dict[str, Any]:
    rgba = image.convert("RGBA")
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
        "alpha_area": area,
    }


def image_record(path: Path, root: Path) -> dict[str, Any]:
    image = Image.open(path)
    first = image.convert("RGBA")
    parsed = parse_character_icon(path)
    return {
        **parsed,
        "path": str(path),
        "relative_path": str(path.relative_to(root)),
        "extension": path.suffix.lower(),
        "sha256": sha256_file(path),
        "width": image.width,
        "height": image.height,
        "frame_count": 1,
        "duration_ms": None,
        "first_frame": alpha_bbox_metrics(first),
    }


def gif_record(path: Path, root: Path) -> dict[str, Any]:
    image = Image.open(path)
    durations: list[int] = []
    bboxes: list[list[int] | None] = []
    bottoms: list[int] = []
    widths: list[int] = []
    heights: list[int] = []
    alpha_areas: list[int] = []
    frames = []
    for frame in ImageSequence.Iterator(image):
        rgba = frame.convert("RGBA")
        frames.append(rgba)
        durations.append(int(frame.info.get("duration", image.info.get("duration", 0)) or 0))
        metrics = alpha_bbox_metrics(rgba)
        bboxes.append(metrics["bbox"])
        if metrics["bbox"]:
            bottoms.append(metrics["bbox"][3])
            widths.append(metrics["bbox_width"])
            heights.append(metrics["bbox_height"])
            alpha_areas.append(metrics["alpha_area"])
    parsed = parse_gif_name(path)
    def rng(values: list[int]) -> int:
        return max(values) - min(values) if values else 0
    return {
        **parsed,
        "path": str(path),
        "relative_path": str(path.relative_to(root)),
        "extension": path.suffix.lower(),
        "sha256": sha256_file(path),
        "width": image.width,
        "height": image.height,
        "frame_count": len(frames),
        "duration_ms": sum(durations) if durations else None,
        "frame_duration_ms_median": sorted(durations)[len(durations) // 2] if durations else None,
        "first_frame": alpha_bbox_metrics(frames[0]) if frames else {"bbox": None, "alpha_area": 0},
        "motion_metrics": {
            "bbox_bottom_range_px": rng(bottoms),
            "bbox_width_range_px": rng(widths),
            "bbox_height_range_px": rng(heights),
            "alpha_area_range_px": rng(alpha_areas),
        },
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "asset_type",
        "category",
        "character_id",
        "species",
        "variant",
        "action",
        "direction",
        "expression",
        "frame_count",
        "duration_ms",
        "width",
        "height",
        "path",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    species: dict[str, int] = {}
    actions: dict[str, int] = {}
    characters: dict[str, int] = {}
    for row in rows:
        if row.get("species"):
            species[row["species"]] = species.get(row["species"], 0) + 1
        if row.get("action"):
            actions[row["action"]] = actions.get(row["action"], 0) + 1
        if row.get("character_id"):
            characters[row["character_id"]] = characters.get(row["character_id"], 0) + 1
    return {
        "total_assets": len(rows),
        "character_images": sum(1 for row in rows if row.get("asset_type") in {"character_icon", "player_skin", "character_image"}),
        "animation_gifs": sum(1 for row in rows if row.get("asset_type") == "animation_gif"),
        "species_counts": dict(sorted(species.items())),
        "action_counts": dict(sorted(actions.items())),
        "character_counts": dict(sorted(characters.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--character-dir", required=True)
    parser.add_argument("--gif-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    profile = load_profile(args.profile)

    character_dir = Path(args.character_dir).expanduser().resolve()
    gif_dir = Path(args.gif_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for root in [character_dir, gif_dir]:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
                continue
            try:
                if path.suffix.lower() == ".gif":
                    rows.append(gif_record(path, root))
                else:
                    rows.append(image_record(path, root))
            except Exception as exc:
                errors.append({"path": str(path), "error": f"{type(exc).__name__}: {exc}"})

    payload = {
        "schema_version": "sofunny-asset-index.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "roots": {"character_dir": str(character_dir), "gif_dir": str(gif_dir)},
        "summary": summarize(rows),
        "assets": rows,
        "errors": errors,
    }
    (output_dir / "asset_index.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(output_dir / "asset_index.csv", rows)
    (output_dir / "summary.json").write_text(json.dumps(payload["summary"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        (output_dir / "errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), **payload["summary"], "errors": len(errors)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
