#!/usr/bin/env python3
"""Create a diagnostic-only SoFunny sequence preview.

This script is the sanctioned path for quick motion previews when clean
production layers do not exist yet. It must never create production approval.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from sofunny_anim.image_io import parse_canvas
from sofunny_anim.previews import save_checker_gif, save_contact_sheet
from sofunny_anim.profiles import keypose_count, load_profile, phases_for


CAPABILITY_REQUIREMENTS = {
    "foot_articulation": {
        "walk",
        "front_walk",
        "step",
        "run",
        "jog",
        "march",
        "stride",
    },
    "tail_articulation": {
        "tail",
        "wag",
        "sway",
    },
    "hand_or_prop_contact": {
        "hand",
        "wave",
        "catch",
        "petal",
        "coin",
        "prop",
        "deal",
        "hold",
        "present",
        "touch",
    },
    "accessory_secondary_motion": {
        "pearl",
        "bow",
        "ribbon",
        "necklace",
        "hair",
        "ear",
    },
    "expression_variant": {
        "blink",
        "wink",
        "smile",
        "eye",
    },
}

PRESET_CAPABILITIES = {
    "whole_body_bounce": {"whole_character_translation", "whole_character_squash"},
    "gentle_walk_in_place": {"whole_character_translation", "whole_character_squash"},
    "idle_bob": {"whole_character_translation"},
}

CAPABILITY_TO_REQUIRED_ROUTE = {
    "foot_articulation": "source_animation_or_provider_keyposes_with_clean_feet_skirt_masks",
    "tail_articulation": "source_animation_or_provider_keyposes_with_clean_tail_layer",
    "hand_or_prop_contact": "provider_keypose_or_masked_local_redraw_with_contact_occlusion",
    "accessory_secondary_motion": "clean accessory masks/backfill or provider keyposes",
    "expression_variant": "approved expression variant or clean face mask",
}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_to_canvas(source: Image.Image, canvas: tuple[int, int], margin: int = 42) -> tuple[Image.Image, dict]:
    rgba = source.convert("RGBA")
    bbox = rgba.getbbox()
    if bbox is None:
        raise ValueError("reference image has no visible pixels")
    crop = rgba.crop(bbox)
    scale = min((canvas[0] - margin * 2) / crop.width, (canvas[1] - margin * 2) / crop.height, 1.0)
    resized = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.Resampling.LANCZOS)
    out = Image.new("RGBA", canvas, (0, 0, 0, 0))
    paste = (round((canvas[0] - resized.width) / 2), round(canvas[1] - margin - resized.height))
    out.alpha_composite(resized, paste)
    return out, {
        "source_bbox": list(bbox),
        "scale": scale,
        "paste": list(paste),
        "normalized_bbox": list(out.getbbox() or (0, 0, 0, 0)),
    }


def transform_whole(source: Image.Image, *, tx: float, ty: float, sx: float, sy: float, rotate: float) -> Image.Image:
    bbox = source.getbbox()
    if bbox is None:
        return Image.new("RGBA", source.size, (0, 0, 0, 0))
    crop = source.crop(bbox)
    resized = crop.resize((max(1, round(crop.width * sx)), max(1, round(crop.height * sy))), Image.Resampling.BICUBIC)
    if rotate:
        resized = resized.rotate(rotate, expand=True, resample=Image.Resampling.BICUBIC)
    cx = (bbox[0] + bbox[2]) / 2 + tx
    bottom = bbox[3] + ty
    out = Image.new("RGBA", source.size, (0, 0, 0, 0))
    out.alpha_composite(resized, (round(cx - resized.width / 2), round(bottom - resized.height)))
    return out


def build_frames(source: Image.Image, frame_count: int, preset: str) -> tuple[list[Image.Image], list[dict]]:
    frames: list[Image.Image] = []
    frame_meta: list[dict] = []
    for index in range(frame_count):
        progress = index / max(1, frame_count - 1)
        theta = math.tau * progress
        if preset == "whole_body_bounce":
            contact = (1 + math.cos(theta)) / 2
            lift = max(0.0, math.sin(theta))
            tx = 1.5 * math.sin(theta)
            ty = 3 * contact - 18 * lift
            sx = 1.0 + 0.018 * contact
            sy = 1.0 - 0.026 * contact + 0.012 * lift
            rotate = 1.0 * math.sin(theta)
            phase = "diagnostic_bounce"
            visual = "whole-character squash, lift, land, and settle"
        elif preset == "gentle_walk_in_place":
            tx = 2.0 * math.sin(theta)
            ty = 2.5 * math.cos(theta * 2)
            sx = 1.0 + 0.006 * abs(math.cos(theta))
            sy = 1.0 - 0.010 * abs(math.cos(theta))
            rotate = 0.8 * math.sin(theta)
            phase = "diagnostic_walk_cycle"
            visual = "whole-character walk-in-place rhythm only; no clean foot layers"
        else:
            tx = 0.0
            ty = 2.5 * math.sin(theta)
            sx = 1.0
            sy = 1.0
            rotate = 0.0
            phase = "diagnostic_idle_bob"
            visual = "whole-character idle bob only"
        frames.append(transform_whole(source, tx=tx, ty=ty, sx=sx, sy=sy, rotate=rotate))
        frame_meta.append(
            {
                "index": index,
                "phase": phase,
                "file": f"sequence_frames/{index:03d}.png",
                "required_visual_change": visual,
                "transforms": {
                    "whole_character": {
                        "translate": [round(tx, 3), round(ty, 3)],
                        "scale": [round(sx, 4), round(sy, 4)],
                        "rotate": round(rotate, 3),
                    }
                },
            }
        )
    return frames, frame_meta


def semantic_capability(action: str, preset: str, force: bool) -> dict:
    normalized = action.lower().replace("-", "_")
    matched: dict[str, list[str]] = {}
    for requirement, tokens in CAPABILITY_REQUIREMENTS.items():
        hits = sorted(token for token in tokens if token in normalized)
        if hits:
            matched[requirement] = hits
    unsupported = sorted(matched)
    status = "pass" if not unsupported else "fail"
    return {
        "schema_version": "sofunny-diagnostic-semantic-capability.v1",
        "status": status,
        "action": action,
        "preset": preset,
        "force_diagnostic": force,
        "preset_capabilities": sorted(PRESET_CAPABILITIES.get(preset, [])),
        "detected_requirements": matched,
        "unsupported_requirements": unsupported,
        "required_routes": {name: CAPABILITY_TO_REQUIRED_ROUTE[name] for name in unsupported},
        "blocks_sequence_generation": bool(unsupported and not force),
        "blocks_production_admission": True,
        "reason": (
            "diagnostic preview can only move the whole character; target action requires local semantic motion"
            if unsupported
            else "diagnostic preview can express this rough whole-character motion direction"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--character-name", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--frames", type=int)
    parser.add_argument("--canvas")
    parser.add_argument("--preset", choices=["whole_body_bounce", "gentle_walk_in_place", "idle_bob"], default="whole_body_bounce")
    parser.add_argument("--duration-ms", type=int, default=60)
    parser.add_argument(
        "--force-diagnostic",
        action="store_true",
        help="Generate a weak diagnostic preview even when semantic capability is known to be insufficient.",
    )
    args = parser.parse_args()

    profile = load_profile(args.profile)
    frame_count = args.frames if args.frames is not None else keypose_count(profile, "candidate", 16)
    if frame_count <= 1:
        parser.error("--frames must be greater than 1")
    canvas = parse_canvas(args.canvas or profile.get("default_canvas", "384x384"))
    reference = Path(args.reference).expanduser().resolve()
    if not reference.exists():
        parser.error(f"--reference does not exist: {reference}")

    run_dir = Path(args.run_dir).expanduser().resolve()
    source_dir = run_dir / "source"
    frames_dir = run_dir / "sequence_frames"
    briefs_dir = run_dir / "generation_briefs"
    capability = semantic_capability(args.action, args.preset, args.force_diagnostic)
    if capability["blocks_sequence_generation"]:
        run_dir.mkdir(parents=True, exist_ok=True)
        write_json(run_dir / "semantic_capability_report.json", capability)
        write_json(
            run_dir / "candidate_boundary_report.json",
            {
                "schema_version": "sofunny-candidate-boundary-report.v1",
                "status": "fail",
                "admission_eligible": False,
                "blocks_production_admission": True,
                "generator": "create_diagnostic_sequence_preview.py",
                "reason": capability["reason"],
                "required_routes": capability["required_routes"],
                "forbidden_next_steps": ["sequence_preview_claim", "finalize_production", "production_keypose_freeze", "production_locked_export"],
            },
        )
        write_json(
            run_dir / "diagnostic_preview_report.json",
            {
                "schema_version": "sofunny-diagnostic-preview-report.v1",
                "status": "fail",
                "diagnostic_only": True,
                "production_eligible": False,
                "frame_count": 0,
                "preset": args.preset,
                "reason": capability["reason"],
                "semantic_capability_report": "semantic_capability_report.json",
            },
        )
        (run_dir / "admission_report.md").write_text(
            "# Admission Report\n\n"
            "Status: fail\n\n"
            "Diagnostic preview was blocked because the target action requires local semantic motion that this route cannot express.\n",
            encoding="utf-8",
        )
        print(json.dumps({"status": "fail", "run_dir": str(run_dir), "reason": capability["reason"], "required_routes": capability["required_routes"]}, ensure_ascii=False, indent=2))
        return 1

    for directory in (source_dir, frames_dir, briefs_dir):
        directory.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("*.png"):
        old.unlink()

    normalized, normalize_report = normalize_to_canvas(Image.open(reference), canvas)
    reference_copy = source_dir / reference.name
    if reference_copy != reference:
        reference_copy.write_bytes(reference.read_bytes())
    normalized.save(source_dir / "canonical-normalized.png")

    frames, frame_meta = build_frames(normalized, frame_count, args.preset)
    for index, frame in enumerate(frames):
        frame.save(frames_dir / f"{index:03d}.png")
    save_contact_sheet(frames, run_dir / "contact_sheet.png", cell_size=192)
    save_checker_gif(frames, run_dir / "animation_checker.gif", duration=args.duration_ms)

    now = datetime.now(timezone.utc).isoformat()
    profile_name = profile.get("profile_name", args.profile)
    phases = phases_for(profile, frame_count, args.action)
    generation = {
        "route": "diagnostic_sequence_preview",
        "generator": "create_diagnostic_sequence_preview.py",
        "generator_type": "skill_diagnostic_preview",
        "preset": args.preset,
        "diagnostic_only": True,
        "admission_eligible": False,
        "reference_used_for_generation": True,
        "ad_hoc_local_generator": False,
        "semantic_capability_status": capability["status"],
    }
    write_json(
        run_dir / "sofunny-run-manifest.json",
        {
            "schema_version": "sofunny-character-gif.v1",
            "created_at": now,
            "profile": profile_name,
            "character_name": args.character_name,
            "action_name": args.action,
            "target": {
                "output": "diagnostic_sequence_preview",
                "frames": frame_count,
                "canvas": {"width": canvas[0], "height": canvas[1], "transparent": True},
            },
            "reference": {
                "source_type": "local_file",
                "source": str(reference),
                "used_for_generation": True,
            },
            "generation": generation,
            "status": "diagnostic_preview",
            "verdict": {"production_approved": False},
        },
    )
    write_json(
        run_dir / "identity-lock.json",
        {
            "character_name": args.character_name,
            "canonical_reference": {"source_type": "local_file", "source": str(reference), "used_for_generation": True},
            "must_keep": {
                "face": ["copy source pixels only"],
                "body_shape": ["diagnostic whole-character transform only"],
                "headwear_or_hair": ["copy source pixels only"],
                "tail": ["copy source pixels only"],
                "accessories": ["copy source pixels only"],
                "palette": ["copy source pixels only"],
                "line_style": ["copy source pixels only"],
                "proportions": ["copy source pixels only"],
            },
            "forbidden_drift": [
                "manual facial overlay",
                "manual accessory overlay",
                "flat PNG hard split promoted to production",
                "production approval from diagnostic preview",
            ],
            "review_status": "draft",
        },
    )
    write_json(
        run_dir / "motion-contract.json",
        {
            "action_name": args.action,
            "target_frames": frame_count,
            "canvas": {"width": canvas[0], "height": canvas[1], "transparent": True},
            "phases": [{"name": phases[index], "frames": [index, index], "description": "diagnostic preview phase"} for index in range(frame_count)],
            "anchor_rules": {
                "diagnostic_only": True,
                "max_bbox_bottom_range_px": None,
                "center_x_rule": "diagnostic preview only; no production claim",
            },
            "review_status": "diagnostic_only",
        },
    )
    write_json(
        run_dir / "action_component_plan.json",
        {
            "schema_version": "sofunny-action-component-plan.v1",
            "action_name": args.action,
            "route": "diagnostic_sequence_preview",
            "diagnostic_only": True,
            "production_eligible": False,
            "frames": frame_count,
            "phases": frame_meta,
        },
    )
    write_json(
        run_dir / "candidate_boundary_report.json",
        {
            "schema_version": "sofunny-candidate-boundary-report.v1",
            "status": "diagnostic_only" if capability["status"] == "pass" else "fail",
            "admission_eligible": False,
            "blocks_production_admission": True,
            "generator": "create_diagnostic_sequence_preview.py",
            "reason": "diagnostic sequence preview cannot replace source-animation contracts, freeze, locked export, or visual admission",
            "semantic_capability_report": "semantic_capability_report.json",
            "forbidden_next_steps": ["finalize_production", "production_keypose_freeze", "production_locked_export"],
        },
    )
    write_json(run_dir / "semantic_capability_report.json", capability)
    write_json(
        run_dir / "diagnostic_preview_report.json",
        {
            "schema_version": "sofunny-diagnostic-preview-report.v1",
            "status": "pass" if capability["status"] == "pass" else "fail",
            "diagnostic_only": True,
            "production_eligible": False,
            "frame_count": frame_count,
            "canvas": {"width": canvas[0], "height": canvas[1]},
            "preset": args.preset,
            "normalize_report": normalize_report,
            "outputs": {
                "sequence_frames": "sequence_frames",
                "contact_sheet": "contact_sheet.png",
                "animation_checker": "animation_checker.gif",
            },
            "semantic_capability_report": "semantic_capability_report.json",
        },
    )
    write_json(run_dir / "style_lock_report.json", {"status": "draft", "identity_match": "diagnostic_pending", "drift_findings": [], "notes": ["diagnostic preview only"]})
    write_json(run_dir / "jitter_diagnostics.json", {"status": "draft", "frame_count": frame_count, "findings": ["diagnostic preview only"]})
    write_json(
        run_dir / "visual-review.json",
        {
            "status": "draft",
            "contact_sheet_reviewed": False,
            "animation_reviewed": False,
            "identity": "pending",
            "motion": "pending",
            "export_quality": "not_applicable",
            "required_fixes": [
                "diagnostic preview must be replaced by production route before admission",
                *(
                    ["target action semantics exceed diagnostic preview capability; use required route from semantic_capability_report.json"]
                    if capability["status"] != "pass"
                    else []
                ),
            ],
        },
    )
    (briefs_dir / "keyposes.md").write_text(
        f"# {args.character_name} {args.action} Diagnostic Preview\n\n"
        "This preview is diagnostic-only. It must not be used for production freeze or final admission.\n",
        encoding="utf-8",
    )
    (briefs_dir / "sequence.md").write_text(
        f"# Diagnostic Sequence\n\nFrames: {frame_count}\nPreset: {args.preset}\nAdmission eligible: false\n",
        encoding="utf-8",
    )
    (run_dir / "admission_report.md").write_text(
        "# Admission Report\n\nStatus: diagnostic_only\n\nThis run is not production-admission eligible.\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "diagnostic_only" if capability["status"] == "pass" else "diagnostic_only_semantic_fail", "run_dir": str(run_dir), "frames": frame_count}, ensure_ascii=False, indent=2))
    return 0 if capability["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
