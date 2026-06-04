#!/usr/bin/env python3
"""Create a SoFunny character GIF run scaffold."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sofunny_anim.profiles import coalesce, get_path, keypose_count, load_profile, phases_for as profile_phases_for


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--character-name", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--action")
    parser.add_argument("--frames", type=int)
    parser.add_argument("--canvas", type=parse_canvas)
    parser.add_argument(
        "--provider",
        choices=["undecided", "local_redraw", "component_rig", "comfyui", "local_lora", "openai_image_edit", "game-character-sprites"],
        default="undecided",
    )
    parser.add_argument("--private-ip", action="store_true")
    args = parser.parse_args()
    profile = load_profile(args.profile)
    args.action = args.action or get_path(profile, "motion_defaults.default_action", None)
    args.frames = args.frames if args.frames is not None else keypose_count(profile, "production", 12)
    args.canvas = parse_canvas(coalesce(args.canvas, profile, "default_canvas", "384x384")) if args.canvas is None else args.canvas
    if not args.action:
        parser.error("--action is required when profile.motion_defaults.default_action is unset")

    if args.frames <= 0:
        parser.error("--frames must be positive")

    run_dir = Path(args.run_dir).expanduser().resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in ["generation_briefs", "parts", "keyposes", "sequence_frames"]:
        (run_dir / name).mkdir(exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    width, height = args.canvas
    reference_path = Path(args.reference).expanduser()
    source_type = "local_file" if reference_path.exists() else "declared_or_chat_attachment"

    manifest = {
        "schema_version": "sofunny-character-gif.v1",
        "created_at": now,
        "profile": profile.get("profile_name"),
        "character_name": args.character_name,
        "action_name": args.action,
        "target": {
            "output": "gif_or_sprite_sequence",
            "frames": args.frames,
            "canvas": {"width": width, "height": height, "transparent": True},
        },
        "provider": {
            "selected": args.provider,
            "private_ip": args.private_ip,
            "external_upload_allowed": False if args.private_ip else None,
        },
        "reference": {
            "source_type": source_type,
            "source": str(reference_path if source_type == "local_file" else args.reference),
            "used_for_generation": False,
        },
        "artifacts": {
            "identity_lock": "identity-lock.json",
            "part_map": "part_map.json",
            "identity_parts_contract": "identity_parts_contract.json",
            "movable_parts_contract": "movable_parts_contract.json",
            "action_component_plan": "action_component_plan.json",
            "part_consistency_report": "part_consistency_report.json",
            "motion_contract": "motion-contract.json",
            "contact_sheet": "contact_sheet.png",
            "jitter_diagnostics": "jitter_diagnostics.json",
            "style_lock_report": "style_lock_report.json",
            "visual_review": "visual-review.json",
            "animation": "animation.gif",
            "admission_report": "admission_report.md",
        },
        "status": "planning",
    }

    identity_lock = {
        "character_name": args.character_name,
        "canonical_reference": manifest["reference"],
        "must_keep": {
            "face": [],
            "body_shape": [],
            "headwear_or_hair": [],
            "tail": [],
            "accessories": [],
            "palette": [],
            "line_style": [],
            "proportions": [],
        },
        "forbidden_drift": [
            "changed face",
            "changed body silhouette",
            "missing accessory",
            "unstable tail",
            "wrong palette",
            "fake transparency",
            "checkerboard artifact",
        ],
        "review_status": "draft",
    }

    motion_contract = {
        "action_name": args.action,
        "target_frames": args.frames,
        "canvas": {"width": width, "height": height, "transparent": True},
        "phases": [{"name": name, "frames": [index, index], "description": "profile motion phase"} for index, name in enumerate(profile_phases_for(profile, args.frames, args.action))],
        "anchor_rules": {
            "fixed_ground_contact": True,
            "max_bbox_bottom_range_px": 1,
            "center_x_rule": "small coherent movement only",
        },
        "review_status": "draft",
    }

    visual_review = {
        "status": "draft",
        "contact_sheet_reviewed": False,
        "animation_reviewed": False,
        "identity": "pending",
        "motion": "pending",
        "export_quality": "pending",
        "required_fixes": [],
    }
    style_lock_report = {
        "status": "draft",
        "identity_match": "pending",
        "drift_findings": [],
        "notes": [],
    }
    jitter_diagnostics = {
        "status": "draft",
        "frame_count": args.frames,
        "bbox_bottom_range_px": None,
        "center_x_range_px": None,
        "loop_delta_sum": None,
        "findings": [],
    }

    write_json(run_dir / "sofunny-run-manifest.json", manifest)
    write_json(run_dir / "identity-lock.json", identity_lock)
    write_json(run_dir / "motion-contract.json", motion_contract)
    write_json(run_dir / "style_lock_report.json", style_lock_report)
    write_json(run_dir / "jitter_diagnostics.json", jitter_diagnostics)
    write_json(run_dir / "visual-review.json", visual_review)
    (run_dir / "generation_briefs" / "keyposes.md").write_text(
        f"# {args.character_name} {args.action} Keyposes\n\n"
        "- Preserve every identity-lock field.\n"
        "- For production GIFs, build part_map.json and source-animation contracts before keypose generation.\n"
        "- Do not use full-frame redraw as production source animation.\n"
        "- Generate or draw 4-6 keyposes before sequence frames.\n"
        "- Reject whole-character redraw drift before in-betweening.\n",
        encoding="utf-8",
    )
    (run_dir / "generation_briefs" / "sequence.md").write_text(
        f"# {args.character_name} {args.action} Sequence\n\n"
        f"- Target frames: {args.frames}\n"
        f"- Canvas: {width}x{height}\n"
        "- Keep ground contact stable unless the action explicitly travels.\n",
        encoding="utf-8",
    )
    (run_dir / "admission_report.md").write_text(
        "# Admission Report\n\n"
        "Status: draft\n\n"
        "Required final evidence: contact_sheet.png, animation.gif, style_lock_report.json, jitter_diagnostics.json, visual-review.json.\n",
        encoding="utf-8",
    )

    print(str(run_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
