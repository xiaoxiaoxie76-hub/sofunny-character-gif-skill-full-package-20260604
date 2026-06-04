#!/usr/bin/env python3
"""Select motion reference GIFs from a SoFunny asset index."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from sofunny_anim.profiles import load_profile
from typing import Any

from PIL import Image, ImageDraw, ImageSequence


ACTION_WEIGHTS = {
    "small_jog_front": {"walk": 70, "rundryer": 42, "excited": 24},
    "walk_front": {"walk": 70},
    "run_front": {"rundryer": 70, "walk": 50, "excited": 28},
}


def load_index(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["assets"]


def character_species(character_id: str) -> str | None:
    parts = character_id.split("_")
    return parts[0] if parts else None


def score_candidate(row: dict[str, Any], target_character: str, target_action: str, direction: str) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    target_species = character_species(target_character)
    if row.get("asset_type") != "animation_gif" or row.get("category") != "action":
        return -999.0, ["not action gif"]
    if row.get("direction") != direction:
        return -999.0, ["wrong direction"]
    action = row.get("action")
    action_weights = ACTION_WEIGHTS.get(target_action, {target_action: 70})
    if action in action_weights:
        score += action_weights[action]
        reasons.append(f"action match: {action}")
    else:
        score += 5
        reasons.append(f"fallback action: {action}")
    if row.get("species") == target_species:
        score += 30
        reasons.append(f"same species: {target_species}")
    elif row.get("species") in {"beav", "capy"} and target_species in {"beav", "capy"}:
        score += 12
        reasons.append("similar body family")
    frame_count = int(row.get("frame_count") or 0)
    if 36 <= frame_count <= 60:
        score += 12
        reasons.append(f"good frame count: {frame_count}")
    elif frame_count >= 24:
        score += 5
        reasons.append(f"usable frame count: {frame_count}")
    metrics = row.get("motion_metrics") or {}
    bottom_range = float(metrics.get("bbox_bottom_range_px") or 0)
    if bottom_range <= 2:
        score += 8
        reasons.append("stable bottom anchor")
    elif bottom_range <= 8:
        score += 2
        reasons.append(f"moderate bottom range: {bottom_range}")
    width = float(row.get("width") or 0)
    height = float(row.get("height") or 0)
    if width and height:
        ratio = width / height
        if 0.55 <= ratio <= 0.95:
            score += 4
            reasons.append("compact front-body ratio")
    return score, reasons


def sample_gif(path: Path, count: int = 6) -> list[Image.Image]:
    image = Image.open(path)
    frames = [frame.convert("RGBA") for frame in ImageSequence.Iterator(image)]
    if not frames:
        return []
    indices = [round(i * (len(frames) - 1) / max(1, count - 1)) for i in range(count)]
    return [frames[index] for index in indices]


def make_contact_sheet(candidates: list[dict[str, Any]], output: Path, samples_per_gif: int = 6, cell: int = 160) -> None:
    if not candidates:
        return
    rows = []
    for candidate in candidates:
        frames = sample_gif(Path(candidate["path"]), samples_per_gif)
        thumbs = []
        for frame in frames:
            canvas = Image.new("RGBA", (cell, cell), (255, 255, 255, 0))
            bbox = frame.getbbox()
            if bbox:
                crop = frame.crop(bbox)
                crop.thumbnail((cell - 20, cell - 26), Image.Resampling.LANCZOS)
                canvas.alpha_composite(crop, ((cell - crop.width) // 2, cell - 8 - crop.height))
            thumbs.append(canvas)
        rows.append((candidate, thumbs))
    sheet_w = samples_per_gif * cell
    sheet_h = len(rows) * (cell + 38)
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (248, 248, 248, 255))
    draw = ImageDraw.Draw(sheet)
    for row_index, (candidate, thumbs) in enumerate(rows):
        y = row_index * (cell + 38)
        label = f"{row_index + 1}. {candidate['character_id']} {candidate.get('action')} {candidate.get('direction')} score={candidate['score']:.1f}"
        draw.text((4, y + 4), label, fill=(0, 0, 0, 255))
        for i, thumb in enumerate(thumbs):
            sheet.alpha_composite(thumb, (i * cell, y + 30))
            draw.text((i * cell + 4, y + 30), f"{i:02d}", fill=(0, 0, 0, 255))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--asset-index", required=True)
    parser.add_argument("--target-character", required=True)
    parser.add_argument("--target-action", required=True)
    parser.add_argument("--direction", default="front")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--top", type=int, default=8)
    args = parser.parse_args()
    profile = load_profile(args.profile)

    rows = load_index(Path(args.asset_index).expanduser().resolve())
    scored = []
    for row in rows:
        score, reasons = score_candidate(row, args.target_character, args.target_action, args.direction)
        if score <= -900:
            continue
        candidate = dict(row)
        candidate["score"] = round(score, 2)
        candidate["selection_reasons"] = reasons
        scored.append(candidate)
    scored.sort(key=lambda item: item["score"], reverse=True)
    selected = scored[: args.top]
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "sofunny-motion-reference-selection.v1",
        "target_character": args.target_character,
        "target_action": args.target_action,
        "direction": args.direction,
        "selected": selected,
    }
    (output_dir / "motion_reference_selection.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    make_contact_sheet(selected, output_dir / "motion_reference_contact_sheet.png")
    print(json.dumps({"selected_count": len(selected), "output_dir": str(output_dir), "top": [{"character_id": item["character_id"], "action": item.get("action"), "score": item["score"]} for item in selected[:5]]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
