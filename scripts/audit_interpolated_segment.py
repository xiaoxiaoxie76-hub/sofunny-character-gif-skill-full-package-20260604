#!/usr/bin/env python3
"""Audit a ToonCrafter candidate interpolation segment before admission or freeze."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_images(frame_dir: Path) -> list[tuple[Path, Image.Image]]:
    paths = sorted(frame_dir.expanduser().glob("*.png"))
    if not paths:
        raise ValueError(f"no PNG frames in {frame_dir}")
    return [(path, Image.open(path).convert("RGBA")) for path in paths]


def rms_delta(a: Image.Image, b: Image.Image) -> float:
    if a.size != b.size:
        b = b.resize(a.size, Image.Resampling.LANCZOS)
    diff = ImageChops.difference(a.convert("RGBA"), b.convert("RGBA"))
    stat = ImageStat.Stat(diff)
    return math.sqrt(sum(value * value for value in stat.rms) / len(stat.rms))


def nonblank(image: Image.Image) -> bool:
    return image.getbbox() is not None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--pair-id", required=True)
    parser.add_argument("--segment-dir")
    parser.add_argument("--pairs", default="interpolation_pairs.json")
    parser.add_argument("--min-frames", type=int, default=3)
    parser.add_argument("--max-endpoint-rms", type=float, default=80.0)
    parser.add_argument("--min-motion-rms", type=float, default=1.0)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    segment_dir = Path(args.segment_dir).expanduser().resolve() if args.segment_dir else run_dir / "tooncrafter_segments" / args.pair_id
    pairs_path = Path(args.pairs)
    if not pairs_path.is_absolute():
        pairs_path = run_dir / pairs_path
    pairs = read_json(pairs_path)
    pair = next((item for item in pairs.get("pairs", []) if item.get("pair_id") == args.pair_id), None)
    if not pair:
        raise ValueError(f"pair_id not found: {args.pair_id}")

    images = load_images(segment_dir)
    blockers: list[str] = []
    warnings: list[str] = []
    if len(images) < args.min_frames:
        blockers.append(f"not enough interpolated frames: {len(images)} < {args.min_frames}")
    blank = [str(path) for path, image in images if not nonblank(image)]
    if blank:
        blockers.append("blank interpolated frames: " + ", ".join(blank))

    start_ref = Image.open(pair["start_frame"]).convert("RGBA")
    end_ref = Image.open(pair["end_frame"]).convert("RGBA")
    start_rms = rms_delta(images[0][1], start_ref)
    end_rms = rms_delta(images[-1][1], end_ref)
    if start_rms > args.max_endpoint_rms:
        warnings.append(f"first imported frame differs from approved start endpoint: rms={start_rms:.2f}")
    if end_rms > args.max_endpoint_rms:
        warnings.append(f"last imported frame differs from approved end endpoint: rms={end_rms:.2f}")

    deltas = [rms_delta(images[index][1], images[index + 1][1]) for index in range(len(images) - 1)]
    moving_deltas = [value for value in deltas if value >= args.min_motion_rms]
    if not moving_deltas:
        blockers.append("interpolated segment has no meaningful frame-to-frame motion")

    status = "pass" if not blockers else "fail"
    report = {
        "schema_version": "sofunny-interpolated-segment-audit.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "adapter": "tooncrafter",
        "pair_id": args.pair_id,
        "candidate_only": True,
        "production_approved": False,
        "segment_dir": str(segment_dir),
        "frame_count": len(images),
        "endpoint_rms": {"start": start_rms, "end": end_rms},
        "frame_delta_rms": deltas,
        "blockers": blockers,
        "warnings": warnings,
        "next_required_step": "candidate admission or new keypose freeze; never direct production approval",
    }
    write_json(run_dir / "interpolated_segment_audit.json", report)
    print(json.dumps({"status": status, "report": str(run_dir / "interpolated_segment_audit.json")}, ensure_ascii=False, indent=2))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
