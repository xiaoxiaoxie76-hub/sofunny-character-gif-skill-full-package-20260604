#!/usr/bin/env python3
"""Create a provider brief by combining character measurement and an action contract."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from measure_character_identity import measure


ROOT = Path(__file__).resolve().parents[1]
ACTION_CONTRACTS = ROOT / "action_contracts"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_action_contract(action: str, action_contract: str | None) -> tuple[dict, Path]:
    path = Path(action_contract).expanduser().resolve() if action_contract else ACTION_CONTRACTS / f"{action}.json"
    if not path.exists():
        raise FileNotFoundError(f"missing action contract: {path}")
    contract = read_json(path)
    if contract.get("schema_version") != "sofunny-action-contract.v1":
        raise ValueError(f"unsupported action contract schema: {path}")
    if contract.get("action") != action:
        raise ValueError(f"action contract mismatch: expected {action}, got {contract.get('action')}")
    return contract, path


def frame_count(contract: dict, requested: int | None) -> int:
    frames = requested if requested is not None else int(contract.get("default_frames") or len(contract.get("phases", [])))
    if frames <= 0:
        raise ValueError("frame count must be positive")
    phases = contract.get("phases", [])
    if phases and len(phases) != frames:
        raise ValueError(f"action contract phase count {len(phases)} does not match requested frames {frames}")
    return frames


def atlas_lines(contract: dict, canvas: str, frames: int) -> list[str]:
    atlas = contract.get("atlas_contract", {})
    layout = atlas.get("layout", "grid")
    rows = atlas.get("rows")
    columns = atlas.get("columns")
    safe_ratio = float(atlas.get("safe_margin_ratio", 0.12))
    return [
        f"target canvas per frame: {canvas}",
        f"frame count: exactly {frames}",
        f"layout: {layout}" + (f", rows={rows}, columns={columns}" if rows and columns else ""),
        f"each character must be centered inside its own cell with at least {safe_ratio:.0%} empty background on all four sides",
        "use visible gutters between cells; never let hair, flowers, hands, clothing, feet, tail, or props touch a cell boundary",
        "no neighbor-frame fragments, duplicate figures, labels, frame numbers, borders, UI, watermark, checkerboard, or accidental transparency",
    ]


def prompt_from_contract(identity: dict, contract: dict, canvas: str, frames: int) -> str:
    phases = contract.get("phases", [])
    phase_lines = "\n".join(
        f"- {int(item.get('frame', index)):02d} {item.get('name', 'phase')}: body={item.get('body', 'follow action contract')}; hands={item.get('hands', 'preserve action semantics')}"
        for index, item in enumerate(phases)
    )
    requirements = "\n".join(f"- {item}" for item in contract.get("hard_requirements", []))
    rejects = "\n".join(f"- {item}" for item in contract.get("reject_if", []))
    preserve = "\n".join(f"- {item}" for item in identity.get("must_preserve", []))
    forbid = "\n".join(f"- {item}" for item in identity.get("forbid", []))
    notes = "\n".join(f"- {item}" for item in identity.get("identity_notes", [])) or "- use the attached canonical image as the source of truth"
    colors = ", ".join(str(item["rgb"]) for item in identity.get("dominant_colors", [])[:6])
    atlas = "\n".join(f"- {item}" for item in atlas_lines(contract, canvas, frames))
    projection = contract.get("projection_contract", {})
    projection_lines = "\n".join(f"- {key}: {value}" for key, value in projection.items())
    local_props = "\n".join(f"- {item}" for item in contract.get("identity_contract", {}).get("preserve_local_proportions", []))

    return f"""Create a SoFunny-style animation candidate sheet from the attached canonical character reference.

Reference rule:
- The canonical image is the hard identity reference.
- Do not invent a similar character.
- Do not paste a static sticker; redraw only what the action requires.
- Preserve local proportions and design details while changing pose according to the action contract.

Measured character identity:
- character_name: {identity.get('character_name')}
- image_size: {identity.get('image_size')}
- visible_bbox: {identity.get('visible_bbox')}
- visible_size: {identity.get('visible_size')}
- visible_aspect_ratio: {identity.get('visible_aspect_ratio')}
- foreground_coverage_ratio: {identity.get('foreground_coverage_ratio')}
- dominant_colors: {colors}

Identity notes:
{notes}

Must preserve:
{preserve}

Forbidden identity drift:
{forbid}

Local proportions to keep stable:
{local_props}

Action:
- action: {contract.get('action')}
- frames: {frames}
- anchor_policy: {contract.get('anchor_policy', 'anchor')}

Projection and physical logic:
{projection_lines}

Frame phases:
{phase_lines}

Atlas and output contract:
{atlas}

Hard requirements:
{requirements}

Reject if:
{rejects}

Important:
The output must satisfy identity measurement, action phases, projection logic, and atlas safety at the same time. If a body appears shorter, wider, cropped, or locally redesigned without an action-projection reason, regenerate the frame instead of hiding the defect with placement or GIF export.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--character-name", required=True)
    parser.add_argument("--action", default="small_jog_front")
    parser.add_argument("--action-contract")
    parser.add_argument("--frames", type=int)
    parser.add_argument("--canvas", default="384x384")
    parser.add_argument("--identity-note", action="append", default=[])
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    reference = Path(args.reference).expanduser().resolve()
    source_dir = run_dir / "source"
    brief_dir = run_dir / "provider_briefs"
    source_dir.mkdir(parents=True, exist_ok=True)
    brief_dir.mkdir(parents=True, exist_ok=True)
    canonical_copy = source_dir / reference.name
    if reference != canonical_copy:
        shutil.copy2(reference, canonical_copy)

    contract, contract_path = load_action_contract(args.action, args.action_contract)
    frames = frame_count(contract, args.frames)
    identity = measure(canonical_copy, args.character_name, args.identity_note)
    identity_path = brief_dir / "identity_measurement.json"
    write_json(identity_path, identity)
    prompt = prompt_from_contract(identity, contract, args.canvas, frames)

    prompt_path = brief_dir / f"{args.action}.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    write_json(
        brief_dir / f"{args.action}.json",
        {
            "schema_version": "sofunny-provider-brief.v2",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "character_name": args.character_name,
            "action": args.action,
            "frames": frames,
            "canvas": args.canvas,
            "canonical_reference": str(canonical_copy),
            "identity_measurement": str(identity_path),
            "action_contract": str(contract_path),
            "prompt_path": str(prompt_path),
            "atlas_contract": contract.get("atlas_contract", {}),
            "anchor_policy": contract.get("anchor_policy", "anchor"),
        },
    )
    print(str(prompt_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
