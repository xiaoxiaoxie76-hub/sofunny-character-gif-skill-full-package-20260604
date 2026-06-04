#!/usr/bin/env python3
"""Create real no-ghost in-betweens from approved keyframes using one-source warps."""

from __future__ import annotations

import argparse
import shutil
from collections import Counter
from pathlib import Path

from sofunny_anim.profiles import load_profile

import numpy as np
from PIL import Image
from skimage.registration import optical_flow_tvl1
from skimage.transform import warp

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
    return len(durations), Counter(durations).most_common(1)[0][0], durations


def flow_image(image: Image.Image) -> np.ndarray:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.float32) / 255.0
    rgb = rgba[:, :, :3]
    alpha = rgba[:, :, 3]
    luma = rgb[:, :, 0] * 0.299 + rgb[:, :, 1] * 0.587 + rgb[:, :, 2] * 0.114
    # Alpha gives the solver a strong silhouette; luma helps internal suit/limb structure.
    return np.clip(alpha * 0.75 + luma * alpha * 0.25, 0.0, 1.0)


def warp_rgba(image: Image.Image, flow_v: np.ndarray, flow_u: np.ndarray, t: float) -> Image.Image:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.float32) / 255.0
    rows, cols = rgba.shape[:2]
    rr, cc = np.meshgrid(np.arange(rows), np.arange(cols), indexing="ij")
    coords = np.array([rr + flow_v * t, cc + flow_u * t])
    warped = np.zeros_like(rgba)
    for channel in range(4):
        warped[:, :, channel] = warp(
            rgba[:, :, channel],
            coords,
            mode="constant",
            cval=0.0,
            preserve_range=True,
        )
    warped[:, :, 3] = np.where(warped[:, :, 3] < 0.015, 0.0, warped[:, :, 3])
    return Image.fromarray(np.clip(warped * 255.0, 0, 255).astype(np.uint8), "RGBA")


def precompute_segment_flows(frames: list[Image.Image]) -> list[dict]:
    flow_inputs = [flow_image(frame) for frame in frames]
    segments: list[dict] = []
    for index in range(len(frames)):
        nxt = (index + 1) % len(frames)
        # Forward: warp current frame toward next frame.
        f_v, f_u = optical_flow_tvl1(flow_inputs[nxt], flow_inputs[index], attachment=18, tightness=0.35, num_warp=8)
        # Backward: warp next frame back toward current frame.
        b_v, b_u = optical_flow_tvl1(flow_inputs[index], flow_inputs[nxt], attachment=18, tightness=0.35, num_warp=8)
        segments.append({
            "from": index,
            "to": nxt,
            "forward": (f_v, f_u),
            "backward": (b_v, b_u),
        })
    return segments


def synthesize(frames: list[Image.Image], flows: list[dict], frame_index: int, total_frames: int) -> tuple[Image.Image, dict]:
    pos = frame_index * len(frames) / total_frames
    key = int(np.floor(pos)) % len(frames)
    local = float(pos - np.floor(pos))
    nxt = (key + 1) % len(frames)
    if local < 0.02:
        return frames[key].copy(), {"frame": frame_index, "source": key, "target": nxt, "local": round(local, 4), "mode": "key"}
    if local <= 0.5:
        flow_v, flow_u = flows[key]["forward"]
        out = warp_rgba(frames[key], flow_v, flow_u, local)
        return out, {"frame": frame_index, "source": key, "target": nxt, "local": round(local, 4), "mode": "forward_warp"}
    flow_v, flow_u = flows[key]["backward"]
    out = warp_rgba(frames[nxt], flow_v, flow_u, 1.0 - local)
    return out, {"frame": frame_index, "source": nxt, "target": key, "local": round(local, 4), "mode": "backward_warp"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-run-dir", required=True)
    parser.add_argument("--reference-gif", required=True)
    parser.add_argument("--target-frames", type=int)
    parser.add_argument("--duration-ms", type=int)
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
    ref_count, ref_duration, ref_durations = reference_timing(reference)
    target_frames = args.target_frames or ref_count
    duration_ms = args.duration_ms or ref_duration
    flows = precompute_segment_flows(keyframes)
    generated: list[Image.Image] = []
    reports: list[dict] = []
    for index in range(target_frames):
        frame, report = synthesize(keyframes, flows, index, target_frames)
        generated.append(frame)
        reports.append(report)

    write_sequence(keyframes, output_run / "accepted_keyframes")
    write_sequence(generated, output_run / "sequence_frames")
    write_sequence(generated, output_run / "timed_preview_frames")
    save_contact_sheet(generated, output_run / "contact_sheet.png", 192)
    save_contact_sheet(generated[: min(12, len(generated))], output_run / "contact_sheet_first_12.png", 192)
    save_transparent_sheet(generated, output_run / "sheet-transparent.png")
    save_transparent_gif(generated, output_run / "animation.gif", duration_ms)
    save_checker_gif(generated, output_run / "animation_checker.gif", duration_ms)
    save_webp(generated, output_run / "animation.webp", duration_ms)
    write_json(output_run / "visual_stability_report.json", audit_visual_stability(generated))
    write_json(output_run / "jitter_diagnostics.json", audit_frames(generated, duration_ms))
    write_json(output_run / "no_ghost_interpolation_report.json", {
        "status": "pass",
        "source_run": str(source_run),
        "output_run": str(output_run),
        "reference_gif": str(reference),
        "freeze_gate": freeze_manifest,
        "source_keyframes": len(keyframes),
        "target_frames": target_frames,
        "duration_ms": duration_ms,
        "total_duration_ms": target_frames * duration_ms,
        "reference_frame_count": ref_count,
        "reference_durations_ms": ref_durations,
        "frames": reports,
        "notes": [
            "Each in-between is produced from one warped source frame, not alpha-blended front/back images.",
            "This avoids double-exposure ghosting from conventional frame interpolation.",
        ],
    })
    print(str(output_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
