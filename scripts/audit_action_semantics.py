#!/usr/bin/env python3
"""Audit action-specific semantic metrics against an action contract."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ACTION_CONTRACTS = ROOT / "action_contracts"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_frames(run_dir: Path) -> list[Image.Image]:
    paths = sorted((run_dir / "sequence_frames").glob("*.png"))
    if not paths:
        paths = sorted((run_dir / "accepted_keyposes").glob("*.png"))
    if not paths:
        raise ValueError(f"no sequence_frames or accepted_keyposes found in {run_dir}")
    return [Image.open(path).convert("RGBA") for path in paths]


def bbox_metrics(frame: Image.Image) -> dict:
    bbox = frame.getbbox()
    if bbox is None:
        return {"bbox": None}
    left, top, right, bottom = bbox
    return {
        "bbox": [left, top, right, bottom],
        "width": right - left,
        "height": bottom - top,
        "bottom": bottom,
        "center_y": round((top + bottom) / 2, 2),
    }


def gentle_bow_audit(frames: list[Image.Image], contract: dict) -> tuple[list[str], dict]:
    failures: list[str] = []
    metrics = [bbox_metrics(frame) for frame in frames]
    if any(item.get("bbox") is None for item in metrics):
        return ["empty frame in action sequence"], {"frames": metrics}
    heights = [int(item["height"]) for item in metrics]
    bottoms = [int(item["bottom"]) for item in metrics]
    audit = contract.get("semantic_audit", {}).get("height_curve", {})
    max_ratio = float(audit.get("max_adjacent_height_delta_ratio", 0.06))
    standing_lock_frames = [idx for idx in audit.get("standing_lock_frames", []) if idx < len(heights)]
    max_standing_ratio = float(audit.get("max_standing_height_delta_ratio", 0.02))
    adjacent = [
        round(abs(heights[index] - heights[index - 1]) / max(1, heights[index - 1]), 6)
        for index in range(1, len(heights))
    ]
    excessive = [index + 1 for index, value in enumerate(adjacent) if value > max_ratio]
    if excessive:
        failures.append(f"adjacent height delta exceeds contract at frames: {excessive}")
    if len(standing_lock_frames) >= 2:
        first = heights[standing_lock_frames[0]]
        locked_excessive = [
            index
            for index in standing_lock_frames[1:]
            if abs(heights[index] - first) / max(1, first) > max_standing_ratio
        ]
        if locked_excessive:
            failures.append(f"standing lock height drift exceeds contract at frames: {locked_excessive}")
    if max(bottoms) - min(bottoms) > 2:
        failures.append(f"bottom anchor range {max(bottoms) - min(bottoms)}px exceeds 2px")
    down_frames = [idx for idx in audit.get("down_frames", []) if idx < len(heights)]
    up_frames = [idx for idx in audit.get("up_frames", []) if idx < len(heights)]
    if down_frames and heights[down_frames[-1]] >= heights[down_frames[0]]:
        failures.append("bow-down height curve did not decrease")
    if up_frames and heights[up_frames[-1]] <= heights[up_frames[0]]:
        failures.append("rise height curve did not increase")
    report = {
        "height_values": heights,
        "bottom_values": bottoms,
        "adjacent_height_delta_ratios": adjacent,
        "max_adjacent_height_delta_ratio": max(adjacent) if adjacent else 0,
        "allowed_adjacent_height_delta_ratio": max_ratio,
        "standing_lock_frames": standing_lock_frames,
        "max_standing_height_delta_ratio": max_standing_ratio,
        "bottom_range_px": max(bottoms) - min(bottoms),
        "manual_review_required": {
            "hand_phase_review": bool(contract.get("semantic_audit", {}).get("hand_phase_review_required", False)),
            "expected_hand_states": contract.get("semantic_audit", {}).get("expected_hand_states", {}),
            "reason": "hand joining/release cannot be reliably proven without hand keypoints or manual annotation",
        },
        "frames": metrics,
    }
    return failures, report


def near_constant_height_audit(frames: list[Image.Image], contract: dict) -> tuple[list[str], dict]:
    failures: list[str] = []
    metrics = [bbox_metrics(frame) for frame in frames]
    if any(item.get("bbox") is None for item in metrics):
        return ["empty frame in action sequence"], {"frames": metrics}
    heights = [int(item["height"]) for item in metrics]
    bottoms = [int(item["bottom"]) for item in metrics]
    audit = contract.get("semantic_audit", {}).get("height_curve", {})
    max_adjacent_ratio = float(audit.get("max_adjacent_height_delta_ratio", 0.065))
    max_total_ratio = float(audit.get("max_total_height_range_ratio", 0.08))
    adjacent = [
        round(abs(heights[index] - heights[index - 1]) / max(1, heights[index - 1]), 6)
        for index in range(1, len(heights))
    ]
    excessive = [index + 1 for index, value in enumerate(adjacent) if value > max_adjacent_ratio]
    if excessive:
        failures.append(f"adjacent height delta exceeds contract at frames: {excessive}")
    total_range_ratio = round((max(heights) - min(heights)) / max(1, max(heights)), 6)
    if total_range_ratio > max_total_ratio:
        failures.append(f"total height range ratio {total_range_ratio} exceeds {max_total_ratio}")
    if max(bottoms) - min(bottoms) > 2:
        failures.append(f"bottom anchor range {max(bottoms) - min(bottoms)}px exceeds 2px")
    report = {
        "height_values": heights,
        "bottom_values": bottoms,
        "adjacent_height_delta_ratios": adjacent,
        "max_adjacent_height_delta_ratio": max(adjacent) if adjacent else 0,
        "allowed_adjacent_height_delta_ratio": max_adjacent_ratio,
        "total_height_range_ratio": total_range_ratio,
        "allowed_total_height_range_ratio": max_total_ratio,
        "bottom_range_px": max(bottoms) - min(bottoms),
        "manual_review_required": {
            "hand_phase_review": bool(contract.get("semantic_audit", {}).get("hand_phase_review_required", False)),
            "expected_hand_states": contract.get("semantic_audit", {}).get("expected_hand_states", {}),
            "reason": "hand joining/release cannot be reliably proven without hand keypoints or manual annotation",
        },
        "frames": metrics,
    }
    return failures, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--action-contract")
    parser.add_argument("--output")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    contract_path = Path(args.action_contract).expanduser().resolve() if args.action_contract else ACTION_CONTRACTS / f"{args.action}.json"
    contract = read_json(contract_path)
    if contract.get("action") != args.action:
        raise ValueError(f"action contract mismatch: expected {args.action}, got {contract.get('action')}")
    frames = load_frames(run_dir)
    if args.action == "gentle_bow_flower_sway":
        failures, metrics = gentle_bow_audit(frames, contract)
    elif args.action == "stable_greeting_idle":
        failures, metrics = near_constant_height_audit(frames, contract)
    else:
        failures = [f"no semantic auditor registered for action: {args.action}"]
        metrics = {}
    status = "pass" if not failures else "fail"
    payload = {
        "schema_version": "sofunny-action-semantics-report.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "action": args.action,
        "action_contract": str(contract_path),
        "frame_count": len(frames),
        "failures": failures,
        "metrics": metrics,
        "notes": [
            "Pixel metrics can check height curve and bottom anchor.",
            "Hand semantics require hand-keypoint adapter output or manual phase review.",
        ],
    }
    output = Path(args.output).expanduser().resolve() if args.output else run_dir / "action_semantics_report.json"
    write_json(output, payload)
    print(json.dumps({"status": status, "report": str(output), "failures": failures}, ensure_ascii=False, indent=2))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
