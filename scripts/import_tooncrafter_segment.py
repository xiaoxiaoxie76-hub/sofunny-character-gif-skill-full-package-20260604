#!/usr/bin/env python3
"""Import ToonCrafter generated frames as a candidate interpolation segment."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from sofunny_anim.image_io import parse_canvas


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_frames(frame_dir: Path) -> list[Path]:
    paths = sorted(frame_dir.expanduser().glob("*.png"))
    if not paths:
        raise ValueError(f"no PNG frames in {frame_dir}; extract ToonCrafter video to PNG frames first")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--pair-id", required=True)
    parser.add_argument("--segment-dir", required=True)
    parser.add_argument("--output-dir")
    parser.add_argument("--target-canvas", type=parse_canvas)
    parser.add_argument("--expected-frames", type=int, default=16)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    source_dir = Path(args.segment_dir).expanduser().resolve()
    paths = load_frames(source_dir)
    target_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else run_dir / "tooncrafter_segments" / args.pair_id
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True)

    imported = []
    original_sizes = []
    for index, path in enumerate(paths):
        image = Image.open(path).convert("RGBA")
        original_sizes.append(list(image.size))
        converted = False
        if args.target_canvas and image.size != args.target_canvas:
            image = image.resize(args.target_canvas, Image.Resampling.LANCZOS)
            converted = True
        out = target_dir / f"{index:03d}.png"
        image.save(out)
        imported.append({"index": index, "source": str(path), "file": str(out), "canvas_converted": converted})

    status = "pass" if len(imported) >= 3 else "fail"
    report = {
        "schema_version": "sofunny-tooncrafter-import.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "adapter": "tooncrafter",
        "pair_id": args.pair_id,
        "candidate_only": True,
        "production_approved": False,
        "source_segment_dir": str(source_dir),
        "imported_segment_dir": str(target_dir),
        "expected_frames": args.expected_frames,
        "imported_frame_count": len(imported),
        "original_sizes": original_sizes,
        "target_canvas": list(args.target_canvas) if args.target_canvas else None,
        "frames": imported,
        "next_required_step": "audit_interpolated_segment.py",
    }
    write_json(run_dir / "tooncrafter_import_report.json", report)
    print(json.dumps({"status": status, "frames": len(imported), "report": str(run_dir / "tooncrafter_import_report.json")}, ensure_ascii=False, indent=2))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
