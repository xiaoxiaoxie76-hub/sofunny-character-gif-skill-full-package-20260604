#!/usr/bin/env python3
"""Create lively 40-frame local in-betweens from accepted SoFunny keyframes."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from collections import Counter
from pathlib import Path

from sofunny_anim.profiles import load_profile

from PIL import Image, ImageDraw, ImageFilter
import numpy as np

from sofunny_anim.frame_layout import read_sequence, write_sequence
from sofunny_anim.freeze_gate import require_freeze_gate
from sofunny_anim.manifests import write_json
from sofunny_anim.motion_metrics import audit_frames
from sofunny_anim.previews import save_checker_gif, save_contact_sheet, save_transparent_gif, save_transparent_sheet, save_webp
from sofunny_anim.visual_stability import audit_visual_stability


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


def shifted(image: Image.Image, dx: int, dy: int) -> Image.Image:
    out = Image.new("RGBA", image.size, (0, 0, 0, 0))
    out.alpha_composite(image.convert("RGBA"), (dx, dy))
    return out


def region_shift(
    image: Image.Image,
    center: tuple[int, int],
    radius: tuple[int, int],
    dx: int,
    dy: int,
    strength: int,
    blur: int = 10,
) -> Image.Image:
    if dx == 0 and dy == 0:
        return image
    rgba = image.convert("RGBA")
    mask = Image.new("L", rgba.size, 0)
    draw = ImageDraw.Draw(mask)
    cx, cy = center
    rx, ry = radius
    draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=strength)
    mask = mask.filter(ImageFilter.GaussianBlur(blur))
    moved = shifted(rgba, dx, dy)
    return Image.composite(moved, rgba, mask)


def eased_blend(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    t = max(0.0, min(1.0, t))
    # Smoothstep reduces snap near keyframes.
    t = t * t * (3.0 - 2.0 * t)
    return Image.blend(a.convert("RGBA"), b.convert("RGBA"), t)


def coverage_blend(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    t = max(0.0, min(1.0, t))
    t = t * t * (3.0 - 2.0 * t)
    arr_a = np.asarray(a.convert("RGBA"), dtype=np.float32)
    arr_b = np.asarray(b.convert("RGBA"), dtype=np.float32)
    alpha_a = arr_a[:, :, 3]
    alpha_b = arr_b[:, :, 3]
    both = (alpha_a > 8) & (alpha_b > 8)
    choose_b = (alpha_b * t) > (alpha_a * (1.0 - t))

    out = np.zeros_like(arr_a)
    out[~choose_b] = arr_a[~choose_b]
    out[choose_b] = arr_b[choose_b]
    out[both] = arr_a[both] * (1.0 - t) + arr_b[both] * t
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def synthesize_frame(
    keyframes: list[Image.Image],
    frame_index: int,
    total_frames: int,
    transition_start: float,
    micro_strength: float,
    blend_mode: str,
) -> tuple[Image.Image, dict]:
    key_count = len(keyframes)
    pos = (frame_index / total_frames) * key_count
    key_index = int(math.floor(pos)) % key_count
    next_index = (key_index + 1) % key_count
    local = pos - math.floor(pos)

    # Hold the strong key drawing for most of the segment, then blend only near the transition.
    if local < transition_start:
        base = keyframes[key_index].convert("RGBA")
        blend_t = 0.0
    else:
        blend_t = (local - transition_start) / max(0.001, 1.0 - transition_start)
        if blend_mode == "coverage":
            base = coverage_blend(keyframes[key_index], keyframes[next_index], blend_t)
        else:
            base = eased_blend(keyframes[key_index], keyframes[next_index], blend_t)

    cycle = 2.0 * math.pi * frame_index / total_frames
    # Compact jog: head/torso bob is subtle; fists and tail get enough phase offset to avoid frozen upper-body.
    head_dx = round(micro_strength * 0.8 * math.sin(cycle + 0.35))
    head_dy = round(micro_strength * 1.6 * math.sin(cycle + math.pi))
    left_hand_dx = round(micro_strength * 2.2 * math.sin(cycle + math.pi))
    left_hand_dy = round(micro_strength * 2.8 * math.sin(cycle + math.pi / 2))
    right_hand_dx = round(micro_strength * 2.2 * math.sin(cycle))
    right_hand_dy = round(micro_strength * 2.8 * math.sin(cycle + math.pi * 1.5))
    tail_dx = round(micro_strength * 1.8 * math.sin(cycle - 0.9))
    tail_dy = round(micro_strength * 1.2 * math.sin(cycle - 0.55))

    lively = base
    lively = region_shift(lively, (194, 109), (74, 72), head_dx, head_dy, 125, blur=16)
    lively = region_shift(lively, (111, 236), (32, 38), left_hand_dx, left_hand_dy, 178, blur=8)
    lively = region_shift(lively, (244, 235), (34, 38), right_hand_dx, right_hand_dy, 178, blur=8)
    lively = region_shift(lively, (263, 249), (58, 55), tail_dx, tail_dy, 120, blur=14)
    # Small shadow breathing helps flight/contact phases read without moving the whole character.
    shadow_dy = round(micro_strength * 1.2 * math.sin(cycle + math.pi))
    lively = region_shift(lively, (194, 350), (90, 20), 0, shadow_dy, 120, blur=8)
    return lively, {
        "frame": frame_index,
        "source_key": key_index,
        "next_key": next_index,
        "local_phase": round(local, 4),
        "blend_t": round(blend_t, 4),
        "head_shift": [head_dx, head_dy],
        "left_hand_shift": [left_hand_dx, left_hand_dy],
        "right_hand_shift": [right_hand_dx, right_hand_dy],
        "tail_shift": [tail_dx, tail_dy],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-run-dir", required=True)
    parser.add_argument("--reference-gif", required=True)
    parser.add_argument("--target-frames", type=int)
    parser.add_argument("--duration-ms", type=int)
    parser.add_argument("--transition-start", type=float, default=0.68)
    parser.add_argument("--micro-strength", type=float, default=1.0)
    parser.add_argument("--blend-mode", choices=["alpha", "coverage"], default="alpha")
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
    keyframes = read_sequence(keypose_dir if keypose_dir.exists() else source_run / "sequence_frames")
    reference_count, reference_duration, reference_durations = reference_timing(reference)
    target_frames = args.target_frames or reference_count
    duration_ms = args.duration_ms or reference_duration

    lively_frames: list[Image.Image] = []
    frame_reports: list[dict] = []
    for index in range(target_frames):
        frame, report = synthesize_frame(keyframes, index, target_frames, args.transition_start, args.micro_strength, args.blend_mode)
        lively_frames.append(frame)
        frame_reports.append(report)

    # Preserve the accepted 6-frame source separately; make sequence_frames the real playback sequence.
    accepted_dir = output_run / "accepted_keyframes"
    write_sequence(keyframes, accepted_dir)
    write_sequence(lively_frames, output_run / "sequence_frames")
    write_sequence(lively_frames, output_run / "timed_preview_frames")
    save_contact_sheet(lively_frames, output_run / "contact_sheet.png", 192)
    save_contact_sheet(lively_frames[: min(12, len(lively_frames))], output_run / "contact_sheet_first_12.png", 192)
    save_transparent_sheet(lively_frames, output_run / "sheet-transparent.png")
    save_transparent_gif(lively_frames, output_run / "animation.gif", duration_ms)
    save_checker_gif(lively_frames, output_run / "animation_checker.gif", duration_ms)
    save_webp(lively_frames, output_run / "animation.webp", duration_ms)
    write_json(output_run / "visual_stability_report.json", audit_visual_stability(lively_frames))
    write_json(output_run / "jitter_diagnostics.json", audit_frames(lively_frames, duration_ms))

    candidate_path = output_run / "candidate_manifest.json"
    if candidate_path.exists():
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        candidate["frames"] = target_frames
        candidate["route"] = f"{candidate.get('route', 'candidate')}_lively_inbetweens"
        candidate["accepted_keyframes"] = str(accepted_dir)
        candidate_path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    write_json(
        output_run / "lively_inbetween_report.json",
        {
            "status": "pass",
            "source_run": str(source_run),
            "output_run": str(output_run),
            "reference_gif": str(reference),
            "freeze_gate": freeze_manifest,
            "source_keyframes": len(keyframes),
            "target_frames": target_frames,
            "duration_ms": duration_ms,
            "transition_start": args.transition_start,
            "micro_strength": args.micro_strength,
            "blend_mode": args.blend_mode,
            "total_duration_ms": target_frames * duration_ms,
            "reference_frame_count": reference_count,
            "reference_durations_ms": reference_durations,
            "frames": frame_reports,
            "notes": [
                "Creates unique local in-between frames from accepted keyframes.",
                "Adds head bob, two-hand counter motion, tail lag, and shadow breathing without provider redraw.",
                "This is a local animation polish pass; it cannot create new fully redrawn limb anatomy.",
            ],
        },
    )
    print(str(output_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
