#!/usr/bin/env python3
"""Finalize a SoFunny candidate run with explicit visual and production verdicts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from sofunny_anim.profiles import load_profile

from sofunny_anim.freeze_gate import PASS_VALUES, production_enforcement_statuses
from sofunny_anim.manifests import read_json, write_json
from validate_sofunny_run import validate_admission


SMALL_JOG_PHASES = [
    {"name": "contact", "frames": [0, 0], "description": "front small-jog contact pose"},
    {"name": "down", "frames": [1, 1], "description": "compressed/down step"},
    {"name": "passing", "frames": [2, 2], "description": "leg passing through"},
    {"name": "up", "frames": [3, 3], "description": "lift/up phase"},
    {"name": "contact", "frames": [4, 4], "description": "opposite contact pose"},
    {"name": "recover", "frames": [5, 5], "description": "recover into loop"},
]

PRODUCTION_REQUIRED_FILES = [
    "contact_sheet.png",
    "animation.gif",
    "animation_checker.gif",
    "animation.webp",
    "sheet-transparent.png",
    "keypose_contact_sheet.png",
    "keypose_checker_preview.gif",
    "admission_report.md",
]

PRODUCTION_REQUIRED_DIRS = [
    "sequence_frames",
    "accepted_keyposes",
]

PRODUCTION_REQUIRED_REPORTS = [
    "style_lock_report.json",
    "jitter_diagnostics.json",
    "visual_stability_report.json",
    "body_tail_consistency_report.json",
    "visual-review.json",
    "action_validation_report.json",
    "identity_feature_lock_report.json",
    "component_integrity_report.json",
    "lively_motion_report.json",
    "provider_preflight_report.json",
    "keypose_freeze_manifest.json",
    "keypose_freeze_report.json",
    "locked_gif_export_report.json",
]

BLOCKING_STATUSES = {
    "missing",
    "manual_required",
    "manual_identity_review_required",
    "manual_action_review_required",
    "warn",
    "fail",
    "draft",
    "pending",
    "pending_manual_review",
    "blocked_by_candidate_route",
}

SMOKE_ROUTE_MARKERS = ("pipeline_smoke", "smoke", "fallback", "not_admission_eligible")


def write_generation_briefs(run_dir: Path, action: str, frames: int) -> None:
    brief_dir = run_dir / "generation_briefs"
    brief_dir.mkdir(parents=True, exist_ok=True)
    keyposes = brief_dir / "keyposes.md"
    sequence = brief_dir / "sequence.md"
    if not keyposes.exists():
        keyposes.write_text(
            f"# Keyposes\n\nAction: `{action}`\nFrames: {frames}\n\n"
            "Use the imported candidate sheet as the keypose source. Preserve character identity, "
            "then repair only failed frames or body parts.\n",
            encoding="utf-8",
        )
    if not sequence.exists():
        sequence.write_text(
            f"# Sequence\n\nAction: `{action}`\nFrames: {frames}\n\n"
            "Sequence frames are normalized from the imported candidate. Check contact sheet and "
            "checker GIF before approving admission.\n",
            encoding="utf-8",
        )


def status_of(payload: dict, default: str = "missing") -> str:
    return str(payload.get("status", default)).lower()


def read_required_report(run_dir: Path, filename: str, failures: list[str]) -> dict:
    try:
        payload = read_json(run_dir / filename)
    except FileNotFoundError:
        failures.append(f"missing required file: {filename}")
        return {}
    return payload


def production_approval_failures(run_dir: Path, candidate: dict, args: argparse.Namespace) -> list[str]:
    failures: list[str] = []
    previous_manifest = read_json(run_dir / "sofunny-run-manifest.json", {})
    _ = previous_manifest

    if args.required_fix:
        failures.append("--production-approved cannot be used while --required-fix is present")
    for label, value in {
        "style_status": args.style_status,
        "visual_status": args.visual_status,
        "identity_match": args.identity_match,
        "motion_status": args.motion_status,
        "export_status": args.export_status,
    }.items():
        if value != "pass":
            failures.append(f"{label} must be pass for production approval, got {value}")

    route = str(args.route or candidate.get("route") or "").lower()
    if candidate.get("admission_eligible") is not True:
        failures.append("candidate_manifest.admission_eligible must be true for production approval")
    if any(marker in route for marker in SMOKE_ROUTE_MARKERS):
        failures.append(f"candidate route is not production-eligible: {route or 'missing'}")

    for filename in PRODUCTION_REQUIRED_FILES:
        if not (run_dir / filename).exists():
            failures.append(f"missing required file: {filename}")
    for dirname in PRODUCTION_REQUIRED_DIRS:
        if not list((run_dir / dirname).glob("*.png")):
            failures.append(f"{dirname}/ must contain PNG frames for production approval")

    reports = {filename: read_required_report(run_dir, filename, failures) for filename in PRODUCTION_REQUIRED_REPORTS}
    if (run_dir / "part_map.json").exists():
        part_consistency = read_required_report(run_dir, "part_consistency_report.json", failures)
        part_status = status_of(part_consistency)
        if part_status in BLOCKING_STATUSES or part_status != "pass":
            failures.append(f"part_consistency_report.json.status must be pass for source-animation production approval, got {part_status}")
        component_integrity = read_required_report(run_dir, "component_integrity_report.json", failures)
        component_status = status_of(component_integrity)
        if component_status in BLOCKING_STATUSES or component_status != "pass":
            failures.append(f"component_integrity_report.json.status must be pass for source-animation production approval, got {component_status}")
        lively_motion = read_required_report(run_dir, "lively_motion_report.json", failures)
        lively_status = status_of(lively_motion)
        if lively_status in BLOCKING_STATUSES or lively_status != "pass":
            failures.append(f"lively_motion_report.json.status must be pass for source-animation production approval, got {lively_status}")
        route_report = read_json(run_dir / "source_route_selection_report.json", {}) or read_json(run_dir / "route_selection_report.json", {})
        if str(route_report.get("recommended_route", "")).lower() == "prop_action_component_route":
            prop_contact = read_required_report(run_dir, "prop_action_contact_report.json", failures)
            prop_status = status_of(prop_contact)
            if prop_status in BLOCKING_STATUSES or prop_status != "pass":
                failures.append(f"prop_action_contact_report.json.status must be pass for prop-action production approval, got {prop_status}")
    for filename in [
        "style_lock_report.json",
        "visual_stability_report.json",
        "body_tail_consistency_report.json",
        "visual-review.json",
        "action_validation_report.json",
        "identity_feature_lock_report.json",
        "component_integrity_report.json",
        "lively_motion_report.json",
        "provider_preflight_report.json",
        "keypose_freeze_report.json",
        "locked_gif_export_report.json",
    ]:
        status = status_of(reports.get(filename, {}))
        if status in BLOCKING_STATUSES or status != "pass":
            failures.append(f"{filename}.status must be pass for production approval, got {status}")

    jitter_status = status_of(reports.get("jitter_diagnostics.json", {}))
    if jitter_status in BLOCKING_STATUSES or jitter_status != "pass":
        failures.append(f"jitter_diagnostics.json.status must be pass for production approval, got {jitter_status}")

    visual_review = reports.get("visual-review.json", {})
    if visual_review.get("contact_sheet_reviewed") is not True:
        failures.append("visual-review.json must confirm contact_sheet_reviewed=true")
    if visual_review.get("animation_reviewed") is not True:
        failures.append("visual-review.json must confirm animation_reviewed=true")
    if visual_review.get("required_fixes"):
        failures.append("visual-review.json.required_fixes must be empty for production approval")

    freeze_manifest = reports.get("keypose_freeze_manifest.json", {})
    if freeze_manifest.get("schema_version") != "sofunny-keypose-freeze.v1":
        failures.append("keypose_freeze_manifest.json.schema_version must be sofunny-keypose-freeze.v1")
    if freeze_manifest.get("candidate_only") is True or freeze_manifest.get("freeze_stage") not in {"production", None}:
        failures.append("candidate-only keypose freeze cannot be used for production approval")
    if freeze_manifest.get("manual_approved") is True:
        failures.append("manual-approved keypose freeze cannot be used for production approval")
    freeze_requirements = freeze_manifest.get("requirements", {})
    for key, status in freeze_requirements.items():
        if status not in PASS_VALUES:
            failures.append(f"keypose_freeze_manifest.json.requirements.{key} must be pass, got {status}")

    locked_export = reports.get("locked_gif_export_report.json", {})
    if locked_export.get("candidate_only") is True or locked_export.get("export_stage") not in {"production", None}:
        failures.append("candidate-only locked GIF export cannot be used for production approval")
    if locked_export.get("source_keyposes_unchanged") is not True:
        failures.append("locked_gif_export_report.json.source_keyposes_unchanged must be true")

    for name, status in production_enforcement_statuses(run_dir).items():
        if status not in PASS_VALUES:
            failures.append(f"{name} enforcement status must be pass for production approval, got {status}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--character-name")
    parser.add_argument("--action")
    parser.add_argument("--frames", type=int)
    parser.add_argument("--canvas", default="384x384")
    parser.add_argument("--route")
    parser.add_argument("--style-status", choices=["pass", "warn", "fail"], required=True)
    parser.add_argument("--visual-status", choices=["pass", "warn", "fail"], required=True)
    parser.add_argument("--identity-match", choices=["pass", "warn", "fail"], required=True)
    parser.add_argument("--motion-status", choices=["pass", "warn", "fail"], required=True)
    parser.add_argument("--export-status", choices=["pass", "warn", "fail"], required=True)
    parser.add_argument("--production-approved", action="store_true")
    parser.add_argument("--reference-used-for-generation", action="store_true")
    parser.add_argument("--required-fix", action="append", default=[])
    parser.add_argument("--note", action="append", default=[])
    args = parser.parse_args()
    profile = load_profile(args.profile)

    run_dir = Path(args.run_dir).expanduser().resolve()
    candidate = read_json(run_dir / "candidate_manifest.json", {})
    jitter = read_json(run_dir / "jitter_diagnostics.json", {})
    visual_stability = read_json(run_dir / "visual_stability_report.json", {})
    action_report = read_json(run_dir / "action_validation_report.json", {})
    cleanup = read_json(run_dir / "component_cleanup_report.json", {})
    offset = read_json(run_dir / "offset_normalization_report.json", {})

    character = args.character_name or candidate.get("character_name") or "unknown_character"
    action = args.action or candidate.get("action") or "unknown_action"
    frames = args.frames or int(candidate.get("frames") or len(list((run_dir / "sequence_frames").glob("*.png"))))
    route = args.route or candidate.get("route") or "unknown_route"
    canvas_w, canvas_h = [int(part) for part in args.canvas.lower().split("x")]

    if args.production_approved:
        failures = production_approval_failures(run_dir, candidate, args)
        if failures:
            print("FAIL: production approval blocked")
            for failure in failures:
                print(f"- {failure}")
            return 1

    write_generation_briefs(run_dir, action, frames)

    manifest = {
        "schema_version": "sofunny-character-gif.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "character_name": character,
        "action_name": action,
        "reference": {
            "source_type": "local_file",
            "source": str(Path(args.reference).expanduser().resolve()),
        },
        "generation": {
            "route": route,
            "admission_eligible": bool(candidate.get("admission_eligible")),
            "candidate_sheet": candidate.get("candidate_sheet"),
            "reference_used_for_generation": args.reference_used_for_generation,
        },
        "artifacts": {
            "contact_sheet": "contact_sheet.png",
            "animation_gif": "animation.gif",
            "animation_checker_gif": "animation_checker.gif",
            "animation_webp": "animation.webp",
            "transparent_sheet": "sheet-transparent.png",
            "sequence_frames": "sequence_frames/",
            "accepted_keyposes": "accepted_keyposes/",
            "style_lock_report": "style_lock_report.json",
            "jitter_diagnostics": "jitter_diagnostics.json",
            "visual_stability_report": "visual_stability_report.json",
            "body_tail_consistency_report": "body_tail_consistency_report.json",
            "identity_feature_lock_report": "identity_feature_lock_report.json",
            "component_integrity_report": "component_integrity_report.json",
            "lively_motion_report": "lively_motion_report.json",
            "action_validation_report": "action_validation_report.json",
            "visual_review": "visual-review.json",
            "provider_preflight_report": "provider_preflight_report.json",
            "keypose_freeze_manifest": "keypose_freeze_manifest.json",
            "keypose_freeze_report": "keypose_freeze_report.json",
            "keypose_contact_sheet": "keypose_contact_sheet.png",
            "keypose_checker_preview": "keypose_checker_preview.gif",
            "locked_gif_export_report": "locked_gif_export_report.json",
            "part_map": "part_map.json",
            "identity_parts_contract": "identity_parts_contract.json",
            "movable_parts_contract": "movable_parts_contract.json",
            "action_component_plan": "action_component_plan.json",
            "part_consistency_report": "part_consistency_report.json",
        },
        "verdict": {
            "production_approved": bool(args.production_approved),
            "style_status": args.style_status,
            "visual_status": args.visual_status,
            "motion_status": args.motion_status,
            "export_status": args.export_status,
        },
    }
    write_json(run_dir / "sofunny-run-manifest.json", manifest)

    write_json(run_dir / "identity-lock.json", {
        "character_name": character,
        "canonical_reference": {
            "source_type": "local_file",
            "source": manifest["reference"]["source"],
            "used_for_generation": args.reference_used_for_generation,
        },
        "must_keep": {
            "face": ["same face shape", "same eye/glasses expression", "same mouth/nose read"],
            "body_shape": ["same compact chibi proportions"],
            "headwear_or_hair": ["same hair mass and part direction"],
            "tail": ["same tail size, placement, stripe rhythm"],
            "accessories": ["black suit", "blue tie", "glasses"],
            "palette": ["same warm tan fur", "same dark suit"],
            "line_style": ["same SoFunny clean dark outline"],
            "proportions": ["head/body balance must remain close to canonical"],
        },
        "forbidden_drift": [
            "changed face",
            "changed body silhouette",
            "missing accessory",
            "unstable tail",
            "wrong palette",
            "fake transparency",
            "checkerboard artifact",
            "detached source-frame residue",
        ],
        "review_status": args.identity_match,
    })

    phases = SMALL_JOG_PHASES if action == "small_jog_front" else [
        {"name": "action_phase", "frames": [0, max(0, frames - 1)], "description": "user-specified action"}
    ]
    write_json(run_dir / "motion-contract.json", {
        "action_name": action,
        "target_frames": frames,
        "canvas": {"width": canvas_w, "height": canvas_h, "transparent": True},
        "phases": phases,
        "anchor_rules": {
            "fixed_ground_contact": True,
            "max_bbox_bottom_range_px": 1,
            "max_lower_body_anchor_x_range_px": 6,
            "center_x_rule": "small coherent movement only",
        },
        "review_status": args.motion_status,
    })

    style_findings = []
    if args.style_status != "pass":
        style_findings = args.required_fix or ["identity/style lock is not approved"]
    write_json(run_dir / "style_lock_report.json", {
        "status": args.style_status,
        "identity_match": args.identity_match,
        "drift_findings": style_findings,
        "notes": args.note,
    })

    write_json(run_dir / "visual-review.json", {
        "status": args.visual_status,
        "contact_sheet_reviewed": True,
        "animation_reviewed": True,
        "identity": args.identity_match,
        "motion": args.motion_status,
        "export_quality": args.export_status,
        "required_fixes": args.required_fix,
        "notes": args.note,
    })

    report = [
        "# SoFunny Admission Report",
        "",
        f"- Character: `{character}`",
        f"- Action: `{action}`",
        f"- Route: `{route}`",
        f"- Production approved: `{str(bool(args.production_approved)).lower()}`",
        f"- Style status: `{args.style_status}`",
        f"- Motion status: `{args.motion_status}`",
        f"- Export status: `{args.export_status}`",
        f"- Visual status: `{args.visual_status}`",
        f"- Action validation: `{action_report.get('status', 'missing')}`",
        f"- Jitter validation: `{jitter.get('status', 'missing')}`",
        f"- Visual stability: `{visual_stability.get('status', 'missing')}`",
        f"- Offset validation: `{offset.get('status', 'missing')}`",
        f"- Component cleanup: `{cleanup.get('status', 'missing')}`",
        "",
        "## Required Fixes",
        "",
    ]
    if args.required_fix:
        report.extend(f"- {fix}" for fix in args.required_fix)
    else:
        report.append("- none")
    if args.note:
        report.extend(["", "## Notes", ""])
        report.extend(f"- {note}" for note in args.note)
    (run_dir / "admission_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    if args.production_approved:
        failures = validate_admission(run_dir, profile)
        if failures:
            manifest["verdict"]["production_approved"] = False
            write_json(run_dir / "sofunny-run-manifest.json", manifest)
            print("FAIL: strict admission validation blocked production approval")
            for failure in failures:
                print(f"- {failure}")
            return 1

    print(str(run_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
