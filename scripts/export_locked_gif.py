#!/usr/bin/env python3
"""Export GIF/WebP/spritesheet from frozen SoFunny keyposes without changing source art."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from sofunny_anim.frame_layout import read_sequence, write_sequence
from sofunny_anim.freeze_gate import PASS_VALUES, production_source_animation_route, read_json, require_freeze_gate
from sofunny_anim.manifests import write_json
from sofunny_anim.previews import save_checker_gif, save_contact_sheet, save_transparent_gif, save_transparent_sheet, save_webp
from sofunny_anim.profiles import coalesce, get_path, load_profile


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_frame_paths(run_dir: Path, manifest: dict) -> list[Path]:
    paths = []
    for frame in manifest.get("frames", []):
        file_value = frame.get("file")
        if not file_value:
            continue
        path = Path(file_value)
        paths.append(path if path.is_absolute() else run_dir / path)
    if not paths:
        accepted = Path(manifest.get("accepted_keyposes", run_dir / "accepted_keyposes"))
        paths = sorted(accepted.glob("*.png"))
    return paths


def verify_hashes(run_dir: Path, manifest: dict) -> list[dict]:
    entries = []
    expected_by_file = {Path(item.get("file", "")).name: item.get("sha256") for item in manifest.get("frames", [])}
    for path in manifest_frame_paths(run_dir, manifest):
        actual = sha256(path)
        expected = expected_by_file.get(path.name)
        entries.append({
            "file": str(path),
            "expected_sha256": expected,
            "actual_sha256": actual,
            "match": expected is None or expected == actual,
        })
    return entries


def reference_timing(path: Path) -> tuple[int, int, list[int]]:
    image = Image.open(path)
    durations = []
    try:
        index = 0
        while True:
            image.seek(index)
            durations.append(int(image.info.get("duration", 0) or 0))
            index += 1
    except EOFError:
        pass
    if not durations:
        raise ValueError(f"reference gif has no frames: {path}")
    return len(durations), Counter(durations).most_common(1)[0][0], durations


def expand_frames(frames: list[Image.Image], target_count: int) -> tuple[list[Image.Image], list[int]]:
    if target_count <= 0:
        raise ValueError("target frame count must be positive")
    expanded = []
    source_indices = []
    for index in range(target_count):
        source_index = min(len(frames) - 1, int(index * len(frames) / target_count))
        expanded.append(frames[source_index].copy())
        source_indices.append(source_index)
    return expanded, source_indices


def maybe_optimize_with_gifsicle(path: Path, enabled: bool) -> dict:
    gifsicle = shutil.which("gifsicle")
    if not enabled:
        return {"enabled": False, "used": False, "reason": "not requested"}
    if not gifsicle:
        return {"enabled": True, "used": False, "reason": "gifsicle not found"}
    tmp = path.with_suffix(".optimized.gif")
    result = subprocess.run([gifsicle, "-O3", str(path), "-o", str(tmp)], text=True, capture_output=True)
    if result.returncode != 0:
        return {"enabled": True, "used": False, "reason": "gifsicle failed", "stderr": result.stderr}
    tmp.replace(path)
    return {"enabled": True, "used": True, "command": [gifsicle, "-O3", str(path)]}


def require_part_consistency_if_source_route(run_dir: Path, production: bool) -> dict | None:
    if not (run_dir / "part_map.json").exists():
        return None
    report_path = run_dir / "part_consistency_report.json"
    if not report_path.exists():
        if not production:
            return {"status": "missing", "candidate_only": True}
        raise ValueError("source-animation route requires part_consistency_report.json before GIF export")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if production and report.get("status") != "pass":
        raise ValueError(f"part_consistency_report.json must be pass before GIF export, got {report.get('status')}")
    return report


def require_strict_freeze_for_export(run_dir: Path, manifest: dict, production: bool) -> dict:
    freeze_report = read_json(run_dir / "keypose_freeze_report.json", {})
    failures: list[str] = []
    if freeze_report.get("status") != "pass":
        failures.append(f"keypose_freeze_report.status must be pass, got {freeze_report.get('status', 'missing')}")
    if production and freeze_report.get("manual_approved") is True:
        failures.append("manual-approved freeze is diagnostic-only and cannot feed locked export")
    if production and manifest.get("manual_approved") is True:
        failures.append("keypose_freeze_manifest.manual_approved=true cannot feed locked export")
    if production and manifest.get("candidate_only") is True:
        failures.append("candidate-only freeze cannot feed production locked export")
    if production and production_source_animation_route(run_dir):
        for key, status in (manifest.get("requirements") or {}).items():
            if status not in PASS_VALUES:
                failures.append(f"keypose_freeze_manifest.requirements.{key} must be pass for locked export, got {status}")
    if failures:
        raise ValueError("; ".join(failures))
    return freeze_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-run-dir")
    parser.add_argument("--duration-ms", type=int)
    parser.add_argument("--target-frames", type=int)
    parser.add_argument("--reference-gif")
    parser.add_argument("--use-profile-reference", action="store_true")
    parser.add_argument("--optimize-gif", action="store_true")
    parser.add_argument("--stage", choices=["candidate", "production"], default="candidate")
    args = parser.parse_args()

    profile = load_profile(args.profile)
    args.duration_ms = int(coalesce(args.duration_ms, profile, "motion_defaults.duration_ms", 90))
    if not args.reference_gif and args.use_profile_reference:
        args.reference_gif = get_path(profile, "asset_paths.default_timing_reference")
    run_dir = Path(args.run_dir).expanduser().resolve()
    manifest = require_freeze_gate(run_dir, allow_unfrozen=False)
    try:
        production = args.stage == "production"
        freeze_report = require_strict_freeze_for_export(run_dir, manifest, production)
        part_consistency = require_part_consistency_if_source_route(run_dir, production)
    except Exception as exc:
        report = {
            "schema_version": "sofunny-locked-gif-export.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "fail",
            "run_dir": str(run_dir),
            "failure": "FREEZE_OR_SOURCE_GATE_BLOCKED_EXPORT",
            "message": str(exc),
        }
        write_json(run_dir / "locked_gif_export_report.json", report)
        print(json.dumps({"status": "fail", "failure": report["failure"], "message": str(exc), "report": str(run_dir / "locked_gif_export_report.json")}, indent=2))
        return 1
    before_hashes = verify_hashes(run_dir, manifest)
    if not before_hashes or not all(item["match"] for item in before_hashes):
        report = {
            "schema_version": "sofunny-locked-gif-export.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "fail",
            "run_dir": str(run_dir),
            "failure": "FROZEN_KEYPOSE_HASH_MISMATCH",
            "source_hashes_before": before_hashes,
        }
        write_json(run_dir / "locked_gif_export_report.json", report)
        print(json.dumps({"status": "fail", "failure": report["failure"], "report": str(run_dir / "locked_gif_export_report.json")}, indent=2))
        return 1

    output_run = Path(args.output_run_dir).expanduser().resolve() if args.output_run_dir else run_dir
    if output_run != run_dir:
        if output_run.exists():
            shutil.rmtree(output_run)
        shutil.copytree(run_dir, output_run)

    source_frames = read_sequence(run_dir / "accepted_keyposes")
    reference_details = None
    duration_ms = args.duration_ms
    target_count = args.target_frames or len(source_frames)
    if args.reference_gif:
        reference_count, reference_duration, reference_durations = reference_timing(Path(args.reference_gif).expanduser().resolve())
        target_count = args.target_frames or reference_count
        duration_ms = reference_duration
        reference_details = {
            "reference_gif": str(Path(args.reference_gif).expanduser().resolve()),
            "reference_frame_count": reference_count,
            "reference_duration_ms_mode": reference_duration,
            "reference_durations_ms": reference_durations,
        }
    frames, source_indices = expand_frames(source_frames, target_count)
    write_sequence(frames, output_run / "locked_export_frames")
    save_contact_sheet(source_frames, output_run / "keypose_contact_sheet.png", 192)
    save_contact_sheet(frames, output_run / "contact_sheet.png", 192)
    save_transparent_sheet(source_frames, output_run / "sheet-transparent.png")
    save_transparent_gif(frames, output_run / "animation.gif", duration_ms)
    save_checker_gif(frames, output_run / "animation_checker.gif", duration_ms)
    save_webp(frames, output_run / "animation.webp", duration_ms)
    optimizer = maybe_optimize_with_gifsicle(output_run / "animation.gif", args.optimize_gif)
    after_hashes = verify_hashes(run_dir, manifest)
    source_unchanged = bool(after_hashes) and all(item["match"] for item in after_hashes)
    report = {
        "schema_version": "sofunny-locked-gif-export.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if source_unchanged else "fail",
        "approval_boundary": "Candidate export success is not production approval. Direct visual review and production_approved=true are still required.",
        "export_stage": args.stage,
        "candidate_only": args.stage != "production" or manifest.get("candidate_only") is True,
        "profile": profile.get("profile_name"),
        "run_dir": str(run_dir),
        "output_run_dir": str(output_run),
        "freeze_manifest": str(run_dir / "keypose_freeze_manifest.json"),
        "source_keypose_count": len(source_frames),
        "export_frame_count": len(frames),
        "duration_ms": duration_ms,
        "duplicated_timing_frames": len(frames) != len(source_frames),
        "source_indices": source_indices,
        "reference_timing": reference_details,
        "optimizer": optimizer,
        "source_hashes_before": before_hashes,
        "source_hashes_after": after_hashes,
        "source_keyposes_unchanged": source_unchanged,
        "freeze_report": freeze_report,
        "part_consistency": part_consistency,
        "outputs": {
            "animation_gif": str(output_run / "animation.gif"),
            "animation_checker_gif": str(output_run / "animation_checker.gif"),
            "animation_webp": str(output_run / "animation.webp"),
            "sheet_transparent": str(output_run / "sheet-transparent.png"),
        },
    }
    write_json(output_run / "locked_gif_export_report.json", report)
    print(json.dumps({"status": report["status"], "report": str(output_run / "locked_gif_export_report.json"), "animation": str(output_run / "animation.gif")}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
