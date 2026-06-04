#!/usr/bin/env python3
"""Create a controlled ToonCrafter packet from an approved keypose pair."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_pair(pairs: dict[str, Any], pair_id: str | None) -> dict[str, Any]:
    items = pairs.get("pairs", [])
    if not items:
        raise ValueError("interpolation_pairs.json has no pairs")
    if not pair_id:
        return items[0]
    for item in items:
        if item.get("pair_id") == pair_id:
            return item
    raise ValueError(f"pair_id not found: {pair_id}")


def copy_or_resize(src: Path, dst: Path, width: int, height: int) -> dict[str, Any]:
    image = Image.open(src).convert("RGBA")
    original_size = image.size
    if image.size != (width, height):
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    image.save(dst)
    return {"source": str(src), "target": str(dst), "original_size": original_size, "packet_size": [width, height]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--pairs", default="interpolation_pairs.json")
    parser.add_argument("--pair-id")
    parser.add_argument("--output-dir")
    parser.add_argument("--target-width", type=int, default=512)
    parser.add_argument("--target-height", type=int, default=320)
    parser.add_argument("--expected-frames", type=int, default=16)
    parser.add_argument("--prompt", default="smooth cartoon interpolation between the two approved keyposes, preserve the same character identity, clean lines")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    pairs_path = Path(args.pairs)
    if not pairs_path.is_absolute():
        pairs_path = run_dir / pairs_path
    pairs = read_json(pairs_path)
    pair = find_pair(pairs, args.pair_id)
    pair_id = pair["pair_id"]
    packet_root = Path(args.output_dir).expanduser().resolve() if args.output_dir else run_dir / "tooncrafter_packets" / pair_id
    if packet_root.exists():
        shutil.rmtree(packet_root)
    packet_root.mkdir(parents=True)

    start = copy_or_resize(Path(pair["start_frame"]), packet_root / "start_frame.png", args.target_width, args.target_height)
    end = copy_or_resize(Path(pair["end_frame"]), packet_root / "end_frame.png", args.target_width, args.target_height)
    (packet_root / "prompt.txt").write_text(args.prompt + "\n", encoding="utf-8")
    (packet_root / "README.md").write_text(
        "\n".join([
            "# ToonCrafter Packet",
            "",
            "Use this packet only for interpolation between approved SoFunny keyposes.",
            "Output is candidate-only and must be re-imported with import_tooncrafter_segment.py.",
            "Do not mark ToonCrafter output as production approved.",
            "",
        ]),
        encoding="utf-8",
    )
    payload = {
        "schema_version": "sofunny-tooncrafter-packet.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass",
        "adapter": "tooncrafter",
        "pair_id": pair_id,
        "candidate_only": True,
        "production_approved": False,
        "expected_frames": args.expected_frames,
        "target_resolution": {"width": args.target_width, "height": args.target_height},
        "prompt": args.prompt,
        "source_pair": pair,
        "packet_files": {
            "start_frame": str(packet_root / "start_frame.png"),
            "end_frame": str(packet_root / "end_frame.png"),
            "prompt": str(packet_root / "prompt.txt"),
        },
        "geometry": {"start": start, "end": end},
        "requirements_after_generation": [
            "import_tooncrafter_segment.py",
            "audit_interpolated_segment.py",
            "candidate admission or new freeze",
            "deterministic GIF export",
            "final admission",
        ],
    }
    write_json(packet_root / "tooncrafter_packet.json", payload)
    print(json.dumps({"status": "pass", "packet": str(packet_root), "pair_id": pair_id}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
