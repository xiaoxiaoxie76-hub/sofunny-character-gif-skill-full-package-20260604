#!/usr/bin/env python3
"""Export SoFunny previews from sequence_frames."""

from __future__ import annotations

import argparse
from pathlib import Path

from sofunny_anim.profiles import load_profile

from sofunny_anim.frame_layout import read_sequence
from sofunny_anim.previews import save_checker_gif, save_contact_sheet, save_transparent_gif, save_transparent_sheet, save_webp


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--duration-ms", type=int, default=90)
    args = parser.parse_args()
    profile = load_profile(args.profile)
    run_dir = Path(args.run_dir).expanduser().resolve()
    frames = read_sequence(run_dir / "sequence_frames")
    save_contact_sheet(frames, run_dir / "contact_sheet.png", 256)
    save_contact_sheet(frames, run_dir / "contact_sheet_full_canvas.png", 192)
    save_transparent_sheet(frames, run_dir / "sheet-transparent.png")
    save_transparent_gif(frames, run_dir / "animation.gif", args.duration_ms)
    save_checker_gif(frames, run_dir / "animation_checker.gif", args.duration_ms)
    save_webp(frames, run_dir / "animation.webp", args.duration_ms)
    print(f"wrote SoFunny previews to {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

