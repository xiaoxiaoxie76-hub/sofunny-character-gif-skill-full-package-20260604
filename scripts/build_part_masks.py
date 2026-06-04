#!/usr/bin/env python3
"""Build a source-animation part map from one canonical character image.

This is an MVP pseudo-rig helper, not a full automatic rigging system. It creates
deterministic part crops that can be reviewed, edited, or replaced by manual
masks before source-animation keypose generation.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw


DEFAULT_PARTS = [
    {
        "name": "tail",
        "role": "movable",
        "region": [0.58, 0.42, 1.00, 0.86],
        "anchor": "tail_root",
        "render": True,
    },
    {
        "name": "left_leg",
        "role": "movable",
        "region": [0.28, 0.66, 0.52, 1.00],
        "anchor": "hip_left",
        "render": True,
    },
    {
        "name": "right_leg",
        "role": "movable",
        "region": [0.48, 0.66, 0.72, 1.00],
        "anchor": "hip_right",
        "render": True,
    },
    {
        "name": "torso",
        "role": "fixed_identity",
        "region": [0.22, 0.36, 0.78, 0.82],
        "anchor": "body_center",
        "render": True,
    },
    {
        "name": "left_arm",
        "role": "movable",
        "region": [0.00, 0.34, 0.40, 0.78],
        "anchor": "shoulder_left",
        "render": True,
    },
    {
        "name": "right_arm",
        "role": "movable",
        "region": [0.60, 0.34, 1.00, 0.78],
        "anchor": "shoulder_right",
        "render": True,
    },
    {
        "name": "head",
        "role": "fixed_identity",
        "region": [0.18, 0.00, 0.82, 0.50],
        "anchor": "neck",
        "render": True,
    },
    {
        "name": "face",
        "role": "fixed_identity_reference",
        "region": [0.30, 0.10, 0.70, 0.39],
        "anchor": "head_center",
        "render": False,
    },
    {
        "name": "glasses",
        "role": "fixed_identity_reference",
        "region": [0.26, 0.12, 0.74, 0.31],
        "anchor": "head_center",
        "render": False,
    },
]


def parse_canvas(value: str) -> tuple[int, int]:
    parts = value.lower().split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("canvas must use WIDTHxHEIGHT, e.g. 384x384")
    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("canvas width and height must be integers") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("canvas width and height must be positive")
    return width, height


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_to_canvas(image: Image.Image, canvas: tuple[int, int], margin: int) -> tuple[Image.Image, dict]:
    source = image.convert("RGBA")
    bbox = source.getbbox()
    if bbox is None:
        raise ValueError("canonical image has no visible foreground")
    crop = source.crop(bbox)
    width, height = canvas
    scale = min((width - margin * 2) / crop.width, (height - margin * 2) / crop.height, 1.0)
    if scale <= 0:
        raise ValueError("canvas and margin leave no room for character")
    resized = crop.resize((max(1, round(crop.width * scale)), max(1, round(crop.height * scale))), Image.Resampling.LANCZOS)
    out = Image.new("RGBA", canvas, (0, 0, 0, 0))
    x = round((width - resized.width) / 2)
    y = round(height - margin - resized.height)
    out.alpha_composite(resized, (x, y))
    return out, {
        "source_bbox": list(bbox),
        "scale": scale,
        "paste": [x, y],
        "normalized_bbox": list(out.getbbox() or (0, 0, 0, 0)),
    }


def clip_part(canvas_image: Image.Image, bbox: tuple[int, int, int, int]) -> Image.Image:
    part = Image.new("RGBA", canvas_image.size, (0, 0, 0, 0))
    part.alpha_composite(canvas_image.crop(bbox), (bbox[0], bbox[1]))
    return part


def region_to_bbox(region: list[float], bbox: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    x0 = max(left, round(left + width * region[0]))
    y0 = max(top, round(top + height * region[1]))
    x1 = min(right, round(left + width * region[2]))
    y1 = min(bottom, round(top + height * region[3]))
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"invalid part region resolved to empty bbox: {region}")
    return x0, y0, x1, y1


def write_default_contracts(run_dir: Path, character_name: str, action_name: str, canvas: tuple[int, int], frames: int) -> None:
    identity = {
        "schema_version": "sofunny-identity-parts.v1",
        "character_name": character_name,
        "fixed_identity_parts": [
            {"part": "head", "must_preserve": True, "allowed_change": "minor vertical bob and small rotation only", "max_rotation_deg": 4, "max_translation_px": 8, "max_area_delta_ratio": 0.08},
            {"part": "face", "must_preserve": True, "allowed_change": "approved blink/mouth variants only", "max_rotation_deg": 2, "max_translation_px": 6, "max_area_delta_ratio": 0.06},
            {"part": "glasses", "must_preserve": True, "allowed_change": "translate/rotate with head, no redesign", "max_rotation_deg": 4, "max_translation_px": 8, "max_area_delta_ratio": 0.06},
            {"part": "torso", "must_preserve": True, "allowed_change": "minor squash/stretch only", "max_rotation_deg": 2, "max_translation_px": 8, "max_area_delta_ratio": 0.08},
            {"part": "tail", "must_preserve": True, "allowed_change": "lag rotation/deformation while attached", "max_rotation_deg": 14, "max_translation_px": 12, "max_area_delta_ratio": 0.12},
        ],
        "forbidden_changes": ["redesigned face", "changed glasses shape", "changed body silhouette", "detached tail", "new costume structure"],
    }
    movable = {
        "schema_version": "sofunny-movable-parts.v1",
        "character_name": character_name,
        "movable_parts": [
            {"part": "head", "motion": ["bob_y", "small_rotation"], "max_rotation_deg": 4, "max_translation_px": 8, "must_remain_attached": True},
            {"part": "torso", "motion": ["bob_y", "squash_stretch"], "max_rotation_deg": 2, "max_translation_px": 8, "must_remain_attached": True},
            {"part": "left_arm", "motion": ["swing", "raise", "counter_motion"], "max_rotation_deg": 25, "max_translation_px": 10, "must_remain_attached": True},
            {"part": "right_arm", "motion": ["swing", "touch_glasses", "counter_motion"], "max_rotation_deg": 25, "max_translation_px": 10, "must_remain_attached": True},
            {"part": "left_leg", "motion": ["contact", "passing", "lift"], "max_rotation_deg": 12, "max_translation_px": 12, "must_remain_attached": True},
            {"part": "right_leg", "motion": ["contact", "passing", "lift"], "max_rotation_deg": 12, "max_translation_px": 12, "must_remain_attached": True},
            {"part": "tail", "motion": ["lag", "small_rotation"], "max_rotation_deg": 14, "max_translation_px": 12, "must_remain_attached": True},
        ],
    }
    phase_names = [
        "contact_left",
        "push_left",
        "passing_left",
        "airborne_left",
        "contact_right",
        "push_right",
        "passing_right",
        "airborne_right",
        "contact_left_return",
        "settle_up",
        "settle_down",
        "loop_return",
    ]
    phases = []
    for index in range(frames):
        name = phase_names[index % len(phase_names)]
        # Symmetric, deliberately small transforms. Better art can replace this
        # plan without changing downstream gates.
        direction = -1 if index < frames / 2 else 1
        lift = -6 if "airborne" in name or "passing" in name else 0
        phases.append(
            {
                "name": name,
                "frame": index,
                "transforms": {
                    "head": {"translate": [0, 1 if index % 2 == 0 else -2], "rotate": -direction},
                    "torso": {"translate": [0, lift // 2], "scale": [1.01 if lift == 0 else 0.99, 0.99 if lift == 0 else 1.01]},
                    "left_arm": {"rotate": 10 * direction},
                    "right_arm": {"rotate": -10 * direction},
                    "left_leg": {"translate": [-5 * direction, lift]},
                    "right_leg": {"translate": [5 * direction, 0 if lift else -4]},
                    "tail": {"rotate": 7 * direction},
                },
                "required_visual_change": f"{name}: coherent jog phase with stable identity parts",
            }
        )
    if phases:
        phases[-1]["transforms"] = phases[0]["transforms"]
        phases[-1]["required_visual_change"] = "loop return: visually compatible with first frame"
    action_plan = {
        "schema_version": "sofunny-action-component-plan.v1",
        "action_name": action_name,
        "frames": frames,
        "canvas": {"width": canvas[0], "height": canvas[1]},
        "background": "#00ff00",
        "phases": phases,
        "loop": {"first_last_match": True, "max_loop_delta_px": 2},
    }
    write_json(run_dir / "identity_parts_contract.json", identity)
    write_json(run_dir / "movable_parts_contract.json", movable)
    write_json(run_dir / "action_component_plan.json", action_plan)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--character-name", required=True)
    parser.add_argument("--action", default="small_jog_front")
    parser.add_argument("--canvas", type=parse_canvas, default=parse_canvas("384x384"))
    parser.add_argument("--frames", type=int, default=12)
    parser.add_argument("--margin", type=int, default=42)
    parser.add_argument("--write-default-contracts", action="store_true")
    args = parser.parse_args()

    if args.frames <= 0:
        parser.error("--frames must be positive")

    canonical = Path(args.canonical).expanduser().resolve()
    if not canonical.exists():
        parser.error(f"canonical image does not exist: {canonical}")

    run_dir = Path(args.run_dir).expanduser().resolve()
    parts_dir = run_dir / "parts"
    source_dir = run_dir / "source"
    parts_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(canonical, source_dir / canonical.name)

    normalized, normalize_report = normalize_to_canvas(Image.open(canonical), args.canvas, args.margin)
    normalized_path = source_dir / "canonical-normalized.png"
    normalized.save(normalized_path)
    normalized_bbox = tuple(normalize_report["normalized_bbox"])
    if normalized_bbox == (0, 0, 0, 0):
        parser.error("normalized canonical has no visible foreground")

    entries = []
    render_order = []
    for spec in DEFAULT_PARTS:
        bbox = region_to_bbox(spec["region"], normalized_bbox)
        part = clip_part(normalized, bbox)
        part_path = parts_dir / f"{spec['name']}.png"
        part.save(part_path)
        visible_bbox = part.getbbox()
        entries.append(
            {
                "name": spec["name"],
                "file": f"parts/{spec['name']}.png",
                "role": spec["role"],
                "render": spec["render"],
                "bbox": list(visible_bbox or bbox),
                "region": spec["region"],
                "anchor": spec["anchor"],
                "alpha_area": sum(1 for value in part.getchannel("A").getdata() if value > 0),
            }
        )
        if spec["render"]:
            render_order.append(spec["name"])

    part_map = {
        "schema_version": "sofunny-part-map.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "character_name": args.character_name,
        "action_name": args.action,
        "canvas": {"width": args.canvas[0], "height": args.canvas[1]},
        "canonical": {
            "source": str(canonical),
            "normalized": "source/canonical-normalized.png",
            "normalize_report": normalize_report,
        },
        "route": "source_animation_pseudo_rig_mvp",
        "render_order": render_order,
        "parts": entries,
        "review_status": "draft",
    }
    write_json(run_dir / "part_map.json", part_map)
    if args.write_default_contracts:
        write_default_contracts(run_dir, args.character_name, args.action, args.canvas, args.frames)

    overview = normalized.copy()
    draw = ImageDraw.Draw(overview)
    for entry in entries:
        left, top, right, bottom = entry["bbox"]
        draw.rectangle((left, top, right, bottom), outline=(255, 0, 0, 220), width=1)
        draw.text((left + 2, top + 2), entry["name"], fill=(255, 0, 0, 255))
    overview.save(run_dir / "part_map_overlay.png")
    print(str(run_dir / "part_map.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

