#!/usr/bin/env python3
"""Export GIF/WebP previews using timing sampled from a reference GIF."""

from __future__ import annotations

import argparse
import shutil
from collections import Counter
from pathlib import Path

from sofunny_anim.profiles import load_profile

from PIL import Image

from sofunny_anim.frame_layout import read_sequence, write_sequence
from sofunny_anim.freeze_gate import require_freeze_gate
from sofunny_anim.manifests import write_json
from sofunny_anim.previews import save_checker_gif, save_transparent_gif, save_webp


def reference_timing(path: Path) -> tuple[int, int, list[int]]:
    image = Image.open(path)
    durations: list[int] = []
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
    common_duration = Counter(durations).most_common(1)[0][0]
    return len(durations), common_duration, durations


def expand_frames(frames: list[Image.Image], target_count: int) -> tuple[list[Image.Image], list[int]]:
    if target_count <= 0:
        raise ValueError("target frame count must be positive")
    if not frames:
        raise ValueError("no source frames")
    expanded: list[Image.Image] = []
    source_indices: list[int] = []
    for index in range(target_count):
        source_index = min(len(frames) - 1, int(index * len(frames) / target_count))
        expanded.append(frames[source_index].copy())
        source_indices.append(source_index)
    return expanded, source_indices


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-run-dir", required=True)
    parser.add_argument("--reference-gif", required=True)
    parser.add_argument("--allow-unfrozen", action="store_true")
    args = parser.parse_args()
    profile = load_profile(args.profile)

    source_run = Path(args.run_dir).expanduser().resolve()
    freeze_manifest = require_freeze_gate(source_run, args.allow_unfrozen)
    output_run = Path(args.output_run_dir).expanduser().resolve()
    reference = Path(args.reference_gif).expanduser().resolve()
    if output_run.exists() and output_run != source_run:
        shutil.rmtree(output_run)
    if output_run != source_run:
        shutil.copytree(source_run, output_run)

    keypose_dir = source_run / "accepted_keyposes"
    frames = read_sequence(keypose_dir if keypose_dir.exists() else output_run / "sequence_frames")
    reference_count, duration_ms, reference_durations = reference_timing(reference)
    expanded, source_indices = expand_frames(frames, reference_count)
    timed_dir = output_run / "timed_preview_frames"
    write_sequence(expanded, timed_dir)
    save_transparent_gif(expanded, output_run / "animation.gif", duration_ms)
    save_checker_gif(expanded, output_run / "animation_checker.gif", duration_ms)
    save_webp(expanded, output_run / "animation.webp", duration_ms)
    write_json(
        output_run / "retime_preview_report.json",
        {
            "status": "pass",
            "source_run": str(source_run),
            "output_run": str(output_run),
            "reference_gif": str(reference),
            "freeze_gate": freeze_manifest,
            "source_keyframes": len(frames),
            "reference_frame_count": reference_count,
            "reference_duration_ms_mode": duration_ms,
            "reference_durations_ms": reference_durations,
            "expanded_frame_count": len(expanded),
            "expanded_duration_ms": duration_ms,
            "expanded_total_duration_ms": len(expanded) * duration_ms,
            "source_indices": source_indices,
            "notes": [
                "The sprite sheet still contains the original keyframes.",
                "The exported GIF/WebP previews duplicate keyframes to match the reference GIF playback cadence.",
            ],
        },
    )
    print(str(output_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
