#!/usr/bin/env python3
"""Create a pose-animation adapter packet for external motion/pose tools."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from measure_character_identity import measure


ROOT = Path(__file__).resolve().parents[1]
ACTION_CONTRACTS = ROOT / "action_contracts"


ADAPTER_NOTES = {
    "mmpose_dwpose": {
        "role": "pose_extraction",
        "output": "pose_only_guides",
        "next": "use pose guides as provider conditioning; this adapter does not output final art",
    },
    "animate_anyone": {
        "role": "pose_conditioned_animation",
        "output": "candidate_video_or_frames",
        "next": "extract PNG frames and re-import through SoFunny gates",
    },
    "magic_animate": {
        "role": "densepose_conditioned_animation",
        "output": "candidate_video_or_frames",
        "next": "extract PNG frames and re-import through SoFunny gates",
    },
}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def copy_optional(source: str | None, output_dir: Path, name: str) -> str | None:
    if not source:
        return None
    src = Path(source).expanduser().resolve()
    dst = output_dir / name
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)
    return str(dst)


def command_templates(adapter: str, packet_dir: Path, frames: int, canvas: str) -> dict:
    if adapter == "mmpose_dwpose":
        return {
            "purpose": "extract whole-body and hand keypoints from motion_reference into pose-only guides",
            "template": [
                "Run MMPose/DWPose on motion_reference/* or motion_reference video.",
                f"Export exactly {frames} pose guide PNGs into {packet_dir / 'pose_guides'} at canvas {canvas}.",
                "Each guide must contain body, hand, face, and foot keypoints only; no donor identity pixels.",
            ],
        }
    if adapter in {"animate_anyone", "magic_animate"}:
        return {
            "purpose": "animate canonical character from pose guide sequence",
            "template": [
                f"Use {packet_dir / 'canonical_reference.png'} as the reference character.",
                f"Use pose guides from {packet_dir / 'pose_guides'} or adapter-specific motion condition.",
                f"Export exactly {frames} PNG frames or a video that can be extracted to exactly {frames} frames.",
                "Do not crop character; preserve atlas safe margins and character local proportions.",
                f"After execution, place frames in {packet_dir / 'adapter_output_frames'} or sheet at {packet_dir / 'generated_sheet.png'}.",
            ],
        }
    raise ValueError(f"unsupported adapter: {adapter}")


def build_prompt(identity: dict, contract: dict, adapter: str, frames: int, canvas: str) -> str:
    phases = "\n".join(
        f"- {int(phase.get('frame', index)):02d} {phase.get('name')}: body={phase.get('body')}; hands={phase.get('hands')}"
        for index, phase in enumerate(contract.get("phases", []))
    )
    return f"""Pose adapter packet for {contract.get('action')} using {adapter}.

Character reference:
- source: canonical_reference.png
- measured visible_bbox: {identity.get('visible_bbox')}
- measured visible_size: {identity.get('visible_size')}
- dominant_colors: {[item.get('rgb') for item in identity.get('dominant_colors', [])[:6]]}

Action contract:
- frames: {frames}
- canvas: {canvas}
- anchor_policy: {contract.get('anchor_policy')}
- projection_contract: {contract.get('projection_contract')}

Required phases:
{phases}

Adapter objective:
- preserve the measured character identity and local proportions
- use pose/action condition to enforce real motion timing
- keep safe atlas margins and stable bottom baseline
- output candidate frames only; SoFunny gates decide acceptance
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--character-name", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--adapter", choices=sorted(ADAPTER_NOTES), required=True)
    parser.add_argument("--motion-reference")
    parser.add_argument("--pose-guides")
    parser.add_argument("--action-contract")
    parser.add_argument("--frames", type=int)
    parser.add_argument("--canvas", default="512x512")
    parser.add_argument("--identity-note", action="append", default=[])
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    packet_dir = run_dir / "pose_adapter_packet" / args.adapter
    packet_dir.mkdir(parents=True, exist_ok=True)
    reference = Path(args.reference).expanduser().resolve()
    canonical = packet_dir / "canonical_reference.png"
    shutil.copy2(reference, canonical)
    motion_copy = copy_optional(args.motion_reference, packet_dir, "motion_reference") if args.motion_reference else None
    pose_copy = copy_optional(args.pose_guides, packet_dir, "pose_guides") if args.pose_guides else None

    contract_path = Path(args.action_contract).expanduser().resolve() if args.action_contract else ACTION_CONTRACTS / f"{args.action}.json"
    contract = read_json(contract_path)
    frames = args.frames if args.frames is not None else int(contract.get("default_frames") or len(contract.get("phases", [])))
    if contract.get("action") != args.action:
        raise ValueError(f"action contract mismatch: expected {args.action}, got {contract.get('action')}")
    identity = measure(canonical, args.character_name, args.identity_note)
    write_json(packet_dir / "identity_measurement.json", identity)
    prompt = build_prompt(identity, contract, args.adapter, frames, args.canvas)
    (packet_dir / "ADAPTER_PROMPT.md").write_text(prompt, encoding="utf-8")
    import_commands = {
        "frames": f"python3 {ROOT / 'scripts' / 'import_video_provider_frames.py'} --run-dir {run_dir} --frames-dir {packet_dir / 'adapter_output_frames'} --target-canvas {args.canvas}",
        "sheet": f"python3 {ROOT / 'scripts' / 'import_candidate_sheet.py'} --input {packet_dir / 'generated_sheet.png'} --run-dir {run_dir} --frames {frames} --canvas {args.canvas} --layout grid --rows {contract.get('atlas_contract', {}).get('rows', 1)} --columns {contract.get('atlas_contract', {}).get('columns', frames)} --placement-mode {contract.get('anchor_policy', 'anchor')} --min-source-cell-margin 12 --source-margin-policy fail --max-adjacent-height-ratio {contract.get('projection_contract', {}).get('max_adjacent_height_delta_ratio', 1.0)} --proportion-policy fail --action {args.action} --character-name {args.character_name}",
    }
    manifest = {
        "schema_version": "sofunny-pose-adapter-packet.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "adapter": args.adapter,
        "adapter_role": ADAPTER_NOTES[args.adapter],
        "character_name": args.character_name,
        "action": args.action,
        "frames": frames,
        "canvas": args.canvas,
        "canonical_reference": str(canonical),
        "motion_reference": motion_copy,
        "pose_guides": pose_copy,
        "identity_measurement": str(packet_dir / "identity_measurement.json"),
        "action_contract": str(contract_path),
        "adapter_prompt": str(packet_dir / "ADAPTER_PROMPT.md"),
        "command_templates": command_templates(args.adapter, packet_dir, frames, args.canvas),
        "expected_outputs": {
            "pose_guides": str(packet_dir / "pose_guides"),
            "adapter_output_frames": str(packet_dir / "adapter_output_frames"),
            "generated_sheet": str(packet_dir / "generated_sheet.png"),
        },
        "return_to_sofunny_gates": import_commands,
        "candidate_only": True,
    }
    write_json(packet_dir / "pose_adapter_packet.json", manifest)
    print(json.dumps({"status": "pass", "packet": str(packet_dir / "pose_adapter_packet.json")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
