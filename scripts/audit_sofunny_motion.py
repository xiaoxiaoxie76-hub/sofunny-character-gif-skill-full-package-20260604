#!/usr/bin/env python3
"""Audit SoFunny sequence motion and export jitter_diagnostics.json."""

from __future__ import annotations

import argparse
from pathlib import Path

from sofunny_anim.profiles import coalesce, get_path, load_profile

from sofunny_anim.frame_layout import read_sequence
from sofunny_anim.manifests import write_json
from sofunny_anim.motion_metrics import audit_frames


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--duration-ms", type=int)
    args = parser.parse_args()
    profile = load_profile(args.profile)
    args.duration_ms = int(coalesce(args.duration_ms, profile, "motion_defaults.duration_ms", 90))
    run_dir = Path(args.run_dir).expanduser().resolve()
    frames = read_sequence(run_dir / "sequence_frames")
    report = audit_frames(frames, args.duration_ms, get_path(profile, "thresholds.jitter", {}))
    report["profile"] = profile.get("profile_name")
    write_json(run_dir / "jitter_diagnostics.json", report)
    print({"status": report["status"], "frame_count": report["frame_count"]})
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
