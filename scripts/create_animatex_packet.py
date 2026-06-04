#!/usr/bin/env python3
"""Create a controlled Animate-X packet for large full-body action candidates."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


SUPPORTED_ACTIONS = {
    "large_full_body_action",
    "dance",
    "jump",
    "run_large_body_motion",
    "complex_dynamic_pose",
}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_required(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(str(src))
    shutil.copy2(src, dst)


def image_size(path: Path) -> list[int]:
    image = Image.open(path)
    return [image.width, image.height]


def fail(code: str, details: str = "") -> int:
    print(code + (f": {details}" if details else ""))
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--canonical-reference", required=True)
    parser.add_argument("--motion-video", default="")
    parser.add_argument("--motion-reference", default="")
    parser.add_argument("--action", default="large_full_body_action")
    parser.add_argument("--deidentified-motion", action="store_true")
    parser.add_argument("--output-dir")
    parser.add_argument("--prompt", default="animate the same character with large full-body motion; preserve identity, costume, proportions, and clean cartoon line art")
    parser.add_argument("--target-width", type=int, default=768)
    parser.add_argument("--target-height", type=int, default=512)
    parser.add_argument("--expected-frames", type=int, default=32)
    args = parser.parse_args()

    if args.action not in SUPPORTED_ACTIONS:
        return fail("ANIMATEX_UNSUPPORTED_ACTION", args.action)
    if not args.deidentified_motion:
        return fail("ANIMATEX_REQUIRES_DEIDENTIFIED_MOTION")
    if bool(args.motion_video) == bool(args.motion_reference):
        return fail("ANIMATEX_REQUIRES_EXACTLY_ONE_MOTION_SOURCE", "use --motion-video or --motion-reference")
    if args.target_width <= 0 or args.target_height <= 0 or args.expected_frames <= 0:
        return fail("ANIMATEX_INVALID_TARGETS")

    run_dir = Path(args.run_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else run_dir / "animatex_packets" / args.action
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    canonical = Path(args.canonical_reference).expanduser().resolve()
    motion_source = Path(args.motion_video or args.motion_reference).expanduser().resolve()
    copy_required(canonical, output_dir / "canonical_reference.png")
    motion_name = "motion_video" + motion_source.suffix if args.motion_video else "motion_reference" + motion_source.suffix
    copy_required(motion_source, output_dir / motion_name)

    (output_dir / "prompt.txt").write_text(args.prompt + "\n", encoding="utf-8")
    (output_dir / "README.md").write_text(
        "\n".join([
            "# Animate-X Packet",
            "",
            "Use this packet only for large full-body action video candidates.",
            "Motion input must already be de-identified or pose-only.",
            "After Animate-X execution, extract the output video to PNG frames and import with import_animatex_video_frames.py.",
            "Output is candidate-only and cannot be marked production approved.",
            "",
        ]),
        encoding="utf-8",
    )

    payload = {
        "schema_version": "sofunny-animatex-packet.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass",
        "adapter": "animate_x_wan",
        "provider": "animate_x",
        "source_run": str(run_dir),
        "action": args.action,
        "candidate_only": True,
        "production_approved": False,
        "requires_reimport": True,
        "requires_sofunny_gates": True,
        "direct_gif_export_allowed": False,
        "deidentified_motion": True,
        "expected_frames": args.expected_frames,
        "target_resolution": {"width": args.target_width, "height": args.target_height},
        "prompt": args.prompt,
        "files": {
            "canonical_reference": str(output_dir / "canonical_reference.png"),
            "motion_source": str(output_dir / motion_name),
            "prompt": str(output_dir / "prompt.txt"),
        },
        "geometry": {
            "canonical_reference_size": image_size(canonical),
        },
        "requirements_after_generation": [
            "extract Animate-X output video to PNG frames",
            "import_animatex_video_frames.py",
            "audit_video_provider_frames.py",
            "provider/source preflight",
            "keypose admission",
            "keypose freeze",
            "locked GIF export",
            "final admission",
        ],
        "prohibited": [
            "direct transparent GIF export",
            "production_approved true",
            "full-frame identity repair",
            "prompt polishing after repeated same-class failures",
        ],
    }
    write_json(output_dir / "animatex_packet.json", payload)
    print(json.dumps({"status": "pass", "packet": str(output_dir), "action": args.action}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
