#!/usr/bin/env python3
"""Audit whether production admission scripts enforce the documented gates."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"

DOC_PATHS = {
    "SKILL.md": ROOT / "SKILL.md",
    "references/admission-gates.md": ROOT / "references" / "admission-gates.md",
    "references/keypose-freeze-gate.md": ROOT / "references" / "keypose-freeze-gate.md",
    "references/gif-export-contract.md": ROOT / "references" / "gif-export-contract.md",
}

TARGET_SCRIPTS = {
    "finalize_sofunny_candidate.py": SCRIPTS_DIR / "finalize_sofunny_candidate.py",
    "validate_sofunny_manifest.py": SCRIPTS_DIR / "validate_sofunny_manifest.py",
    "validate_sofunny_run.py": SCRIPTS_DIR / "validate_sofunny_run.py",
}

PASS_ONLY_REPORTS = {
    "style_lock_report.json",
    "jitter_diagnostics.json",
    "visual_stability_report.json",
    "body_tail_consistency_report.json",
    "identity_feature_lock_report.json",
    "component_integrity_report.json",
    "lively_motion_report.json",
    "prop_action_contact_report.json",
    "action_validation_report.json",
    "visual-review.json",
    "provider_preflight_report.json",
    "keypose_freeze_report.json",
    "locked_gif_export_report.json",
}

NONPASS_BLOCK_VALUES = {"manual_required", "manual_identity_review_required", "manual_action_review_required", "warn", "missing"}
ALLOWED_DIR_ARTIFACTS = {"accepted_keyposes/", "sequence_frames/"}
EXCLUDED_FILE_ARTIFACTS = {
    "000.png",
    "admission-gates.md",
    "gif-export-contract.md",
    "keypose-freeze-gate.md",
    "script-runbook.md",
}


@dataclass
class Finding:
    severity: str
    title: str
    evidence: list[str]
    recommendation: str


@dataclass
class NegativeTestResult:
    name: str
    expected: str
    passed: bool
    returncode: int
    production_approved_written: bool
    evidence: list[str]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def extract_section(text: str, heading: str) -> str:
    pattern = re.compile(rf"^## {re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"^##\s+", text[start:], flags=re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end]


def extract_artifacts(text: str) -> set[str]:
    artifacts = set(re.findall(r"\b[\w-]+\.(?:json|png|gif|webp|md)\b", text))
    artifacts = {artifact for artifact in artifacts if artifact not in EXCLUDED_FILE_ARTIFACTS}
    artifacts = {
        artifact for artifact in artifacts
        if not artifact.endswith(".md") or artifact == "admission_report.md"
    }
    artifacts.update(
        artifact for artifact in re.findall(r"\b[\w-]+/\b", text)
        if artifact in ALLOWED_DIR_ARTIFACTS
    )
    return artifacts


def documented_required_artifacts() -> dict[str, list[str]]:
    skill = read_text(DOC_PATHS["SKILL.md"])
    admission = read_text(DOC_PATHS["references/admission-gates.md"])
    freeze = read_text(DOC_PATHS["references/keypose-freeze-gate.md"])
    gif_export = read_text(DOC_PATHS["references/gif-export-contract.md"])

    by_source = {
        "SKILL.md:Admission Boundary": sorted(extract_artifacts(extract_section(skill, "Admission Boundary"))),
        "admission-gates.md:Required Visual Artifacts": sorted(extract_artifacts(extract_section(admission, "Required Visual Artifacts"))),
        "admission-gates.md:Keypose Freeze Requirement": sorted(extract_artifacts(extract_section(admission, "Keypose Freeze Requirement"))),
        "admission-gates.md:Blocked Acceptance": sorted(extract_artifacts(extract_section(admission, "Blocked Acceptance"))),
        "keypose-freeze-gate.md:Freeze Requirements": sorted(extract_artifacts(extract_section(freeze, "Freeze Requirements"))),
        "keypose-freeze-gate.md:Manifest Contract": sorted(extract_artifacts(extract_section(freeze, "Manifest Contract"))),
        "gif-export-contract.md:Locked Source": sorted(extract_artifacts(extract_section(gif_export, "Locked Source"))),
        "gif-export-contract.md:Required Export Report": sorted(extract_artifacts(extract_section(gif_export, "Required Export Report"))),
    }
    return by_source


def union_artifacts(by_source: dict[str, list[str]]) -> list[str]:
    items: set[str] = set()
    for values in by_source.values():
        items.update(values)
    return sorted(items)


def script_reads(source: str, artifact: str) -> bool:
    normalized = artifact.rstrip("/")
    escaped = re.escape(artifact)
    read_patterns = [
        rf"(?:read_json|load_json)\([^)]*['\"]{escaped}['\"]",
        rf"Path\([^)]*['\"]{escaped}['\"]\)\.read_text",
    ]
    if any(re.search(pattern, source, flags=re.DOTALL) for pattern in read_patterns):
        return True
    if artifact in source or normalized in source:
        return any(token in source for token in ("read_required_report", "load_required_json", ".exists()", ".glob("))
    return False


def script_mentions(source: str, artifact: str) -> bool:
    return artifact in source or artifact.rstrip("/") in source


def has_failure_path(source: str) -> bool:
    return any(token in source for token in ("return 1", "return 2", "parser.error", "sys.exit"))


def source_line_numbers(source: str, needle: str) -> list[int]:
    return [index for index, line in enumerate(source.splitlines(), start=1) if needle in line]


def analyze_static_enforcement(required_artifacts: list[str]) -> tuple[dict[str, Any], list[Finding]]:
    sources = {name: read_text(path) for name, path in TARGET_SCRIPTS.items()}
    findings: list[Finding] = []

    finalize = sources["finalize_sofunny_candidate.py"]
    validate_run = sources["validate_sofunny_run.py"]
    validate_manifest = sources["validate_sofunny_manifest.py"]

    finalize_reads = sorted(artifact for artifact in required_artifacts if script_reads(finalize, artifact))
    finalize_mentions = sorted(artifact for artifact in required_artifacts if script_mentions(finalize, artifact))
    validate_run_mentions = sorted(artifact for artifact in required_artifacts if script_mentions(validate_run, artifact))
    validate_manifest_mentions = sorted(artifact for artifact in required_artifacts if script_mentions(validate_manifest, artifact))

    approval_lines = source_line_numbers(finalize, '"production_approved": bool(args.production_approved)')
    finalizer_has_strict_precheck = "production_approval_failures" in finalize and "if args.production_approved:" in finalize
    finalizer_has_strict_postcheck = "validate_admission(run_dir, profile)" in finalize
    if approval_lines and not (finalizer_has_strict_precheck and finalizer_has_strict_postcheck):
        findings.append(Finding(
            severity="P0",
            title="finalize_sofunny_candidate.py can write production_approved from a CLI flag",
            evidence=[
                f"finalize_sofunny_candidate.py:{line} writes production_approved from args.production_approved"
                for line in approval_lines
            ] + [
                "No strict admission validator is called before or after writing sofunny-run-manifest.json.",
            ],
            recommendation="Make finalization call the strict admission validator before writing production_approved:true, and fail closed on missing, warn, or manual_required evidence.",
        ))

    if not has_failure_path(finalize):
        findings.append(Finding(
            severity="P0",
            title="finalize_sofunny_candidate.py has no production-blocking failure path",
            evidence=["The script returns 0 unconditionally after writing approval-facing artifacts."],
            recommendation="Return non-zero before writing approval when any required final artifact is missing or not pass.",
        ))

    missing_finalizer_reads = [
        artifact for artifact in required_artifacts
        if artifact in PASS_ONLY_REPORTS or artifact in {
            "sofunny-run-manifest.json",
            "keypose_freeze_manifest.json",
            "accepted_keyposes/",
            "locked_gif_export_report.json",
            "animation_checker.gif",
        }
        if artifact not in finalize_reads
    ]
    if missing_finalizer_reads:
        findings.append(Finding(
            severity="P0",
            title="finalize_sofunny_candidate.py does not read all required production evidence",
            evidence=[f"Missing finalizer read/enforcement for: {', '.join(missing_finalizer_reads)}"],
            recommendation="Load and validate every required final report/artifact before allowing production approval.",
        ))

    if 'get("admission_eligible") is not False' in validate_run:
        findings.append(Finding(
            severity="P1",
            title="validate_sofunny_run.py allows missing admission_eligible",
            evidence=["validate_sofunny_run.py accepts generation.admission_eligible values that are not explicitly false, so missing/None can pass."],
            recommendation="Require generation.admission_eligible is True for production admission.",
        ))

    required_gate_artifacts = {
        "provider_preflight_report.json",
        "keypose_freeze_manifest.json",
        "keypose_freeze_report.json",
        "accepted_keyposes/",
        "keypose_contact_sheet.png",
        "keypose_checker_preview.gif",
        "locked_gif_export_report.json",
        "animation_checker.gif",
    }
    missing_validate_run = sorted(artifact for artifact in required_gate_artifacts if artifact not in validate_run_mentions)
    if missing_validate_run:
        findings.append(Finding(
            severity="P0",
            title="validate_sofunny_run.py does not enforce required freeze/export artifacts",
            evidence=[f"Missing validate_sofunny_run.py checks for: {', '.join(missing_validate_run)}"],
            recommendation="Admission validation must require provider preflight, freeze manifest/report, accepted keyposes, keypose previews, checker GIF, and locked export report.",
        ))

    if "if artifact and" in validate_manifest:
        findings.append(Finding(
            severity="P0",
            title="validate_sofunny_manifest.py treats required artifact declarations as optional",
            evidence=["validate_sofunny_manifest.py only checks an artifact path if the manifest declared that key."],
            recommendation="Require mandatory production artifact keys, then verify each declared path exists.",
        ))

    if "manual_required" not in finalize and "manual_identity_review_required" not in finalize:
        findings.append(Finding(
            severity="P0",
            title="finalize_sofunny_candidate.py does not block manual_required review states",
            evidence=["No manual_required/manual_identity_review_required/manual_action_review_required blocking logic is present in finalizer source."],
            recommendation="Treat manual_required, warn, and missing report statuses as production blockers.",
        ))

    if "warn" in finalize and "--production-approved" in finalize and "required_fix" in finalize and 'value != "pass"' not in finalize:
        findings.append(Finding(
            severity="P1",
            title="finalize_sofunny_candidate.py accepts warn statuses as CLI values",
            evidence=["CLI choices include warn for style, visual, motion, and export status; finalizer does not independently block production approval when warn is supplied."],
            recommendation="Allow warn only for non-production reports, or reject --production-approved whenever any final status is warn.",
        ))

    static = {
        "scripts": {
            "finalize_sofunny_candidate.py": {
                "has_failure_path": has_failure_path(finalize),
                "reads_required_artifacts": finalize_reads,
                "mentions_required_artifacts": finalize_mentions,
                "production_approved_cli_flag_lines": approval_lines,
            },
            "validate_sofunny_run.py": {
                "mentions_required_artifacts": validate_run_mentions,
                "missing_required_gate_artifacts": missing_validate_run,
                "uses_non_strict_admission_eligible_check": 'get("admission_eligible") is not False' in validate_run,
            },
            "validate_sofunny_manifest.py": {
                "mentions_required_artifacts": validate_manifest_mentions,
                "optional_artifact_declaration_check": "if artifact and" in validate_manifest,
            },
        }
    }
    return static, findings


def tiny_png_bytes() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00"
        b"\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def write_base_fixture(
    run_dir: Path,
    *,
    identity_status: str = "pass",
    smoke: bool = False,
    omit_visual_review: bool = False,
    omit_route_selection: bool = False,
    retry_pivot_required: bool = False,
    omit_part_map: bool = False,
    part_consistency_status: str = "pass",
    omit_lively_motion: bool = False,
    component_integrity_status: str = "pass",
    adapter: str = "",
    omit_adapter_audit: bool = False,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "sequence_frames").mkdir()
    (run_dir / "accepted_keyposes").mkdir()
    png = tiny_png_bytes()
    for rel in [
        "reference.png",
        "contact_sheet.png",
        "animation.gif",
        "animation_checker.gif",
        "animation.webp",
        "sheet-transparent.png",
        "keypose_contact_sheet.png",
        "keypose_checker_preview.gif",
        "identity_feature_comparison.png",
        "body_tail_debug_sheet.png",
        "sequence_frames/000.png",
        "accepted_keyposes/000.png",
    ]:
        (run_dir / rel).write_bytes(png)
    (run_dir / "admission_report.md").write_text("# admission\n", encoding="utf-8")

    candidate = {
        "character_name": "audit_char",
        "action": "small_jog_front",
        "frames": 1,
        "route": "pipeline_smoke_candidate" if smoke else "component_pseudo_rig_action_component_plan",
        "admission_eligible": False if smoke else True,
        "candidate_sheet": str(run_dir / "contact_sheet.png"),
    }
    write_json(run_dir / "candidate_manifest.json", candidate)
    if not omit_route_selection:
        route_report = {
            "schema_version": "sofunny-route-selection-report.v1",
            "status": "pass",
            "action": "small_jog_front",
            "run_type": "smoke" if smoke else "production",
            "recommended_route": "full_frame_redraw" if smoke else "component_pseudo_rig_action_component_plan",
            "route_reason": "fixture route selection",
            "candidate_only": False,
            "de_identification_required": False,
            "reimport_required": False,
            "freeze_required": True,
            "admission_required": True,
            "blockers": [],
            "warnings": [],
        }
        write_json(run_dir / "source_route_selection_report.json", route_report)
        write_json(run_dir / "route_selection_report.json", route_report)
    write_json(run_dir / "retry_tax_report.json", {
        "schema_version": "sofunny-retry-tax-report.v1",
        "status": "pivot_required" if retry_pivot_required else "pass",
        "pivot_required": retry_pivot_required,
        "prompt_polishing_allowed": not retry_pivot_required,
        "blockers": ["same route reached budget: full_frame_redraw count=2"] if retry_pivot_required else [],
        "warnings": [],
    })
    if not smoke and not omit_part_map:
        write_json(run_dir / "part_map.json", {"schema_version": "sofunny-part-map.v1", "parts": [{"name": "body"}]})
        write_json(run_dir / "identity_parts_contract.json", {"schema_version": "sofunny-identity-parts.v1", "fixed_parts": ["face", "body"]})
        write_json(run_dir / "movable_parts_contract.json", {"schema_version": "sofunny-movable-parts.v1", "movable_parts": ["leg_l", "leg_r", "tail"]})
        write_json(run_dir / "action_component_plan.json", {"schema_version": "sofunny-action-component-plan.v1", "action": "small_jog_front", "phases": ["contact"]})
    if not smoke:
        write_json(run_dir / "part_consistency_report.json", {"status": part_consistency_status, "warnings": []})
        write_json(run_dir / "component_integrity_report.json", {"status": component_integrity_status, "warnings": [], "blocks_keypose_freeze": component_integrity_status != "pass"})
        if not omit_lively_motion:
            write_json(run_dir / "lively_motion_report.json", {"status": "pass", "warnings": [], "blocks_keypose_freeze": False})
    if adapter:
        write_json(run_dir / "route_adapter_report.json", {
            "schema_version": "sofunny-route-adapter-report.v1",
            "status": "pass",
            "adapter": adapter,
            "route": "interpolation_route" if adapter == "tooncrafter" else "external_animation_provider_candidate",
            "candidate_only": True,
            "reimport_through_gates": True,
            "blockers": [],
            "warnings": ["adapter output is candidate-only and cannot set production_approved"],
        })
    if adapter == "tooncrafter":
        write_json(run_dir / "tooncrafter_import_report.json", {"status": "pass", "adapter": "tooncrafter", "candidate_only": True})
        if not omit_adapter_audit:
            write_json(run_dir / "interpolated_segment_audit.json", {"status": "pass", "adapter": "tooncrafter", "candidate_only": True})
    if adapter == "animate_x_wan":
        write_json(run_dir / "animatex_import_report.json", {"status": "pass", "adapter": "animate_x_wan", "candidate_only": True})
        if not omit_adapter_audit:
            write_json(run_dir / "video_provider_frame_audit.json", {"status": "pass", "adapter": "animate_x_wan", "candidate_only": True})
    write_json(run_dir / "provider_preflight_report.json", {"status": "pass", "failures": []})
    write_json(run_dir / "jitter_diagnostics.json", {"status": "pass", "warnings": []})
    write_json(run_dir / "visual_stability_report.json", {"status": "pass", "warnings": []})
    write_json(run_dir / "body_tail_consistency_report.json", {"status": "pass", "warnings": []})
    write_json(run_dir / "identity_feature_lock_report.json", {"status": identity_status, "warnings": []})
    write_json(run_dir / "action_validation_report.json", {"status": "pass", "warnings": []})
    write_json(run_dir / "keypose_freeze_manifest.json", {
        "schema_version": "sofunny-keypose-freeze.v1",
        "accepted_keyposes": str(run_dir / "accepted_keyposes"),
        "frame_count": 1,
        "frames": [{"index": 0, "file": "accepted_keyposes/000.png", "sha256": "not-used-by-finalizer", "phase": "contact"}],
        "requirements": {
            "provider_preflight": "pass",
            "identity": identity_status,
            "action": "pass",
            "body_tail": "pass",
            "jitter": "pass",
            "visual_stability": "pass",
            "route_selection": "pass" if not omit_route_selection else "missing",
            "retry_tax": "pivot_required" if retry_pivot_required else "pass",
            "part_map": "missing" if omit_part_map else ("pass" if not smoke else "not_required"),
            "part_consistency": part_consistency_status if not smoke else "not_required",
            "component_integrity": component_integrity_status if not smoke else "not_required",
            "lively_motion": "missing" if omit_lively_motion else ("pass" if not smoke else "not_required"),
        },
    })
    write_json(run_dir / "keypose_freeze_report.json", {"status": "pass"})
    write_json(run_dir / "locked_gif_export_report.json", {
        "status": "pass",
        "source_keyposes_unchanged": True,
        "outputs": {"animation_checker_gif": str(run_dir / "animation_checker.gif")},
    })
    write_json(run_dir / "style_lock_report.json", {"status": "pass", "identity_match": "pass"})
    if not omit_visual_review:
        write_json(run_dir / "visual-review.json", {
            "status": "pass",
            "contact_sheet_reviewed": True,
            "animation_reviewed": True,
            "identity": "pass",
            "motion": "pass",
            "export_quality": "pass",
            "required_fixes": [],
        })
    (run_dir / "generation_briefs").mkdir()
    (run_dir / "generation_briefs" / "keyposes.md").write_text("# keyposes\n", encoding="utf-8")
    (run_dir / "generation_briefs" / "sequence.md").write_text("# sequence\n", encoding="utf-8")


def run_finalize(run_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "finalize_sofunny_candidate.py"),
            "--run-dir",
            str(run_dir),
            "--reference",
            str(run_dir / "reference.png"),
            "--character-name",
            "audit_char",
            "--action",
            "small_jog_front",
            "--frames",
            "1",
            "--route",
            "pipeline_smoke_candidate" if "smoke" in run_dir.name else "component_pseudo_rig_action_component_plan",
            "--style-status",
            "pass",
            "--visual-status",
            "pass",
            "--identity-match",
            "pass",
            "--motion-status",
            "pass",
            "--export-status",
            "pass",
            "--production-approved",
            "--reference-used-for-generation",
        ],
        text=True,
        capture_output=True,
    )


def manifest_production_approved(run_dir: Path) -> bool:
    try:
        manifest = json.loads((run_dir / "sofunny-run-manifest.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return False
    return manifest.get("verdict", {}).get("production_approved") is True


def run_negative_tests(keep_temp: bool = False) -> tuple[list[NegativeTestResult], str | None]:
    temp_dir_obj = tempfile.TemporaryDirectory(prefix="sofunny_admission_enforcement_")
    temp_root = Path(temp_dir_obj.name)
    results: list[NegativeTestResult] = []
    cases = [
        {
            "name": "missing visual-review.json blocks finalization",
            "dirname": "missing_visual_review",
            "fixture": {"omit_visual_review": True},
            "expected": "finalize exits non-zero and does not write production_approved:true",
        },
        {
            "name": "manual_required identity_feature_lock_report blocks finalization",
            "dirname": "manual_required_identity",
            "fixture": {"identity_status": "manual_required"},
            "expected": "finalize exits non-zero and does not write production_approved:true",
        },
        {
            "name": "smoke run blocks production approval",
            "dirname": "pipeline_smoke_run",
            "fixture": {"smoke": True},
            "expected": "finalize exits non-zero and does not write production_approved:true",
        },
    ]
    for case in cases:
        run_dir = temp_root / case["dirname"]
        write_base_fixture(run_dir, **case["fixture"])
        result = run_finalize(run_dir)
        approved = manifest_production_approved(run_dir)
        passed = result.returncode != 0 and not approved
        evidence = [
            f"returncode={result.returncode}",
            f"production_approved_written={approved}",
        ]
        if result.stdout.strip():
            evidence.append("stdout=" + result.stdout.strip().splitlines()[-1])
        if result.stderr.strip():
            evidence.append("stderr=" + result.stderr.strip().splitlines()[-1])
        results.append(NegativeTestResult(
            name=case["name"],
            expected=case["expected"],
            passed=passed,
            returncode=result.returncode,
            production_approved_written=approved,
            evidence=evidence,
        ))

    if keep_temp:
        kept = str(temp_root)
        temp_dir_obj.cleanup = lambda: None  # type: ignore[method-assign]
        return results, kept
    temp_dir_obj.cleanup()
    return results, None


def findings_from_negative_tests(results: list[NegativeTestResult]) -> list[Finding]:
    findings: list[Finding] = []
    for result in results:
        if result.passed:
            continue
        findings.append(Finding(
            severity="P0",
            title=f"Negative test failed: {result.name}",
            evidence=result.evidence,
            recommendation="Patch finalization so this scenario exits non-zero and cannot write production_approved:true.",
        ))
    return findings


def severity_status(findings: list[Finding]) -> str:
    severities = {finding.severity for finding in findings}
    if "P0" in severities:
        return "fail"
    if "P1" in severities:
        return "warn"
    return "pass"


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Admission Enforcement Audit",
        "",
        f"Generated: {payload['generated_at']}",
        f"Status: `{payload['status']}`",
        "",
        "## Required Final Artifacts",
        "",
    ]
    for source, artifacts in payload["required_artifacts"]["by_source"].items():
        lines.append(f"### {source}")
        lines.append("")
        for artifact in artifacts:
            lines.append(f"- `{artifact}`")
        if not artifacts:
            lines.append("- none parsed")
        lines.append("")

    lines.extend([
        "## Findings",
        "",
    ])
    if not payload["findings"]:
        lines.append("No enforcement mismatches found.")
    for finding in payload["findings"]:
        lines.extend([
            f"### {finding['severity']}: {finding['title']}",
            "",
            "Evidence:",
            "",
        ])
        for item in finding["evidence"]:
            lines.append(f"- {item}")
        lines.extend([
            "",
            "Recommendation:",
            "",
            finding["recommendation"],
            "",
        ])

    lines.extend([
        "## Negative Tests",
        "",
    ])
    for test in payload["negative_tests"]:
        verdict = "PASS" if test["passed"] else "FAIL"
        lines.extend([
            f"### {verdict}: {test['name']}",
            "",
            f"Expected: {test['expected']}",
            "",
        ])
        for item in test["evidence"]:
            lines.append(f"- {item}")
        lines.append("")

    lines.extend([
        "## Static Coverage",
        "",
        "```json",
        json.dumps(payload["static_analysis"], ensure_ascii=False, indent=2),
        "```",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(ROOT))
    parser.add_argument("--skip-negative-tests", action="store_true")
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args()

    required_by_source = documented_required_artifacts()
    required = union_artifacts(required_by_source)
    static, findings = analyze_static_enforcement(required)
    negative_results: list[NegativeTestResult] = []
    temp_root = None
    if not args.skip_negative_tests:
        negative_results, temp_root = run_negative_tests(keep_temp=args.keep_temp)
        findings.extend(findings_from_negative_tests(negative_results))

    payload = {
        "schema_version": "sofunny-admission-enforcement-audit.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": severity_status(findings),
        "skill_root": str(ROOT),
        "required_artifacts": {
            "by_source": required_by_source,
            "union": required,
        },
        "static_analysis": static,
        "negative_tests": [asdict(result) for result in negative_results],
        "findings": [asdict(finding) for finding in findings],
    }
    if temp_root:
        payload["temp_root"] = temp_root

    output_dir = Path(args.output_dir).expanduser().resolve()
    json_path = output_dir / "admission_enforcement_audit.json"
    md_path = output_dir / "admission_enforcement_audit.md"
    write_json(json_path, payload)
    write_text(md_path, render_markdown(payload))
    print(json.dumps({
        "status": payload["status"],
        "findings": len(findings),
        "p0": sum(1 for finding in findings if finding.severity == "P0"),
        "p1": sum(1 for finding in findings if finding.severity == "P1"),
        "p2": sum(1 for finding in findings if finding.severity == "P2"),
        "json": str(json_path),
        "md": str(md_path),
    }, ensure_ascii=False, indent=2))
    return 1 if payload["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
