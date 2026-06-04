#!/usr/bin/env python3
"""Import extracted Animate-X video frames as candidate provider frames."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from sofunny_anim.image_io import parse_canvas, remove_background


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_frames(frame_dir: Path) -> list[Path]:
    paths = sorted(frame_dir.expanduser().glob("*.png"))
    if not paths:
        raise ValueError(f"no PNG frames in {frame_dir}; extract Animate-X video to PNG frames first")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--frames-dir", required=True)
    parser.add_argument("--packet", default="")
    parser.add_argument("--output-dir")
    parser.add_argument("--target-canvas", type=parse_canvas)
    parser.add_argument("--background", choices=["none", "transparent", "green", "checker"], default="none")
    parser.add_argument("--expected-min-frames", type=int, default=8)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    frames_dir = Path(args.frames_dir).expanduser().resolve()
    frame_paths = load_frames(frames_dir)
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else run_dir / "animatex_imported_frames"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    packet: dict[str, Any] | None = None
    if args.packet:
        packet_path = Path(args.packet).expanduser().resolve()
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        if packet.get("production_approved") is True:
            raise SystemExit("ANIMATEX_PACKET_CANNOT_BE_PRODUCTION_APPROVED")

    imported = []
    original_sizes = []
    converted_count = 0
    for index, path in enumerate(frame_paths):
        image = Image.open(path).convert("RGBA")
        original_sizes.append(list(image.size))
        if args.background != "none":
            image = remove_background(image, args.background)
        converted = False
        if args.target_canvas and image.size != args.target_canvas:
            image = image.resize(args.target_canvas, Image.Resampling.LANCZOS)
            converted = True
            converted_count += 1
        out = output_dir / f"{index:03d}.png"
        image.save(out)
        imported.append({"index": index, "source": str(path), "file": str(out), "canvas_converted": converted})

    blockers = []
    if len(imported) < args.expected_min_frames:
        blockers.append(f"not enough frames: {len(imported)} < {args.expected_min_frames}")
    status = "pass" if not blockers else "fail"
    report = {
        "schema_version": "sofunny-animatex-import.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "adapter": "animate_x_wan",
        "provider": "animate_x",
        "candidate_only": True,
        "production_approved": False,
        "requires_sofunny_gates": True,
        "source_frames_dir": str(frames_dir),
        "imported_frames_dir": str(output_dir),
        "packet": packet,
        "expected_min_frames": args.expected_min_frames,
        "imported_frame_count": len(imported),
        "background_mode": args.background,
        "original_sizes": original_sizes,
        "target_canvas": list(args.target_canvas) if args.target_canvas else None,
        "converted_frame_count": converted_count,
        "frames": imported,
        "blockers": blockers,
        "next_required_step": "audit_video_provider_frames.py",
    }
    write_json(run_dir / "animatex_import_report.json", report)
    print(json.dumps({"status": status, "frames": len(imported), "report": str(run_dir / "animatex_import_report.json")}, ensure_ascii=False, indent=2))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
