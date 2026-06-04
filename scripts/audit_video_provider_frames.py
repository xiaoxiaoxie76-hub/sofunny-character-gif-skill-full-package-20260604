#!/usr/bin/env python3
"""Audit imported video-provider frames before SoFunny admission or freeze."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat


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


def is_nonblank(image: Image.Image) -> bool:
    alpha = image.getchannel("A")
    if alpha.getbbox() is None:
        return False
    return image.getbbox() is not None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--frame-dir", default="")
    parser.add_argument("--import-report", default="")
    parser.add_argument("--min-frames", type=int, default=8)
    parser.add_argument("--min-motion-rms", type=float, default=1.0)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    frame_dir = Path(args.frame_dir).expanduser().resolve() if args.frame_dir else run_dir / "animatex_imported_frames"
    images = load_images(frame_dir)
    import_report: dict[str, Any] | None = None
    if args.import_report:
        import_report = json.loads(Path(args.import_report).expanduser().resolve().read_text(encoding="utf-8"))
        if import_report.get("production_approved") is True:
            raise SystemExit("VIDEO_PROVIDER_IMPORT_CANNOT_BE_PRODUCTION_APPROVED")

    blockers: list[str] = []
    warnings: list[str] = []
    if len(images) < args.min_frames:
        blockers.append(f"not enough provider frames: {len(images)} < {args.min_frames}")

    sizes = sorted({image.size for _, image in images})
    if len(sizes) != 1:
        blockers.append("inconsistent frame sizes: " + ", ".join(f"{w}x{h}" for w, h in sizes))

    blank = [str(path) for path, image in images if not is_nonblank(image)]
    if blank:
        blockers.append("blank provider frames: " + ", ".join(blank))

    deltas = [rms_delta(images[index][1], images[index + 1][1]) for index in range(len(images) - 1)]
    moving_deltas = [value for value in deltas if value >= args.min_motion_rms]
    if len(images) > 1 and not moving_deltas:
        blockers.append("provider frames have no meaningful frame-to-frame motion")
    if len(moving_deltas) < max(1, len(deltas) // 3):
        warnings.append("provider frame motion is sparse; action admission must verify semantics")

    status = "pass" if not blockers else "fail"
    report = {
        "schema_version": "sofunny-video-provider-frame-audit.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "adapter": "animate_x_wan",
        "provider": "animate_x",
        "candidate_only": True,
        "production_approved": False,
        "requires_sofunny_gates": True,
        "frame_dir": str(frame_dir),
        "frame_count": len(images),
        "sizes": [list(size) for size in sizes],
        "frame_delta_rms": deltas,
        "blockers": blockers,
        "warnings": warnings,
        "import_report": import_report,
        "next_required_step": "provider/source preflight, keypose admission, freeze, locked GIF export, final admission",
    }
    write_json(run_dir / "video_provider_frame_audit.json", report)
    print(json.dumps({"status": status, "report": str(run_dir / "video_provider_frame_audit.json")}, ensure_ascii=False, indent=2))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
