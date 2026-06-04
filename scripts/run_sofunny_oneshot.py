#!/usr/bin/env python3
"""Run a complete SoFunny GIF pipeline from one reference image."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sofunny_anim.image_io import parse_canvas
from sofunny_anim.manifests import write_json


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run(command: list[str], *, allow_fail: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if result.returncode != 0 and not allow_fail:
        raise RuntimeError(f"command failed: {' '.join(command)}\n{result.stderr}")
    return result


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def strict_import_candidate(args: argparse.Namespace, run_dir: Path) -> tuple[bool, dict]:
    if not args.candidate_sheet:
        return False, {"status": "skipped", "reason": "no candidate sheet provided"}
    command = [
        sys.executable,
        str(SCRIPTS / "import_candidate_sheet.py"),
        "--input",
        args.candidate_sheet,
        "--run-dir",
        str(run_dir),
        "--frames",
        str(args.frames),
        "--canvas",
        args.canvas,
        "--layout",
        "grid",
        "--rows",
        str(args.rows),
        "--columns",
        str(args.columns),
        "--allow-uneven-grid",
        "--placement-mode",
        args.placement_mode,
        "--fit-slot-margin",
        str(args.margin),
        "--component-mode",
        "largest",
        "--background",
        args.background,
        "--min-source-cell-margin",
        str(args.min_source_cell_margin),
        "--source-margin-policy",
        "fail",
        "--max-adjacent-height-ratio",
        str(args.max_adjacent_height_ratio),
        "--proportion-policy",
        "fail",
        "--action",
        args.action,
        "--character-name",
        args.character_name,
        "--route",
        "oneshot_candidate_sheet",
    ]
    result = run(command, allow_fail=True)
    return result.returncode == 0, {
        "status": "pass" if result.returncode == 0 else "fail",
        "command": command,
        "stdout": result.stdout.strip().splitlines()[-8:],
        "stderr": result.stderr.strip().splitlines()[-8:],
    }


def local_fallback(args: argparse.Namespace, run_dir: Path) -> dict:
    if args.action != "gentle_bow_flower_sway":
        raise ValueError(f"no built-in local fallback registered for action: {args.action}")
    stage_dir = run_dir / "local_sheet_generation"
    command = [
        sys.executable,
        str(SCRIPTS / "generate_reference_locked_bow.py"),
        "--reference",
        args.reference,
        "--run-dir",
        str(stage_dir),
        "--character-name",
        args.character_name,
        "--action",
        args.action,
        "--frames",
        str(args.frames),
        "--canvas",
        args.canvas,
        "--duration-ms",
        str(args.duration_ms),
        "--margin",
        str(args.margin),
        "--rows",
        str(args.rows),
        "--columns",
        str(args.columns),
    ]
    result = run(command)
    generated_sheet = stage_dir / "local_generated_sheet.png"
    import_command = [
        sys.executable,
        str(SCRIPTS / "import_candidate_sheet.py"),
        "--input",
        str(generated_sheet),
        "--run-dir",
        str(run_dir),
        "--frames",
        str(args.frames),
        "--canvas",
        args.canvas,
        "--layout",
        "grid",
        "--rows",
        str(args.rows),
        "--columns",
        str(args.columns),
        "--placement-mode",
        args.placement_mode,
        "--fit-slot-margin",
        str(args.margin),
        "--component-mode",
        "clean-small",
        "--background",
        "transparent",
        "--min-source-cell-margin",
        str(args.min_source_cell_margin),
        "--source-margin-policy",
        "fail",
        "--max-adjacent-height-ratio",
        str(args.max_adjacent_height_ratio),
        "--proportion-policy",
        "warn",
        "--action",
        args.action,
        "--character-name",
        args.character_name,
        "--route",
        "oneshot_local_generated_sheet",
    ]
    import_result = run(import_command)
    return {
        "status": "diagnostic",
        "admission_eligible": False,
        "generation_command": command,
        "import_command": import_command,
        "generated_sheet": str(generated_sheet),
        "stdout": result.stdout.strip().splitlines()[-8:],
        "import_stdout": import_result.stdout.strip().splitlines()[-8:],
    }


def freeze_export_audit(args: argparse.Namespace, run_dir: Path) -> dict:
    phases = ",".join(f"f{index:02d}" for index in range(args.frames))
    commands = [
        [
            sys.executable,
            str(SCRIPTS / "freeze_keyposes.py"),
            "--run-dir",
            str(run_dir),
            "--frame-dir",
            str(run_dir / "sequence_frames"),
            "--canvas",
            args.canvas,
            "--duration-ms",
            str(args.duration_ms),
            "--action",
            args.action,
            "--stage",
            "candidate",
            "--phases",
            phases,
        ],
        [
            sys.executable,
            str(SCRIPTS / "export_locked_gif.py"),
            "--run-dir",
            str(run_dir),
            "--duration-ms",
            str(args.duration_ms),
            "--stage",
            "candidate",
        ],
    ]
    results = []
    for command in commands:
        result = run(command)
        results.append({"command": command, "stdout": result.stdout.strip().splitlines()[-8:]})
    audit = run([
        sys.executable,
        str(SCRIPTS / "audit_action_semantics.py"),
        "--run-dir",
        str(run_dir),
        "--action",
        args.action,
    ], allow_fail=True)
    results.append({
        "command": [sys.executable, str(SCRIPTS / "audit_action_semantics.py"), "--run-dir", str(run_dir), "--action", args.action],
        "returncode": audit.returncode,
        "stdout": audit.stdout.strip().splitlines()[-8:],
        "stderr": audit.stderr.strip().splitlines()[-8:],
    })
    return {"status": "pass" if audit.returncode == 0 else "fail", "steps": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--character-name", required=True)
    parser.add_argument("--action", default="gentle_bow_flower_sway")
    parser.add_argument("--candidate-sheet")
    parser.add_argument("--frames", type=int, default=16)
    parser.add_argument("--canvas", default="512x512")
    parser.add_argument("--rows", type=int, default=4)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--background", choices=["white", "green", "checker", "transparent"], default="white")
    parser.add_argument("--placement-mode", choices=["anchor", "cell", "fit-slot", "fit-ground"], default="fit-ground")
    parser.add_argument("--duration-ms", type=int, default=90)
    parser.add_argument("--margin", type=int, default=56)
    parser.add_argument("--min-source-cell-margin", type=int, default=12)
    parser.add_argument("--max-adjacent-height-ratio", type=float, default=0.06)
    parser.add_argument(
        "--allow-diagnostic-fallback",
        action="store_true",
        help="Allow the local reference-locked bow generator as a diagnostic-only smoke route.",
    )
    args = parser.parse_args()
    parse_canvas(args.canvas)

    run_dir = Path(args.run_dir).expanduser().resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    brief_result = run([
        sys.executable,
        str(SCRIPTS / "create_provider_brief.py"),
        "--reference",
        args.reference,
        "--run-dir",
        str(run_dir),
        "--character-name",
        args.character_name,
        "--action",
        args.action,
        "--frames",
        str(args.frames),
        "--canvas",
        args.canvas,
    ])
    imported, import_report = strict_import_candidate(args, run_dir)
    fallback_report = None
    route = "candidate_sheet"
    if not imported:
        if not args.allow_diagnostic_fallback:
            route = "candidate_sheet_failed" if args.candidate_sheet else "candidate_sheet_required"
            report = {
                "schema_version": "sofunny-oneshot-report.v1",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "fail",
                "route": route,
                "admission_eligible": False,
                "reference": str(Path(args.reference).expanduser().resolve()),
                "candidate_sheet": args.candidate_sheet,
                "provider_brief": brief_result.stdout.strip().splitlines()[-1] if brief_result.stdout.strip() else "",
                "candidate_import": import_report,
                "fallback": {
                    "status": "blocked",
                    "reason": "diagnostic fallback is disabled by default; regenerate or provide a valid provider sheet",
                    "enable_only_for_smoke": "--allow-diagnostic-fallback",
                },
                "freeze_export_audit": None,
                "outputs": {},
            }
            report_path = run_dir / "oneshot_report.json"
            write_json(report_path, report)
            stderr_lines = import_report.get("stderr", [])
            print(json.dumps({
                "status": "fail",
                "route": route,
                "run_dir": str(run_dir),
                "oneshot_report": str(report_path),
                "reason": stderr_lines[-1] if stderr_lines else report["fallback"]["reason"],
            }, ensure_ascii=False, indent=2))
            return 1
        fallback_report = local_fallback(args, run_dir)
        route = "diagnostic_local_fallback"
    try:
        freeze_report = freeze_export_audit(args, run_dir)
    except Exception as exc:
        freeze_report = {
            "status": "fail",
            "failure": "freeze_export_audit_failed",
            "message": str(exc),
        }
    status = "pass" if freeze_report.get("status") == "pass" else "fail"
    report = {
        "schema_version": "sofunny-oneshot-report.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "route": route,
        "admission_eligible": status == "pass" and route == "candidate_sheet",
        "reference": str(Path(args.reference).expanduser().resolve()),
        "candidate_sheet": args.candidate_sheet,
        "provider_brief": brief_result.stdout.strip().splitlines()[-1] if brief_result.stdout.strip() else "",
        "candidate_import": import_report,
        "fallback": fallback_report,
        "freeze_export_audit": freeze_report,
        "outputs": {
            "animation_gif": str(run_dir / "animation.gif"),
            "animation_webp": str(run_dir / "animation.webp"),
            "generated_sheet": (fallback_report or {}).get("generated_sheet", args.candidate_sheet),
            "contact_sheet": str(run_dir / "contact_sheet.png"),
            "locked_export_report": str(run_dir / "locked_gif_export_report.json"),
        },
    }
    write_json(run_dir / "oneshot_report.json", report)
    print(json.dumps({"status": status, "route": route, "run_dir": str(run_dir), "animation": str(run_dir / "animation.gif")}, ensure_ascii=False, indent=2))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
