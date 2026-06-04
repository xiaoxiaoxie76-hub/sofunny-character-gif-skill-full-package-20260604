#!/usr/bin/env python3
"""Build approved keypose pairs for ToonCrafter-style interpolation."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def manifest_frame_paths(run_dir: Path, manifest: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for frame in manifest.get("frames", []):
        value = frame.get("file")
        if not value:
            continue
        path = Path(value)
        paths.append(path if path.is_absolute() else run_dir / path)
    if not paths:
        accepted_dir = Path(manifest.get("accepted_keyposes", run_dir / "accepted_keyposes"))
        if not accepted_dir.is_absolute():
            accepted_dir = run_dir / accepted_dir
        paths = sorted(accepted_dir.glob("*.png"))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--manifest", default="keypose_freeze_manifest.json")
    parser.add_argument("--output", default="interpolation_pairs.json")
    parser.add_argument("--include-loop-pair", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = run_dir / manifest_path
    if not manifest_path.exists():
        raise SystemExit("TOONCRAFTER_REQUIRES_APPROVED_KEYPOSES: missing keypose_freeze_manifest.json")

    manifest = read_json(manifest_path)
    frames = manifest_frame_paths(run_dir, manifest)
    if len(frames) < 2:
        raise SystemExit("TOONCRAFTER_REQUIRES_APPROVED_KEYPOSES: need at least two approved keyposes")
    missing = [str(path) for path in frames if not path.exists()]
    if missing:
        raise SystemExit("TOONCRAFTER_REQUIRES_APPROVED_KEYPOSES: missing frames: " + ", ".join(missing))

    pairs = []
    pair_indices = [(index, index + 1) for index in range(len(frames) - 1)]
    if args.include_loop_pair and len(frames) > 2:
        pair_indices.append((len(frames) - 1, 0))
    for start, end in pair_indices:
        start_path = frames[start]
        end_path = frames[end]
        pairs.append({
            "pair_id": f"pair_{start:03d}_{end:03d}",
            "start_index": start,
            "end_index": end,
            "start_frame": str(start_path),
            "end_frame": str(end_path),
            "start_sha256": sha256(start_path),
            "end_sha256": sha256(end_path),
            "endpoint_status": "approved_frozen_keypose",
            "candidate_only": True,
            "adapter": "tooncrafter",
            "freeze_required_after_import": True,
            "admission_required_after_import": True,
        })

    payload = {
        "schema_version": "sofunny-interpolation-pairs.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass",
        "run_dir": str(run_dir),
        "source_manifest": str(manifest_path),
        "frame_count": len(frames),
        "pair_count": len(pairs),
        "candidate_only": True,
        "pairs": pairs,
    }
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = run_dir / output_path
    write_json(output_path, payload)
    print(json.dumps({"status": "pass", "pairs": len(pairs), "output": str(output_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
