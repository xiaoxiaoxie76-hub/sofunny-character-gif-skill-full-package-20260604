#!/usr/bin/env python3
"""Create a provider brief for SoFunny action candidate generation."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sofunny_anim.profiles import load_profile

from PIL import Image


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def identity_summary(reference: Path) -> dict:
    image = Image.open(reference).convert("RGBA")
    bbox = image.getbbox()
    return {
        "source": str(reference),
        "image_size": {"width": image.width, "height": image.height},
        "visible_bbox": bbox,
        "identity_notes": [
            "SoFunny chibi beaver businessman character",
            "tan beaver face, brown swept hair tuft, rounded ears",
            "small rectangular black glasses, half-lidded eyes, small muzzle and teeth",
            "black/charcoal suit jacket, white shirt, blue tie",
            "brown striped beaver tail on character right side",
            "large head, small body, clean dark mobile-game icon outline",
        ],
        "must_not_change": [
            "face shape",
            "glasses shape",
            "hair tuft",
            "suit and blue tie",
            "tail shape and stripes",
            "chibi proportions",
            "line-art style",
        ],
    }


def small_jog_front_contract(frames: int) -> dict:
    if frames not in {6, 12}:
        raise ValueError("small_jog_front provider brief supports 6 or 12 frames")
    phases = [
        "left_contact_down",
        "left_push_off",
        "flight_passing_left_to_right",
        "right_contact_down",
        "right_push_off",
        "flight_recover_to_left_contact",
    ]
    if frames == 12:
        phases = [
            "contact_left",
            "down_left",
            "passing_left",
            "up_left",
            "contact_right",
            "down_right",
            "passing_right",
            "up_right",
            "contact_left",
            "settle",
            "recover",
            "loop_return",
        ]
    frame_plan_6 = [
        {
            "frame": 0,
            "phase": "left_contact_down",
            "body": "lowest point, slight compression",
            "legs": "left foot planted under body, right knee lifted/back",
            "arms": "right fist forward, left fist back",
            "tail": "lags to character right/back",
            "shadow": "wider and slightly darker",
        },
        {
            "frame": 1,
            "phase": "left_push_off",
            "body": "rising from compression",
            "legs": "left leg extends, right leg passes forward",
            "arms": "arms crossing toward neutral",
            "tail": "still lagging behind torso",
            "shadow": "starting to narrow",
        },
        {
            "frame": 2,
            "phase": "flight_passing_left_to_right",
            "body": "highest point, no full-foot plant",
            "legs": "both feet separated, clear passing silhouette",
            "arms": "opposite swing from legs",
            "tail": "slight delayed lift",
            "shadow": "narrower/lighter",
        },
        {
            "frame": 3,
            "phase": "right_contact_down",
            "body": "lowest point, mirror of frame 0",
            "legs": "right foot planted, left knee lifted/back",
            "arms": "left fist forward, right fist back",
            "tail": "lags to character right/back",
            "shadow": "wider and slightly darker",
        },
        {
            "frame": 4,
            "phase": "right_push_off",
            "body": "rising from compression",
            "legs": "right leg extends, left leg passes forward",
            "arms": "arms crossing toward neutral",
            "tail": "still lagging behind torso",
            "shadow": "starting to narrow",
        },
        {
            "frame": 5,
            "phase": "flight_recover_to_left_contact",
            "body": "mid-high point, preparing frame 0",
            "legs": "left foot preparing to land, right foot recovering",
            "arms": "preparing to return to frame 0 opposition",
            "tail": "delayed recover",
            "shadow": "narrower/lighter",
        },
    ]
    return {
        "action": "small_jog_front",
        "frames": frames,
        "required_phases": phases,
        "frame_plan": frame_plan_6 if frames == 6 else [],
        "hard_requirements": [
            "front-facing small jog in place",
            "alternating left/right support feet, not random leg variation",
            "visible contact/down/push-off/flight/recover phases",
            "body bounce is subtle and coupled to foot contact",
            "body silhouette and volume remain consistent across all frames",
            "arms oppose legs; fists must not stay symmetrical across frames",
            "tail lags one phase behind body motion but remains fully visible and attached",
            "shadow changes explain contact versus flight",
            "same character identity in every frame",
            "consistent scale and camera",
            "keep generous canvas margin around the right-side tail; no tail crop or flat chopped tail edge",
            "one horizontal row of separated full-body frames",
            "solid #00ff00 background outside the character",
            "no text, labels, frame numbers, borders, panels, or UI",
        ],
        "reject_if": [
            "same legs in every frame",
            "whole-body squash or translation only",
            "speed lines used as a substitute for leg motion",
            "neutral standing frames used as contact frames",
            "symmetrical fists in every frame",
            "body height jumps more than leg action explains",
            "frame 5 does not visibly prepare frame 0",
            "unclear planted foot on contact/down frames",
            "shadow does not match contact or flight",
            "tail detached from body or creates lower-right texture artifacts",
            "tail is cropped, cut off, flattened at the edge, missing stripes, or changes size between frames",
            "body shape changes width/height/volume between frames instead of only posing",
            "face, glasses, suit, tie, or tail identity changes",
            "cropped body or feet",
            "uneven character scale between frames",
        ],
    }


def build_prompt(identity: dict, contract: dict, canvas: str) -> str:
    identity_notes = "; ".join(identity["identity_notes"])
    must_not_change = "; ".join(identity["must_not_change"])
    requirements = "\n".join(f"- {item}" for item in contract["hard_requirements"])
    rejects = "\n".join(f"- {item}" for item in contract["reject_if"])
    phases = " -> ".join(contract["required_phases"])
    frame_plan = "\n".join(
        f"{item['frame']:02d} {item['phase']}: body={item['body']}; legs={item['legs']}; arms={item['arms']}; tail={item['tail']}; shadow={item['shadow']}"
        for item in contract.get("frame_plan", [])
    )
    return f"""Create a SoFunny-style animation candidate sheet from the provided canonical character reference.

