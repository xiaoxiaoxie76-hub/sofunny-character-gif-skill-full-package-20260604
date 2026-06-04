#!/usr/bin/env python3
"""Create a ComfyUI/IPAdapter packet for masked local part repair."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_required(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(str(src))
    shutil.copy2(src, dst)


def mask_stats(path: Path) -> dict[str, Any]:
    image = Image.open(path).convert("L")
    values = list(image.getdata())
    white = sum(1 for value in values if value > 0)
    total = len(values)
    bbox = image.getbbox()
    return {
        "size": list(image.size),
        "coverage_ratio": white / total if total else 0,
        "bbox": list(bbox) if bbox else None,
        "nonzero_pixels": white,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--part-name", required=True)
    parser.add_argument("--failure-reason", required=True)
    parser.add_argument("--failed-frame", required=True)
    parser.add_argument("--part-mask", required=True)
    parser.add_argument("--canonical-reference", required=True)
    parser.add_argument("--previous-frame", default="")
    parser.add_argument("--next-frame", default="")
    parser.add_argument("--output-dir")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--negative-prompt", default="full frame redraw, changed face, changed glasses, changed costume, detached tail, altered unmasked pixels")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else run_dir / "ipadapter_part_repair_packets" / args.part_name
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    failed_frame = Path(args.failed_frame).expanduser().resolve()
    part_mask = Path(args.part_mask).expanduser().resolve()
    canonical = Path(args.canonical_reference).expanduser().resolve()
    copy_required(failed_frame, output_dir / "failed_frame.png")
    copy_required(part_mask, output_dir / "part_mask.png")
    copy_required(canonical, output_dir / "canonical_reference.png")
    optional_files = {}
    for label, value in (("previous_frame", args.previous_frame), ("next_frame", args.next_frame)):
        if value:
            src = Path(value).expanduser().resolve()
            copy_required(src, output_dir / f"{label}.png")
            optional_files[label] = str(output_dir / f"{label}.png")

    prompt = args.prompt or (
        f"Repair only the {args.part_name} inside the provided mask. "
        "Preserve the same character identity and style from the canonical reference. "
        "Do not alter pixels outside the mask."
    )
    (output_dir / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    (output_dir / "negative_prompt.txt").write_text(args.negative_prompt + "\n", encoding="utf-8")
    stats = mask_stats(part_mask)
    if not stats["bbox"]:
        raise SystemExit("IPADAPTER_REPAIR_MASK_EMPTY")
    if stats["coverage_ratio"] > 0.45:
        raise SystemExit("IPADAPTER_REPAIR_MASK_TOO_LARGE: mask suggests full-frame redraw")

    payload = {
        "schema_version": "sofunny-ipadapter-part-repair-packet.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass",
        "adapter": "ipadapter_comfyui",
        "source_run": str(run_dir),
        "part_name": args.part_name,
        "failure_reason": args.failure_reason,
        "candidate_only": True,
        "production_approved": False,
        "full_frame_redraw": False,
        "mask_stats": stats,
        "files": {
            "canonical_reference": str(output_dir / "canonical_reference.png"),
            "failed_frame": str(output_dir / "failed_frame.png"),
            "part_mask": str(output_dir / "part_mask.png"),
            **optional_files,
            "prompt": str(output_dir / "prompt.txt"),
            "negative_prompt": str(output_dir / "negative_prompt.txt"),
        },
        "rules": [
            "Use IPAdapter for reference identity/style conditioning only.",
            "Use the part mask as the repair boundary.",
            "Do not full-frame redraw.",
            "After import, run audit_part_consistency.py.",
        ],
    }
    write_json(output_dir / "ipadapter_part_repair_packet.json", payload)
    (output_dir / "README.md").write_text(
        "# IPAdapter Part Repair Packet\n\n"
        "Repair only the masked part. Output is candidate-only and must be imported with import_ipadapter_part_repair.py.\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "pass", "packet": str(output_dir), "part_name": args.part_name}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
