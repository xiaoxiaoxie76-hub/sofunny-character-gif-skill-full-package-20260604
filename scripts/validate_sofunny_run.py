#!/usr/bin/env python3
"""Validate required SoFunny character GIF run artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sofunny_anim.freeze_gate import PASS_VALUES, production_enforcement_statuses
from sofunny_anim.profiles import load_profile


REQUIRED_ADMISSION_ARTIFACTS = [
    "contact_sheet.png",
    "animation.gif",
    "animation_checker.gif",
    "animation.webp",
    "sheet-transparent.png",
    "admission_report.md",
    "keypose_contact_sheet.png",
    "keypose_checker_preview.gif",
]

REQUIRED_ADMISSION_DIRS = [
    "sequence_frames",
    "accepted_keyposes",
]

REQUIRED_ADMISSION_REPORTS = [
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


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"missing required file: {path.name}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path.name}: {exc}") from exc


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def load_required_json(run_dir: Path, filename: str, failures: list[str]) -> dict:
    try:
        return load_json(run_dir / filename)
    except ValueError as exc:
        failures.append(str(exc))
        return {}


def validate_planning(run_dir: Path) -> list[str]:
    failures: list[str] = []
    manifest = load_json(run_dir / "sofunny-run-manifest.json")
    identity = load_json(run_dir / "identity-lock.json")
    motion = load_json(run_dir / "motion-contract.json")

    require(manifest.get("schema_version") == "sofunny-character-gif.v1", "manifest schema_version must be sofunny-character-gif.v1", failures)
    require(bool(manifest.get("character_name")), "manifest character_name is required", failures)
    require(bool(manifest.get("action_name")), "manifest action_name is required", failures)
    require(bool(manifest.get("reference", {}).get("source")), "manifest reference.source is required", failures)
    require(identity.get("canonical_reference", {}).get("source") == manifest.get("reference", {}).get("source"), "identity reference must match manifest reference", failures)
    require(bool(identity.get("forbidden_drift")), "identity forbidden_drift must not be empty", failures)
    require(motion.get("target_frames", 0) > 0, "motion target_frames must be positive", failures)
    require(bool(motion.get("phases")), "motion phases must not be empty", failures)
    require((run_dir / "generation_briefs" / "keyposes.md").exists(), "generation_briefs/keyposes.md is required", failures)
    require((run_dir / "generation_briefs" / "sequence.md").exists(), "generation_briefs/sequence.md is required", failures)
    return failures


def validate_admission(run_dir: Path, profile: dict) -> list[str]:
    failures = validate_planning(run_dir)
    manifest = load_required_json(run_dir, "sofunny-run-manifest.json", failures)
    reports = {filename: load_required_json(run_dir, filename, failures) for filename in REQUIRED_ADMISSION_REPORTS}
    style = reports["style_lock_report.json"]
    jitter = reports["jitter_diagnostics.json"]
    visual_stability = reports["visual_stability_report.json"]
    body_tail = reports["body_tail_consistency_report.json"]
    visual = reports["visual-review.json"]
    action_report = reports["action_validation_report.json"]
    identity_feature = reports["identity_feature_lock_report.json"]
    component_integrity = reports["component_integrity_report.json"]
    lively_motion = reports["lively_motion_report.json"]
    provider_preflight = reports["provider_preflight_report.json"]
    freeze_manifest = reports["keypose_freeze_manifest.json"]
    freeze_report = reports["keypose_freeze_report.json"]
    locked_export = reports["locked_gif_export_report.json"]
    enforcement_statuses = production_enforcement_statuses(run_dir)

    for artifact in REQUIRED_ADMISSION_ARTIFACTS:
        require((run_dir / artifact).exists(), f"{artifact} is required for admission", failures)

    for dirname in REQUIRED_ADMISSION_DIRS:
        frame_paths = sorted((run_dir / dirname).glob("*.png"))
        require(bool(frame_paths), f"{dirname}/ must contain PNG frames for admission", failures)

    sequence_frames = sorted((run_dir / "sequence_frames").glob("*.png"))
    accepted_keyposes = sorted((run_dir / "accepted_keyposes").glob("*.png"))
    require(bool(sequence_frames), "sequence_frames must contain PNG frames for admission", failures)
    require(bool(accepted_keyposes), "accepted_keyposes must contain frozen PNG frames for admission", failures)
    require(style.get("status") == "pass", "style_lock_report.status must be pass", failures)
    require(provider_preflight.get("status") == "pass", "provider_preflight_report.status must be pass", failures)
    require(freeze_manifest.get("schema_version") == "sofunny-keypose-freeze.v1", "keypose_freeze_manifest.schema_version must be sofunny-keypose-freeze.v1", failures)
    require(freeze_manifest.get("candidate_only") is not True, "candidate-only keypose freeze cannot be used for production admission", failures)
    if freeze_manifest.get("freeze_stage") is not None:
        require(freeze_manifest.get("freeze_stage") == "production", "keypose_freeze_manifest.freeze_stage must be production for admission", failures)
    require(freeze_report.get("status") == "pass", "keypose_freeze_report.status must be pass", failures)
    require(locked_export.get("status") == "pass", "locked_gif_export_report.status must be pass", failures)
    require(locked_export.get("candidate_only") is not True, "candidate-only locked export cannot be used for production admission", failures)
    if locked_export.get("export_stage") is not None:
        require(locked_export.get("export_stage") == "production", "locked_gif_export_report.export_stage must be production for admission", failures)
    require(locked_export.get("source_keyposes_unchanged") is True, "locked_gif_export_report.source_keyposes_unchanged must be true", failures)
    require(len(freeze_manifest.get("frames", [])) == len(accepted_keyposes), "keypose_freeze_manifest frame count must match accepted_keyposes PNG count", failures)
    if freeze_manifest.get("frame_count") is not None:
        require(freeze_manifest.get("frame_count") == len(accepted_keyposes), "keypose_freeze_manifest.frame_count must match accepted_keyposes PNG count", failures)
    freeze_requirements = freeze_manifest.get("requirements", {})
    for key, status in freeze_requirements.items():
        require(status in PASS_VALUES, f"keypose_freeze_manifest.requirements.{key} must be pass, got {status}", failures)
    require(freeze_manifest.get("manual_approved") is not True, "manual-approved keypose freeze cannot be used for production admission", failures)
    require(body_tail.get("status") == "pass", "body_tail_consistency_report.status must be pass", failures)
    allowed_visual_warnings = {
        "alpha area changes by more than threshold",
        "alpha area changes by more than 8%",
    }
    allowed_jitter_warnings = {
        "lower-body anchor center range exceeds threshold",
        "lower-body anchor center range exceeds 6px",
    }
    visual_warnings = visual_stability.get("warnings", [])
    visual_ok = visual_stability.get("status") == "pass" or (
        visual_stability.get("status") == "warn"
        and body_tail.get("status") == "pass"
        and set(visual_warnings).issubset(allowed_visual_warnings)
    )
    require(visual_ok, "visual_stability_report.status must be pass, or only alpha-area warn with body/tail pass", failures)
    jitter_warnings = jitter.get("warnings", [])
    jitter_ok = jitter.get("status") == "pass" or (
        jitter.get("status") == "warn"
        and visual_ok
        and body_tail.get("status") == "pass"
        and set(jitter_warnings).issubset(allowed_jitter_warnings)
    )
    require(jitter_ok, "jitter_diagnostics.status must be pass, or only lower-body action-anchor warn with visual/body stability pass", failures)
    require(visual.get("status") == "pass", "visual-review.status must be pass", failures)
    require(identity_feature.get("status") == "pass", "identity_feature_lock_report.status must be pass", failures)
    require(component_integrity.get("status") == "pass", "component_integrity_report.status must be pass", failures)
    require(lively_motion.get("status") == "pass", "lively_motion_report.status must be pass", failures)
    route = manifest.get("generation", {}).get("route")
    if str(route).lower() == "prop_action_component_route":
        prop_action_contact = load_required_json(run_dir, "prop_action_contact_report.json", failures)
        require(prop_action_contact.get("status") == "pass", "prop_action_contact_report.status must be pass", failures)
    require(manifest.get("generation", {}).get("admission_eligible") is True, "candidate route must be admission-eligible", failures)
    require(manifest.get("generation", {}).get("reference_used_for_generation") is True, "canonical reference must be used for generation before production admission", failures)
    require(manifest.get("verdict", {}).get("production_approved") is True, "manifest verdict.production_approved must be true for admission", failures)
    require(action_report.get("status") == "pass", "action_validation_report.status must be pass", failures)
    require(visual.get("contact_sheet_reviewed") is True, "visual-review must confirm contact sheet review", failures)
    require(visual.get("animation_reviewed") is True, "visual-review must confirm animation review", failures)
    require(not visual.get("required_fixes"), "visual-review.required_fixes must be empty for admission", failures)
    for name, status in enforcement_statuses.items():
        require(status in PASS_VALUES, f"{name} enforcement status must be pass for production admission, got {status}", failures)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--stage", choices=["planning", "admission"], default="planning")
    args = parser.parse_args()
    profile = load_profile(args.profile)

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.exists():
        print(f"FAIL: run dir does not exist: {run_dir}")
        return 2

    try:
        failures = validate_admission(run_dir, profile) if args.stage == "admission" else validate_planning(run_dir)
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 2

    if failures:
        print("FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(f"PASS: {args.stage} validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