Reference rule:
The canonical PNG is a hard character-identity reference, not a static-pose reference and not a sticker to paste. Preserve the character's visual identity and design features while freely redrawing the body, arms, legs, tail angle, and shadow as needed for the jog.

Do not keep the exact still pose. Do not copy the canonical image as a fixed upper-body layer. Animate the whole character as the same character.

Identity lock means:
- keep the same recognizable character features
- keep the same proportions family and SoFunny line style
- keep the same face/glasses/hair/tail/costume design language
- allow pose, limb positions, body bounce, tail lag, and arm swing to change for the action

Do not redesign the face, glasses, muzzle, teeth, hair, ears, suit silhouette, tie, tail size, tail attachment point, tail stripe rhythm, palette, or outline style.

Character identity to preserve exactly:
{identity_notes}

Must not change:
{must_not_change}

Identity anchors that must remain stable in every frame:
- compact original head/face silhouette, not a generic round mascot face
- small thin black glasses placed low over half-lidded eyes
- small symbolic nose/mouth/teeth, no large white muzzle redesign
- original swept brown hair tuft shape and hairline
- small ears embedded into the head silhouette
- narrow charcoal suit body, white shirt, blue tie in the same proportions
- tail attached from character right rear hip, same size range and stripe rhythm; the full tail must stay visible in every frame
- clean SoFunny mobile-game icon line style, no heavier provider-style redraw

Body and tail consistency:
- the character may bounce and pose, but the body must not become wider/narrower or taller/shorter from frame to frame
- suit torso volume, head-to-body ratio, and tail size must remain consistent across the whole sheet
- tail must remain fully inside every 384x384 cell with clear empty margin on the right
- do not crop, flatten, truncate, hide, detach, or redraw the tail as a partial shape

Action:
small_jog_front, {contract['frames']} frames, front-facing jog in place.

Required frame phases:
{phases}

Frame-by-frame motion plan:
{frame_plan}

Canvas and layout:
- target canvas per frame: {canvas}
- one horizontal row of exactly {contract['frames']} separated full-body frames
- consistent character scale and camera across frames
- each cell exactly {canvas}
- solid #00ff00 background outside the character
- no checkerboard, transparency, text, watermark, UI, labels, borders, or frame numbers

Hard requirements:
{requirements}

Reject conditions:
{rejects}
- canonical reference not attached or not used as an image reference
- output is only a similar beaver businessman, not the same character
- generic round-face mascot, thick glasses, large white muzzle, exaggerated teeth, toy-like ears, oversized tail, or redesigned suit

Important:
This must be a real small jog. Do not merely move, squash, paste, or bounce the same static character. Redraw the full body enough to show alternating feet, arm-leg opposition, contact/passing/recover phases, and tail lag while preserving the original SoFunny character identity.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--reference", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--character-name", required=True)
    parser.add_argument("--action", default="small_jog_front")
    parser.add_argument("--frames", type=int, default=12)
    parser.add_argument("--canvas", default="384x384")
    args = parser.parse_args()
    profile = load_profile(args.profile)

    if args.action != "small_jog_front":
        raise ValueError("currently supports --action small_jog_front")

    run_dir = Path(args.run_dir).expanduser().resolve()
    reference = Path(args.reference).expanduser().resolve()
    source_dir = run_dir / "source"
    brief_dir = run_dir / "provider_briefs"
    source_dir.mkdir(parents=True, exist_ok=True)
    brief_dir.mkdir(parents=True, exist_ok=True)
    canonical_copy = source_dir / reference.name
    if reference != canonical_copy:
        shutil.copy2(reference, canonical_copy)

    identity = identity_summary(canonical_copy)
    contract = small_jog_front_contract(args.frames)
    prompt = build_prompt(identity, contract, args.canvas)

    (brief_dir / f"{args.action}.md").write_text(prompt, encoding="utf-8")
    write_json(
        brief_dir / f"{args.action}.json",
        {
            "schema_version": "sofunny-provider-brief.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "character_name": args.character_name,
            "action": args.action,
            "frames": args.frames,
            "canvas": args.canvas,
            "canonical_reference": str(canonical_copy),
            "identity": identity,
            "action_contract": contract,
            "prompt_path": str(brief_dir / f"{args.action}.md"),
        },
    )
    print(str(brief_dir / f"{args.action}.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
