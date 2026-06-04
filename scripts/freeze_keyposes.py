#!/usr/bin/env python3
"""Freeze accepted SoFunny keyposes before deterministic GIF export."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sofunny_anim.frame_layout import read_sequence, write_sequence
from sofunny_anim.freeze_gate import (
    HARD_ENFORCEMENT_KEYS,
    PASS_VALUES,
    freeze_prerequisite_statuses,
    production_source_animation_route,
    read_json,
)
from sofunny_anim.image_io import parse_canvas
from sofunny_anim.manifests import write_json
from sofunny_anim.previews import save_checker_gif, save_contact_sheet
from sofunny_anim.profiles import coalesce, get_path, load_profile, phases_for as profile_phases_for


DEFAULT_PHASES = {
    6: ["contact", "push_off", "passing", "contact", "push_off", "recover"],
    12: [
        "contact",
        "down",
        "push_off",
        "passing",
        "up",
        "recover",
        "contact",
        "down",
        "push_off",
        "passing",
        "up",
        "recover",
    ],
}


ALLOWED_AFTER_FREEZE = [
    "timing",
    "loop",
    "palette",
    "compression",
    "transparent_export",
    "anchor_normalization",
]


FORBIDDEN_AFTER_FREEZE = [
    "image_gen",
    "redraw",
    "face_repair",
    "body_repair",
    "identity_redraw",
    "broad_provider_regeneration",
    "alpha_volume_hiding",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def phases_for(frame_count: int, phase_csv: str | None) -> list[str]:
    if phase_csv:
        phases = [item.strip() for item in phase_csv.split(",") if item.strip()]
    else:
        phases = DEFAULT_PHASES.get(frame_count) or [f"phase_{index:02d}" for index in range(frame_count)]
    if len(phases) != frame_count:
        raise ValueError(f"phase count {len(phases)} does not match frame count {frame_count}")
    return phases


def status_pass_or_manual(status: str, manual: bool) -> bool:
    return status in PASS_VALUES or manual


PRODUCTION_STRICT_KEYS = {
    "identity",
    "action",
    "body_tail",
    "jitter",
    "visual_stability",
    "provider_preflight",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--frame-dir")
    parser.add_argument("--output-dir")
    parser.add_argument("--canvas", type=parse_canvas)
    parser.add_argument("--duration-ms", type=int)
    parser.add_argument("--action")
    parser.add_argument("--phases")
    parser.add_argument("--manual-approved", action="store_true")
    parser.add_argument("--manual-note", default="")
    parser.add_argument("--stage", choices=["candidate", "production"], default="candidate")
    args = parser.parse_args()
    profile = load_profile(args.profile)
    args.canvas = parse_canvas(coalesce(args.canvas, profile, "default_canvas", "384x384")) if args.canvas is None else args.canvas
    args.duration_ms = int(coalesce(args.duration_ms, profile, "motion_defaults.duration_ms", 90))
    action = args.action or get_path(profile, "motion_defaults.default_action", None)

    run_dir = Path(args.run_dir).expanduser().resolve()
    frame_dir = Path(args.frame_dir).expanduser().resolve() if args.frame_dir else run_dir / "sequence_frames"
    accepted_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else run_dir / "accepted_keyposes"
    report_path = run_dir / "keypose_freeze_report.json"
    manifest_path = run_dir / "keypose_freeze_manifest.json"

    statuses = freeze_prerequisite_statuses(run_dir)
    provider_status = str(read_json(run_dir / "provider_preflight_report.json", {}).get("status", "missing")).lower()
    statuses["provider_preflight"] = provider_status
    strict_production = args.stage == "production" and production_source_animation_route(run_dir)
    failed = {}
    if args.stage == "production":
        for name, status in statuses.items():
            if name in HARD_ENFORCEMENT_KEYS or (strict_production and name in PRODUCTION_STRICT_KEYS):
                if status not in PASS_VALUES:
                    failed[name] = status
            elif not status_pass_or_manual(status, args.manual_approved):
                failed[name] = status

    if failed:
        diagnostic_only = bool(args.manual_approved and strict_production)
        payload = {
            "schema_version": "sofunny-keypose-freeze-report.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "diagnostic_only" if diagnostic_only else "fail",
            "run_dir": str(run_dir),
            "failed_requirements": failed,
            "manual_approved": args.manual_approved,
            "manual_note": args.manual_note,
            "freeze_stage": args.stage,
            "production_source_animation_strict": strict_production,
            "next_step": "Fix failed production reports before freeze. Manual approval is diagnostic-only for production source-animation.",
        }
        write_json(report_path, payload)
        print(json.dumps({"status": "fail", "report": str(report_path), "failed_requirements": failed}, ensure_ascii=False, indent=2))
        return 1

    frames = read_sequence(frame_dir)
    for index, frame in enumerate(frames):
        if frame.size != args.canvas:
            raise ValueError(f"frame {index:02d} size {frame.size} does not match canvas {args.canvas}")
        if frame.getbbox() is None:
            raise ValueError(f"frame {index:02d} has no foreground")

    if accepted_dir.exists():
        shutil.rmtree(accepted_dir)
    paths = write_sequence(frames, accepted_dir)
    phases = phases_for(len(frames), args.phases) if args.phases else profile_phases_for(profile, len(frames), action, DEFAULT_PHASES.get(len(frames)))
    save_contact_sheet(frames, run_dir / "keypose_contact_sheet.png", 192)
    save_checker_gif(frames, run_dir / "keypose_checker_preview.gif", args.duration_ms)

    frame_entries = []
    for index, path in enumerate(paths):
        frame_entries.append({
            "index": index,
            "file": str(path.relative_to(run_dir)) if path.is_relative_to(run_dir) else str(path),
            "sha256": sha256(path),
            "phase": phases[index],
        })

    manifest = {
        "schema_version": "sofunny-keypose-freeze.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_run": str(run_dir),
        "source_frames": str(frame_dir),
        "accepted_keyposes": str(accepted_dir),
        "frame_count": len(frames),
        "canvas": {"width": args.canvas[0], "height": args.canvas[1]},
        "profile": profile.get("profile_name"),
        "action": action,
        "frames": frame_entries,
        "allowed_after_freeze": ALLOWED_AFTER_FREEZE,
        "forbidden_after_freeze": FORBIDDEN_AFTER_FREEZE,
        "requirements": statuses,
        "manual_approved": args.manual_approved,
        "manual_note": args.manual_note,
        "freeze_stage": args.stage,
        "production_source_animation_strict": strict_production,
        "candidate_only": args.stage != "production",
    }
    write_json(manifest_path, manifest)
    write_json(
        report_path,
        {
            "schema_version": "sofunny-keypose-freeze-report.v1",
            "created_at": manifest["created_at"],
            "status": "pass",
            "manifest": str(manifest_path),
            "accepted_keyposes": str(accepted_dir),
            "frame_count": len(frames),
            "requirements": statuses,
            "manual_approved": args.manual_approved,
            "manual_note": args.manual_note,
            "freeze_stage": args.stage,
            "candidate_only": args.stage != "production",
        },
    )
    print(json.dumps({"status": "pass", "manifest": str(manifest_path), "accepted_keyposes": str(accepted_dir)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
