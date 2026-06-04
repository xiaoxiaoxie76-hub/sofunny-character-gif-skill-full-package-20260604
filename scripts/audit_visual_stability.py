#!/usr/bin/env python3
"""Audit upper-body and silhouette stability for a SoFunny sequence."""

from __future__ import annotations

import argparse
from pathlib import Path

from sofunny_anim.frame_layout import read_sequence
from sofunny_anim.manifests import write_json
from sofunny_anim.profiles import get_path, load_profile
from sofunny_anim.visual_stability import audit_visual_stability


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    profile = load_profile(args.profile)
    frames = read_sequence(run_dir / "sequence_frames")
    thresholds = get_path(profile, "thresholds.visual_stability", {})
    report = audit_visual_stability(frames, thresholds=thresholds)
    report["profile"] = profile.get("profile_name")
    write_json(run_dir / "visual_stability_report.json", report)
    print({"status": report["status"], "warnings": report["warnings"]})
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
