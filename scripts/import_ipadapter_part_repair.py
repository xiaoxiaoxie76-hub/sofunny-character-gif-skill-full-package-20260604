#!/usr/bin/env python3
"""Import a ComfyUI/IPAdapter local part repair while preserving unmasked pixels."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def load_mask(path: Path, size: tuple[int, int]) -> Image.Image:
    mask = Image.open(path).convert("L")
    if mask.size != size:
        mask = mask.resize(size, Image.Resampling.NEAREST)
    return mask


def unmasked_delta(original: Image.Image, result: Image.Image, mask: Image.Image) -> int:
    inv = ImageChops.invert(mask)
    diff = ImageChops.difference(original.convert("RGBA"), result.convert("RGBA"))
    alpha = diff.convert("L")
    outside = ImageChops.multiply(alpha, inv)
    return sum(1 for value in outside.getdata() if value > 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--packet-dir", required=True)
    parser.add_argument("--repair-output", required=True)
    parser.add_argument("--output-frame", default="")
    parser.add_argument("--part-name", default="")
    parser.add_argument("--max-unmasked-delta-pixels", type=int, default=0)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    packet_dir = Path(args.packet_dir).expanduser().resolve()
    failed_frame_path = packet_dir / "failed_frame.png"
    mask_path = packet_dir / "part_mask.png"
    if not failed_frame_path.exists() or not mask_path.exists():
        raise SystemExit("IPADAPTER_REPAIR_PACKET_INCOMPLETE")

    failed = load_rgba(failed_frame_path)
    repair = load_rgba(Path(args.repair_output).expanduser().resolve())
    if repair.size != failed.size:
        repair = repair.resize(failed.size, Image.Resampling.LANCZOS)
    mask = load_mask(mask_path, failed.size)
    composited = Image.composite(repair, failed, mask)

    out_path = Path(args.output_frame).expanduser().resolve() if args.output_frame else run_dir / "ipadapter_repaired_frames" / (args.part_name or "part_repair") / "repaired_frame.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    composited.save(out_path)

    delta = unmasked_delta(failed, composited, mask)
    status = "pass" if delta <= args.max_unmasked_delta_pixels else "fail"
    report = {
        "schema_version": "sofunny-ipadapter-part-repair-import.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "adapter": "ipadapter_comfyui",
        "candidate_only": True,
        "production_approved": False,
        "full_frame_redraw": False,
        "part_name": args.part_name or None,
        "packet_dir": str(packet_dir),
        "repair_output": str(Path(args.repair_output).expanduser().resolve()),
        "output_frame": str(out_path),
        "unmasked_delta_pixels": delta,
        "max_unmasked_delta_pixels": args.max_unmasked_delta_pixels,
        "next_required_step": "rerun validate_part_map/generate_component_keyposes if source parts changed, then audit_part_consistency.py",
        "blockers": [] if status == "pass" else ["unmasked pixels changed; possible full-frame redraw"],
    }
    write_json(run_dir / "ipadapter_part_repair_import_report.json", report)
    print(json.dumps({"status": status, "report": str(run_dir / "ipadapter_part_repair_import_report.json"), "output_frame": str(out_path)}, ensure_ascii=False, indent=2))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
