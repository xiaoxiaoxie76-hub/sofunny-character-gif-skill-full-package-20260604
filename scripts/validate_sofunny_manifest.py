#!/usr/bin/env python3
"""Validate SoFunny manifest provenance and admission vocabulary."""

from __future__ import annotations

import argparse
from pathlib import Path

from sofunny_anim.profiles import load_profile

from sofunny_anim.manifests import read_json, resolve_run_path


MANDATORY_ARTIFACTS = [
    "sequence_frames",
    "accepted_keyposes",
    "contact_sheet",
    "animation_gif",
    "animation_checker_gif",
    "animation_webp",
    "transparent_sheet",
    "jitter_diagnostics",
    "visual_stability_report",
    "style_lock_report",
    "visual_review",
    "body_tail_consistency_report",
    "identity_feature_lock_report",
    "component_integrity_report",
    "lively_motion_report",
    "action_validation_report",
    "provider_preflight_report",
    "keypose_freeze_manifest",
    "keypose_freeze_report",
    "keypose_contact_sheet",
    "keypose_checker_preview",
    "locked_gif_export_report",
]


def artifact_exists(run_dir: Path, value: str) -> bool:
    path = resolve_run_path(run_dir, value)
    if path is None:
        return False
    if value.endswith("/"):
        return path.is_dir() and any(path.glob("*.png"))
    return path.exists()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    profile = load_profile(args.profile)
    run_dir = Path(args.run_dir).expanduser().resolve()
    manifest = read_json(run_dir / "sofunny-run-manifest.json")
    failures: list[str] = []
    if manifest.get("schema_version") not in {"sofunny-character-gif.v1", "sofunny-character-gif.v2"}:
        failures.append("unsupported schema_version")
    if not manifest.get("character_name"):
        failures.append("character_name is required")
    if not manifest.get("action_name"):
        failures.append("action_name is required")
    reference = manifest.get("reference", {})
    if not reference.get("source"):
        failures.append("reference.source is required")
    elif (path := resolve_run_path(run_dir, reference.get("source"))) and not path.exists():
        failures.append(f"reference.source does not exist: {path}")
    generation = manifest.get("generation", {})
    if generation.get("admission_eligible") is not True:
        failures.append("generation.admission_eligible must be true for production admission")
    verdict = manifest.get("verdict", {})
    if verdict.get("production_approved") is not True:
        failures.append("verdict.production_approved must be true for production admission")
    artifacts = manifest.get("artifacts", {})
    for rel in MANDATORY_ARTIFACTS:
        artifact = artifacts.get(rel)
        if not artifact:
            failures.append(f"mandatory artifact key missing: {rel}")
        elif not artifact_exists(run_dir, artifact):
            failures.append(f"artifact missing: {rel} -> {artifact}")
    if failures:
        print("FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PASS: manifest validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
