#!/usr/bin/env python3
"""Run SoFunny gates after a provider writes generated_sheet.png into a packet."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sofunny_anim.profiles import coalesce, get_path, keypose_count, load_profile


SCRIPT_DIR = Path(__file__).resolve().parent


def read_json(path: Path, default: dict | None = None) -> dict:
    if not path.exists():
        return default or {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(cmd: list[str], allow_fail: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0 and not allow_fail:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    return result


def write_pending_report(run_dir: Path, generated_sheet: Path) -> None:
    report = [
        "# Provider Result Pending",
        "",
        f"- Expected sheet: `{generated_sheet}`",
        "- Status: `PENDING_PROVIDER_OUTPUT`",
        "",
        "Put the provider-generated fixed-cell sheet at the expected path, then rerun:",
        "",
        "```bash",
        f"python3 {SCRIPT_DIR / 'run_provider_result_gates.py'} --run-dir \"{run_dir}\"",
        "```",
        "",
    ]
    (run_dir / "provider_result_pending_report.md").write_text("\n".join(report), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--generated-sheet")
    parser.add_argument("--frames", type=int)
    parser.add_argument("--canvas")
    parser.add_argument("--duration-ms", type=int)
    parser.add_argument("--character-name", default="beav_buy")
    parser.add_argument("--action")
    parser.add_argument("--skip-preflight", action="store_true")
    args = parser.parse_args()
    profile = load_profile(args.profile)
    args.frames = args.frames if args.frames is not None else keypose_count(profile, "smoke", 6)
    args.canvas = str(coalesce(args.canvas, profile, "default_canvas", "384x384"))
    args.duration_ms = int(coalesce(args.duration_ms, profile, "motion_defaults.duration_ms", 90))
    args.action = args.action or get_path(profile, "motion_defaults.default_action", None)
    if not args.action:
        parser.error("--action is required when profile.motion_defaults.default_action is unset")

    run_dir = Path(args.run_dir).expanduser().resolve()
    packet_dir = run_dir / "provider_packet"
    packet_manifest = read_json(packet_dir / "provider_packet_manifest.json")
    generated_sheet = Path(args.generated_sheet).expanduser().resolve() if args.generated_sheet else Path(packet_manifest.get("expected_output") or packet_dir / "generated_sheet.png")
    candidate_dir = run_dir / "candidate_import"
    status_path = run_dir / "provider_result_gate_report.json"

    if not generated_sheet.exists():
        payload = {
            "schema_version": "sofunny-provider-result-gate.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "profile": profile.get("profile_name"),
            "status": "pending_provider_output",
            "generated_sheet": str(generated_sheet),
            "candidate_dir": str(candidate_dir),
            "next_step": "Create generated_sheet.png with the provider packet, then rerun this script.",
        }
        write_json(status_path, payload)
        write_pending_report(run_dir, generated_sheet)
        print(json.dumps({"status": payload["status"], "generated_sheet": str(generated_sheet)}, ensure_ascii=False, indent=2))
        return 2

    if candidate_dir.exists():
        shutil.rmtree(candidate_dir)

    preflight_result = None
    if not args.skip_preflight:
        preflight_result = run(
            [
                sys.executable,
                str(SCRIPT_DIR / "preflight_provider_output.py"),
                "--profile",
                args.profile,
                "--input",
                str(generated_sheet),
                "--run-dir",
                str(run_dir),
                "--expected-frames",
                str(args.frames),
                "--canvas",
                args.canvas,
            ],
            allow_fail=True,
        )
        preflight = read_json(run_dir / "provider_preflight_report.json")
        if preflight_result.returncode != 0:
            payload = {
                "schema_version": "sofunny-provider-result-gate.v1",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "provider_preflight_failed",
                "generated_sheet": str(generated_sheet),
                "candidate_dir": str(candidate_dir),
                "preflight_report": str(run_dir / "provider_preflight_report.json"),
                "failures": preflight.get("failures", []),
                "next_step": "Regenerate provider output using references/provider-output-contract.md, or fix the exact failure before import.",
            }
            write_json(status_path, payload)
            print(json.dumps({"status": payload["status"], "failures": payload["failures"], "preflight_report": payload["preflight_report"]}, ensure_ascii=False, indent=2))
            return 1

    import_result = run(
        [
            sys.executable,
            str(SCRIPT_DIR / "import_candidate_sheet.py"),
            "--profile",
            args.profile,
            "--input",
            str(generated_sheet),
            "--run-dir",
            str(candidate_dir),
            "--frames",
            str(args.frames),
            "--canvas",
            args.canvas,
            "--action",
            args.action,
            "--character-name",
            args.character_name,
            "--background",
            "green",
            "--route",
            "image_provider_generated",
            "--admission-eligible",
            "--duration-ms",
            str(args.duration_ms),
        ],
        allow_fail=True,
    )
    if (run_dir / "provider_preflight_report.json").exists():
        candidate_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(run_dir / "provider_preflight_report.json", candidate_dir / "provider_preflight_report.json")
    audit_result = run([sys.executable, str(SCRIPT_DIR / "audit_sofunny_motion.py"), "--profile", args.profile, "--run-dir", str(candidate_dir), "--duration-ms", str(args.duration_ms)], allow_fail=True)
    visual_result = run([sys.executable, str(SCRIPT_DIR / "audit_visual_stability.py"), "--profile", args.profile, "--run-dir", str(candidate_dir)], allow_fail=True)
    body_tail_result = run([sys.executable, str(SCRIPT_DIR / "audit_body_tail_consistency.py"), "--profile", args.profile, "--run-dir", str(candidate_dir)], allow_fail=True)
    reference_for_identity = packet_manifest.get("reference") or packet_manifest.get("canonical_reference")
    identity_result = None
    if reference_for_identity:
        identity_result = run(
            [
                sys.executable,
                str(SCRIPT_DIR / "audit_identity_feature_lock.py"),
                "--profile",
                args.profile,
                "--reference",
                str(reference_for_identity),
                "--run-dir",
                str(candidate_dir),
                "--status",
                "manual_required",
                "--note",
                "Auto-created after provider import. Direct visual review must pass character feature identity before admission.",
            ],
            allow_fail=True,
        )

    phase_template = packet_dir / "action_phase_review.template.json"
    if phase_template.exists() and not (candidate_dir / "action_phase_review.json").exists():
        shutil.copy2(phase_template, candidate_dir / "action_phase_review.json")

    action_result = run([sys.executable, str(SCRIPT_DIR / "validate_action_contract.py"), "--profile", args.profile, "--run-dir", str(candidate_dir), "--action", args.action], allow_fail=True)
    jitter = read_json(candidate_dir / "jitter_diagnostics.json")
    visual = read_json(candidate_dir / "visual_stability_report.json")
    body_tail = read_json(candidate_dir / "body_tail_consistency_report.json")
    action = read_json(candidate_dir / "action_validation_report.json")
    identity = read_json(candidate_dir / "identity_feature_lock_report.json")

    status = "needs_review"
    if import_result.returncode != 0:
        status = "import_failed"
    elif jitter.get("status") == "pass" and visual.get("status") == "pass" and body_tail.get("status") == "pass" and action.get("status") == "pass" and identity.get("status") == "pass":
        status = "gate_passed"
    elif jitter.get("status") == "pass" and visual.get("status") == "pass" and body_tail.get("status") == "pass" and action.get("status") == "pass":
        status = "manual_identity_review_required"
    elif jitter.get("status") == "pass" and visual.get("status") == "pass" and body_tail.get("status") == "pass":
        status = "manual_action_review_required"
    else:
        status = "gate_failed"

    payload = {
        "schema_version": "sofunny-provider-result-gate.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile.get("profile_name"),
        "status": status,
        "generated_sheet": str(generated_sheet),
        "candidate_dir": str(candidate_dir),
        "commands": {
            "preflight_returncode": preflight_result.returncode if preflight_result else None,
            "import_returncode": import_result.returncode,
            "audit_returncode": audit_result.returncode,
            "visual_returncode": visual_result.returncode,
            "body_tail_returncode": body_tail_result.returncode,
            "identity_returncode": identity_result.returncode if identity_result else None,
            "action_returncode": action_result.returncode,
        },
        "reports": {
            "jitter_status": jitter.get("status", "missing"),
            "visual_stability_status": visual.get("status", "missing"),
            "body_tail_consistency_status": body_tail.get("status", "missing"),
            "body_tail_failures": body_tail.get("failures", []),
            "identity_feature_lock_status": identity.get("status", "missing"),
            "action_status": action.get("status", "missing"),
            "action_failures": action.get("failures", []),
        },
        "next_step": "Review contact_sheet.png, animation_checker.gif, body_tail_debug_sheet.png, identity_feature_comparison.png, complete identity/action review JSON files, then finalize admission.",
    }
    write_json(status_path, payload)
    print(json.dumps({"status": status, "candidate_dir": str(candidate_dir), "reports": payload["reports"]}, ensure_ascii=False, indent=2))
    return 0 if status in {"gate_passed", "manual_identity_review_required", "manual_action_review_required"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
