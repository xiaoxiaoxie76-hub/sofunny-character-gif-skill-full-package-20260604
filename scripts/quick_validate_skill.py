#!/usr/bin/env python3
"""Validate the local SoFunny skill structure."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "SKILL.md",
    "agents/openai.yaml",
    "profiles/sofunny.json",
    "profiles/sofunny-lively-motion.json",
    "profiles/default-character-gif.json",
    "regression_cases/pass/case.json",
    "regression_cases/identity_drift_fail/case.json",
    "regression_cases/manual_required_fail/case.json",
    "regression_cases/smoke_fail/case.json",
    "regression_cases/missing_visual_review_fail/case.json",
    "references/profile-contract.md",
    "references/contracts.md",
    "references/provider-routing.md",
    "references/route-adapter-registry.md",
    "references/ipadapter-local-repair-route.md",
    "references/animatex-provider-route.md",
    "references/external-adapter-license-notes.md",
    "references/provider-output-contract.md",
    "references/action-contract-schema.md",
    "references/external-pose-animation-adapters.md",
    "references/pose-only-guide-contract.md",
    "references/source-animation-route.md",
    "references/source-animation-route-matrix.md",
    "references/tooncrafter-interpolation-route.md",
    "references/identity-parts-contract.md",
    "references/movable-parts-contract.md",
    "references/action-component-plan.md",
    "references/generation-attempt-budget.md",
    "references/keypose-freeze-gate.md",
    "references/failure-routing.md",
    "references/gif-export-contract.md",
    "references/script-runbook.md",
    "references/admission-gates.md",
    "scripts/preflight_provider_output.py",
    "scripts/audit_admission_enforcement.py",
    "scripts/run_regression_suite.py",
    "scripts/select_source_animation_route.py",
    "scripts/select_route_adapter.py",
    "scripts/retry_tax_report.py",
    "scripts/build_interpolation_pairs.py",
    "scripts/create_tooncrafter_packet.py",
    "scripts/import_tooncrafter_segment.py",
    "scripts/audit_interpolated_segment.py",
    "scripts/create_ipadapter_part_repair_packet.py",
    "scripts/import_ipadapter_part_repair.py",
    "scripts/create_animatex_packet.py",
    "scripts/import_animatex_video_frames.py",
    "scripts/import_video_provider_frames.py",
    "scripts/audit_video_provider_frames.py",
    "scripts/build_part_masks.py",
    "scripts/validate_part_map.py",
    "scripts/create_action_component_plan.py",
    "scripts/generate_component_keyposes.py",
    "scripts/audit_part_consistency.py",
    "scripts/create_local_part_repair_packet.py",
    "scripts/freeze_keyposes.py",
    "scripts/make_pose_only_guides.py",
    "scripts/load_profile.py",
    "scripts/validate_profile.py",
    "scripts/score_identity_consistency.py",
    "scripts/classify_failure_reason.py",
    "scripts/export_locked_gif.py",
    "scripts/init_sofunny_run.py",
    "scripts/import_candidate_sheet.py",
    "scripts/measure_character_identity.py",
    "scripts/create_provider_brief.py",
    "scripts/create_pose_adapter_packet.py",
    "scripts/audit_action_semantics.py",
    "scripts/generate_reference_locked_bow.py",
    "scripts/run_sofunny_oneshot.py",
    "scripts/normalize_candidate_sheet.py",
    "scripts/export_sofunny_previews.py",
    "scripts/audit_sofunny_motion.py",
    "scripts/audit_visual_stability.py",
    "scripts/audit_body_tail_consistency.py",
    "scripts/audit_identity_feature_lock.py",
    "scripts/validate_action_contract.py",
    "scripts/validate_sofunny_run.py",
    "scripts/finalize_sofunny_candidate.py",
]

REQUIRED_SKILL_TERMS = [
    "identity lock -> lively motion -> export/admission QA",
    "references/contracts.md",
    "references/profile-contract.md",
    "references/provider-routing.md",
    "references/route-adapter-registry.md",
    "references/provider-output-contract.md",
    "references/action-contract-schema.md",
    "references/external-pose-animation-adapters.md",
    "references/pose-only-guide-contract.md",
    "references/source-animation-route.md",
    "references/source-animation-route-matrix.md",
    "references/route-adapter-registry.md",
    "references/ipadapter-local-repair-route.md",
    "references/animatex-provider-route.md",
    "references/external-adapter-license-notes.md",
    "references/tooncrafter-interpolation-route.md",
    "references/identity-parts-contract.md",
    "references/movable-parts-contract.md",
    "references/action-component-plan.md",
    "references/generation-attempt-budget.md",
    "references/keypose-freeze-gate.md",
    "references/failure-routing.md",
    "references/gif-export-contract.md",
    "references/script-runbook.md",
    "references/admission-gates.md",
    "production_approved: true",
    "keypose_freeze_manifest.json",
    "provider_preflight_report.json",
    "locked_gif_export_report.json",
    "source animation",
    "generation-attempt-budget.md",
    "source-animation-route-matrix.md",
    "route-adapter-registry.md",
    "ipadapter-local-repair-route.md",
    "animatex-provider-route.md",
    "external-adapter-license-notes.md",
    "tooncrafter-interpolation-route.md",
    "select_source_animation_route.py",
    "retry_tax_report.py",
    "part_map.json",
    "part_consistency_report.json",
    "--profile",
]


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def main() -> int:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).exists()]
    if missing:
        fail("missing required files: " + ", ".join(missing))

    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    if not skill.startswith("---\n"):
        fail("SKILL.md missing YAML frontmatter")

    match = re.match(r"---\n(.*?)\n---\n", skill, flags=re.DOTALL)
    if not match:
        fail("SKILL.md frontmatter is not closed")

    frontmatter = match.group(1)
    if "name: sofunny-character-gif" not in frontmatter:
        fail("frontmatter name is missing or wrong")
    if "description:" not in frontmatter:
        fail("frontmatter description is missing")

    line_count = len(skill.splitlines())
    if line_count > 240:
        fail(f"SKILL.md is too long for trigger-time instructions: {line_count} lines")

    missing_terms = [term for term in REQUIRED_SKILL_TERMS if term not in skill]
    if missing_terms:
        fail("SKILL.md missing required terms: " + ", ".join(missing_terms))

    for ref in (
        "contracts.md",
        "profile-contract.md",
        "route-adapter-registry.md",
        "ipadapter-local-repair-route.md",
        "animatex-provider-route.md",
        "external-adapter-license-notes.md",
        "script-runbook.md",
        "admission-gates.md",
        "keypose-freeze-gate.md",
        "provider-output-contract.md",
        "pose-only-guide-contract.md",
        "source-animation-route.md",
        "source-animation-route-matrix.md",
        "tooncrafter-interpolation-route.md",
        "identity-parts-contract.md",
        "movable-parts-contract.md",
        "action-component-plan.md",
        "generation-attempt-budget.md",
        "failure-routing.md",
        "gif-export-contract.md",
    ):
        text = (ROOT / "references" / ref).read_text(encoding="utf-8")
        if len(text.splitlines()) < 40:
            fail(f"references/{ref} looks too thin")
        if len(text.splitlines()) > 100 and "## Contents" not in text:
            fail(f"references/{ref} is long and missing a contents section")

    print("PASS: SoFunny skill structure is valid")
    print(f"SKILL.md lines: {line_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
