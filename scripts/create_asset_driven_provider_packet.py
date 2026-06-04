#!/usr/bin/env python3
"""Create a full asset-driven SoFunny provider packet in one command."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from sofunny_anim.profiles import coalesce, get_path, keypose_count, load_profile


SCRIPT_DIR = Path(__file__).resolve().parent


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--character-dir")
    parser.add_argument("--gif-dir")
    parser.add_argument("--reference", required=True)
    parser.add_argument("--character-name", required=True)
    parser.add_argument("--action")
    parser.add_argument("--direction", default="front")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--frames", type=int)
    parser.add_argument("--canvas")
    parser.add_argument("--top-donors", type=int, default=5)
    parser.add_argument("--force-reindex", action="store_true")
    args = parser.parse_args()
    profile = load_profile(args.profile)
    args.character_dir = args.character_dir or get_path(profile, "asset_paths.character_dir", None)
    args.gif_dir = args.gif_dir or get_path(profile, "asset_paths.gif_dir", None)
    args.action = args.action or get_path(profile, "motion_defaults.default_action", None)
    args.frames = args.frames if args.frames is not None else keypose_count(profile, "production", 12)
    args.canvas = str(coalesce(args.canvas, profile, "default_canvas", "384x384"))
    if not args.character_dir:
        parser.error("--character-dir is required when profile.asset_paths.character_dir is unset")
    if not args.gif_dir:
        parser.error("--gif-dir is required when profile.asset_paths.gif_dir is unset")
    if not args.action:
        parser.error("--action is required when profile.motion_defaults.default_action is unset")

    run_dir = Path(args.run_dir).expanduser().resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    asset_index_dir = run_dir / "asset_index"
    motion_selection_dir = run_dir / "motion_reference_selection"
    motion_atlas_dir = run_dir / "motion_atlas"
    brief_dir = run_dir / "provider_brief"

    asset_index = asset_index_dir / "asset_index.json"
    if args.force_reindex or not asset_index.exists():
        run(
            [
                sys.executable,
                str(SCRIPT_DIR / "index_sofunny_assets.py"),
                "--profile",
                args.profile,
                "--character-dir",
                args.character_dir,
                "--gif-dir",
                args.gif_dir,
                "--output-dir",
                str(asset_index_dir),
            ]
        )

    run(
        [
            sys.executable,
            str(SCRIPT_DIR / "select_motion_reference.py"),
            "--profile",
            args.profile,
            "--asset-index",
            str(asset_index),
            "--target-character",
            args.character_name,
            "--target-action",
            args.action,
            "--direction",
            args.direction,
            "--output-dir",
            str(motion_selection_dir),
            "--top",
            str(max(args.top_donors, 10)),
        ]
    )

    run(
        [
            sys.executable,
            str(SCRIPT_DIR / "build_motion_atlas.py"),
            "--profile",
            args.profile,
            "--selection",
            str(motion_selection_dir / "motion_reference_selection.json"),
            "--output-dir",
            str(motion_atlas_dir),
            "--top",
            str(args.top_donors),
            "--phase-count",
            str(args.frames),
            "--cell",
            "192x220",
        ]
    )

    run(
        [
            sys.executable,
            str(SCRIPT_DIR / "create_provider_brief.py"),
            "--profile",
            args.profile,
            "--reference",
            args.reference,
            "--run-dir",
            str(brief_dir),
            "--character-name",
            args.character_name,
            "--action",
            args.action,
            "--frames",
            str(args.frames),
            "--canvas",
            args.canvas,
        ]
    )

    run(
        [
            sys.executable,
            str(SCRIPT_DIR / "create_provider_packet.py"),
            "--profile",
            args.profile,
            "--run-dir",
            str(run_dir),
            "--reference",
            args.reference,
            "--brief",
            str(brief_dir / "provider_briefs" / f"{args.action}.md"),
            "--motion-reference",
            str(motion_atlas_dir / "motion_atlas_contact_sheet.png"),
            "--cell",
            args.canvas,
        ]
    )

    print(str(run_dir / "provider_packet"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
