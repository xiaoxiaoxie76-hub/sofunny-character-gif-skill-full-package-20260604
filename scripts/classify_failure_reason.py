#!/usr/bin/env python3
"""Classify SoFunny candidate failure reasons for routing."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sofunny_anim.manifests import read_json, write_json
from sofunny_anim.profiles import load_profile


PRIORITY = [
    "PROVIDER_LAYOUT_FAIL",
    "PROVIDER_BACKGROUND_FAIL",
    "CHECKERBOARD_CONTAMINATION",
    "FAKE_TRANSPARENCY",
    "IDENTITY_DRIFT",
    "POSE_WEAK",
    "TAIL_ARTIFACT",
    "PLACEMENT_DRIFT",
    "SIZE_DRIFT",
    "CHOPPY_TIMING",
    "EXPORT_ONLY_FAIL",
    "KEYPOSE_NOT_FROZEN",
    "UNKNOWN_REVIEW_REQUIRED",
]


ROUTES = {
    "PROVIDER_LAYOUT_FAIL": "Regenerate provider output using provider-output-contract. Do not ad hoc split.",
    "PROVIDER_BACKGROUND_FAIL": "Regenerate or re-export with solid #00ff00 background.",
    "CHECKERBOARD_CONTAMINATION": "Regenerate with solid #00ff00, or cleanup only if contamination is edge-connected background.",
    "FAKE_TRANSPARENCY": "Cleanup or re-export from provider; regenerate affected frame if contamination is baked into character.",
    "IDENTITY_DRIFT": "Use single-frame masked repair or regenerate only the affected phase keypose.",
    "POSE_WEAK": "Regenerate the target phase keypose with stronger pose-only guide.",
    "TAIL_ARTIFACT": "Use masked local redraw for affected frame or phase; do not hide with alpha normalization.",
    "PLACEMENT_DRIFT": "Run offset normalization while preserving art.",
    "SIZE_DRIFT": "Run normalize_bbox_size, then inspect for distortion.",
    "CHOPPY_TIMING": "Generate or import more clean keyposes before retiming.",
    "EXPORT_ONLY_FAIL": "Change only GIF/WebP/palette/compression/transparent export settings.",
    "KEYPOSE_NOT_FROZEN": "Run freeze_keyposes.py after keypose admission.",
    "UNKNOWN_REVIEW_REQUIRED": "Inspect contact sheet and reports manually before choosing a route.",
}


def status(run_dir: Path, filename: str) -> str:
    return str(read_json(run_dir / filename, {}).get("status", "missing")).lower()


def add_if(items: list[str], condition: bool, code: str) -> None:
    if condition:
        items.append(code)


def classify(run_dir: Path) -> tuple[list[str], dict]:
    reasons: list[str] = []
    evidence: dict = {}

    preflight = read_json(run_dir / "provider_preflight_report.json", {})
    preflight_failures = preflight.get("failures", [])
    evidence["provider_preflight"] = {"status": preflight.get("status", "missing"), "failures": preflight_failures}
    for code in ["PROVIDER_LAYOUT_FAIL", "PROVIDER_BACKGROUND_FAIL", "CHECKERBOARD_CONTAMINATION", "FAKE_TRANSPARENCY"]:
        add_if(reasons, code in preflight_failures, code)
    add_if(reasons, preflight.get("status") == "fail" and not preflight_failures, "PROVIDER_LAYOUT_FAIL")

    identity_status = status(run_dir, "identity_feature_lock_report.json")
    identity_score = read_json(run_dir / "identity_consistency_score.json", {})
    score_hints = identity_score.get("routing_hints", [])
    evidence["identity"] = {"status": identity_status, "score_hints": score_hints}
    add_if(reasons, identity_status in {"fail", "warn"} or "IDENTITY_DRIFT" in score_hints, "IDENTITY_DRIFT")

    action = read_json(run_dir / "action_validation_report.json", {})
    action_status = str(action.get("status", "missing")).lower()
    evidence["action"] = {"status": action_status, "failures": action.get("failures", [])}
    add_if(reasons, action_status in {"fail", "warn"} or bool(action.get("failures")), "POSE_WEAK")

    body_tail = read_json(run_dir / "body_tail_consistency_report.json", {})
    body_tail_failures = [str(item).lower() for item in body_tail.get("failures", [])]
    evidence["body_tail"] = {"status": body_tail.get("status", "missing"), "failures": body_tail.get("failures", [])}
    add_if(reasons, any("tail" in item for item in body_tail_failures), "TAIL_ARTIFACT")
    add_if(reasons, str(body_tail.get("status", "")).lower() in {"fail", "warn"} and not any("tail" in item for item in body_tail_failures), "SIZE_DRIFT")

    jitter = read_json(run_dir / "jitter_diagnostics.json", {})
    visual = read_json(run_dir / "visual_stability_report.json", {})
    evidence["placement"] = {
        "jitter_status": jitter.get("status", "missing"),
        "visual_status": visual.get("status", "missing"),
        "bbox_bottom_range_px": jitter.get("bbox_bottom_range_px"),
        "anchor_center_x_range_px": jitter.get("anchor_center_x_range_px"),
    }
    add_if(reasons, str(jitter.get("status", "")).lower() in {"fail", "warn"} or str(visual.get("status", "")).lower() in {"fail", "warn"}, "PLACEMENT_DRIFT")
    add_if(reasons, "SIZE_DRIFT" in score_hints or "BODY_SHAPE_DRIFT" in score_hints, "SIZE_DRIFT")

    near_duplicates = jitter.get("near_duplicate_frames", [])
    frame_count = int(jitter.get("frame_count", 0) or 0)
    add_if(reasons, frame_count and frame_count < 12 and len(near_duplicates) >= max(2, frame_count // 3), "CHOPPY_TIMING")

    add_if(reasons, not (run_dir / "keypose_freeze_manifest.json").exists(), "KEYPOSE_NOT_FROZEN")

    export_report = read_json(run_dir / "locked_gif_export_report.json", {})
    add_if(reasons, str(export_report.get("status", "")).lower() == "fail", "EXPORT_ONLY_FAIL")

    if not reasons:
        reasons.append("UNKNOWN_REVIEW_REQUIRED")
    ordered = []
    for code in PRIORITY:
        if code in reasons and code not in ordered:
            ordered.append(code)
    return ordered, evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    profile = load_profile(args.profile)
    output = Path(args.output).expanduser().resolve() if args.output else run_dir / "failure_classification_report.json"
    reasons, evidence = classify(run_dir)
    primary = reasons[0]
    payload = {
        "schema_version": "sofunny-failure-classification.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "routing_only",
        "approval_boundary": "Failure classification supports routing only. It does not approve production.",
        "profile": profile.get("profile_name"),
        "run_dir": str(run_dir),
        "primary_failure": primary,
        "failure_reasons": reasons,
        "recommended_route": ROUTES[primary],
        "all_routes": {code: ROUTES[code] for code in reasons},
        "evidence": evidence,
    }
    write_json(output, payload)
    print(json.dumps({"primary_failure": primary, "report": str(output), "recommended_route": payload["recommended_route"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
