#!/usr/bin/env python3
"""Create a provider-ready packet with hard identity reference and motion guides."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sofunny_anim.profiles import load_profile

from PIL import Image, ImageDraw

from sofunny_anim.manifests import write_json


def draw_pose_guide(path: Path, cell: tuple[int, int]) -> None:
    cell_w, cell_h = cell
    frames = [
        ("left_contact_down", -4, "L", "R", -16, 10),
        ("left_push_off", -1, "L>", "R>", -8, 5),
        ("flight_passing", 5, "L^", "R^", 0, -5),
        ("right_contact_down", -4, "R", "L", 16, 10),
        ("right_push_off", -1, "R>", "L>", 8, 5),
        ("recover", 3, "L?", "R", 0, -2),
    ]
    sheet = Image.new("RGBA", (cell_w * 6, cell_h), (255, 0, 255, 255))
    for i, (phase, body_y, plant, lift, arm_bias, foot_y) in enumerate(frames):
        x0 = i * cell_w
        cx = x0 + cell_w // 2
        ground = cell_h - 44
        head_r = 58
        torso_w = 68
        torso_h = 78
        head_cy = 118 + body_y
        torso_top = head_cy + head_r - 6
        torso_bottom = torso_top + torso_h
        draw = ImageDraw.Draw(sheet)
        # Character mass guide.
        draw.ellipse((cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r), fill=(88, 96, 110, 255), outline=(18, 24, 32, 255), width=3)
        draw.rounded_rectangle((cx - torso_w // 2, torso_top, cx + torso_w // 2, torso_bottom), radius=28, fill=(88, 96, 110, 255), outline=(18, 24, 32, 255), width=3)
        shoulder_y = torso_top + 20
        hand_y = torso_top + 58
        # Opposing arms.
        left_hand = (cx - 55 - max(0, arm_bias), hand_y + max(0, arm_bias // 4))
        right_hand = (cx + 55 - min(0, arm_bias), hand_y - min(0, arm_bias // 4))
        draw.line((cx - 28, shoulder_y, *left_hand), fill=(28, 34, 43, 255), width=9)
        draw.line((cx + 28, shoulder_y, *right_hand), fill=(28, 34, 43, 255), width=9)
        draw.ellipse((left_hand[0] - 8, left_hand[1] - 8, left_hand[0] + 8, left_hand[1] + 8), fill=(110, 118, 130, 255), outline=(18, 24, 32, 255), width=2)
        draw.ellipse((right_hand[0] - 8, right_hand[1] - 8, right_hand[0] + 8, right_hand[1] + 8), fill=(110, 118, 130, 255), outline=(18, 24, 32, 255), width=2)
        # Legs with explicit alternating support.
        hip_y = torso_bottom - 10
        if plant.startswith("L"):
            left_foot = (cx - 18, ground)
            right_foot = (cx + 26, ground - 26 + foot_y)
        else:
            left_foot = (cx - 26, ground - 26 + foot_y)
            right_foot = (cx + 18, ground)
        draw.line((cx - 16, hip_y, *left_foot), fill=(28, 34, 43, 255), width=11)
        draw.line((cx + 16, hip_y, *right_foot), fill=(28, 34, 43, 255), width=11)
        draw.ellipse((left_foot[0] - 15, left_foot[1] - 7, left_foot[0] + 15, left_foot[1] + 7), fill=(28, 34, 43, 255))
        draw.ellipse((right_foot[0] - 15, right_foot[1] - 7, right_foot[0] + 15, right_foot[1] + 7), fill=(28, 34, 43, 255))
        # Tail lag hint.
        tail_cx = cx + 55 - round(arm_bias * 0.25)
        tail_cy = torso_top + 60 - round(body_y * 0.4)
        draw.ellipse((tail_cx, tail_cy, tail_cx + 58, tail_cy + 38), fill=(88, 96, 110, 255), outline=(18, 24, 32, 255), width=3)
        draw.text((x0 + 8, 8), f"{i:02d} {phase}", fill=(0, 0, 0, 255))
        draw.line((x0, ground, x0 + cell_w, ground), fill=(0, 0, 0, 150), width=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def create_anchor_magenta(reference: Path, output: Path, cell: tuple[int, int]) -> None:
    canvas = Image.new("RGBA", cell, (255, 0, 255, 255))
    image = Image.open(reference).convert("RGBA")
    bbox = image.getbbox()
    if bbox is None:
        raise ValueError("reference image has no foreground")
    crop = image.crop(bbox)
    target_height = min(cell[1] - 56, 300)
    scale = target_height / crop.height
    crop = crop.resize((max(1, round(crop.width * scale)), target_height), Image.Resampling.LANCZOS)
    canvas.alpha_composite(crop, ((cell[0] - crop.width) // 2, cell[1] - 28 - crop.height))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)


def write_codex_image_gen_instruction(packet_dir: Path, motion_copies: list[Path]) -> Path:
    motion_tokens = "\n".join(
        f"- @{path.name}: use as MOTION/ACTION REFERENCE ONLY; do not copy identity, face, costume, or proportions from this image."
        for path in motion_copies
    ) or "- no extra motion references"
    instruction = f"""Create one SoFunny `beav_buy small_jog_front` 6-frame candidate sheet.

Reference roles:
- @01_canonical_reference.png: match the EXACT character and style. This owns identity: face shape, small low rectangular glasses, half-lidded eyes, small nose/mouth/teeth, swept brown hair tuft, small ears, narrow charcoal suit, white shirt, blue tie, right-rear striped tail, palette, and SoFunny outline style.
- @02_anchor_magenta.png: identity anchor only. Use it to preserve silhouette, tail placement, suit proportions, and scale. Do not paste it as a static layer.
- @03_small_jog_pose_guide.png: POSE ONLY. Use support foot, arm opposition, body bounce, tail lag, baseline, and phase. Do not copy the grey guide or labels.
{motion_tokens}

Hard instruction:
Match the EXACT character and style from @01_canonical_reference.png. Apply the POSE/MOTION ONLY from the pose and motion references. Do not blend identities.

Output:
- one exact fixed-cell sprite sheet
- full-body frames, each cell exactly 384x384
- solid #00ff00 background outside the character
- no checkerboard, transparency, labels, borders, frame numbers, UI, duplicate figures, or neighbor fragments

Frame phases:
00 left_contact_down
01 left_push_off
02 flight_passing_left_to_right
03 right_contact_down
04 right_push_off
05 flight_recover_to_left_contact

Character identity constraints:
- keep the compact original head/face silhouette, not a generic round mascot face
- keep small thin black glasses placed low over half-lidded eyes
- keep small symbolic nose/mouth/teeth, no large white muzzle redesign
- keep original swept brown hair tuft and hairline direction
- keep small ears embedded into the head silhouette
- keep narrow charcoal suit body, white shirt, and blue tie in the same proportions
- keep the full right-rear striped tail visible in every frame
- keep clean SoFunny mobile-game outline style

Body/tail consistency constraints:
- body silhouette and volume remain consistent across all frames
- suit torso volume and head-to-body ratio do not drift
- full tail remains attached and fully inside every frame
- no cropped tail, cut off tail, flattened tail edge, missing stripes, detached tail, or tail size change
- keep generous empty margin around the right-side tail

Action constraints:
- real front-facing small jog in place
- alternating left/right support feet
- visible contact/down/push-off/flight/recover phases
- arms oppose legs; fists must not stay symmetrical
- tail lags the body motion but remains complete
- shadow changes reflect contact vs flight

Reject if:
- output is merely a similar beaver businessman
- body shape changes width/height/volume between frames
- tail is partial, cropped, hidden, or unstable
- face/glasses/hair/suit/tie/tail identity changes
- same legs in every frame
- whole-body bounce replaces real leg motion
"""
    path = packet_dir / "CODEX_IMAGE_GEN_INSTRUCTION.md"
    path.write_text(instruction, encoding="utf-8")
    return path


def write_codex_image_gen_runner(run_dir: Path, packet_dir: Path, instruction: Path, reference_paths: list[Path]) -> Path:
    output_dir = run_dir / "codex_image_gen_output"
    references = " \\\n  ".join(f'--reference "{path}"' for path in reference_paths)
    script = f"""#!/usr/bin/env bash
set -euo pipefail

node /Users/xiexiaoxiao/.codex-image-gen/codex-image-gen.mjs edit \\
  {references} \\
  --instruction-file "{instruction}" \\
  --generate 1 \\
  --select 1 \\
  --aspect landscape \\
  --name generated_sheet_candidate \\
  --out "{output_dir}"

echo
echo "Inspect the selected output in:"
echo "{output_dir}"
echo
echo "If the output is a clean 6x1 candidate sheet, copy it to:"
echo "{packet_dir / 'generated_sheet.png'}"
echo
echo "Then run:"
echo "python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/run_provider_result_gates.py --run-dir \\"{run_dir}\\""
"""
    path = run_dir / "RUN_CODEX_IMAGE_GEN.sh"
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--brief", required=True)
    parser.add_argument(
        "--motion-reference",
        action="append",
        default=[],
        help="Motion/reference image to attach. Can be passed multiple times. Used for timing/action only, not identity.",
    )
    parser.add_argument("--cell", default="384x384")
    args = parser.parse_args()
    profile = load_profile(args.profile)

    cell = tuple(int(part) for part in args.cell.lower().split("x"))
    if len(cell) != 2:
        raise ValueError("--cell must be WIDTHxHEIGHT")
    run_dir = Path(args.run_dir).expanduser().resolve()
    reference = Path(args.reference).expanduser().resolve()
    brief = Path(args.brief).expanduser().resolve()
    packet_dir = run_dir / "provider_packet"
    packet_dir.mkdir(parents=True, exist_ok=True)

    canonical_copy = packet_dir / "01_canonical_reference.png"
    shutil.copy2(reference, canonical_copy)
    create_anchor_magenta(reference, packet_dir / "02_anchor_magenta.png", cell)
    pose_guide = packet_dir / "03_small_jog_pose_guide.png"
    draw_pose_guide(pose_guide, cell)
    motion_copies = []
    for index, motion_value in enumerate(args.motion_reference, start=1):
        motion_reference = Path(motion_value).expanduser().resolve()
        motion_copy = packet_dir / f"{3 + index:02d}_motion_reference_{motion_reference.name}"
        shutil.copy2(motion_reference, motion_copy)
        motion_copies.append(motion_copy)
    codex_instruction = write_codex_image_gen_instruction(packet_dir, motion_copies)
    codex_runner = write_codex_image_gen_runner(
        run_dir,
        packet_dir,
        codex_instruction,
        [canonical_copy, packet_dir / "02_anchor_magenta.png", pose_guide, *motion_copies],
    )

    brief_text = brief.read_text(encoding="utf-8")
    motion_lines = "\n".join(
        f"{index + 3}. `{path.name}`: motion/action reference only. Use for timing, action readability, body bounce, arm-leg opposition, tail lag, and shadow logic. Do not use as identity."
        for index, path in enumerate(motion_copies, start=1)
    )
    if not motion_lines:
        motion_lines = "4. No extra motion reference was attached. Use the pose guide for action only."
    prompt = f"""Use the attached images in this exact order:

1. `01_canonical_reference.png`: hard character-identity reference. Preserve the character's visual features, proportions, face, glasses, hair, suit, tie, and tail. Do not freeze the pose.
2. `02_anchor_magenta.png`: keyed identity reference on magenta. Use it to understand silhouette, face, glasses, suit, tie, and tail. Do not paste it as a static layer.
3. `03_small_jog_pose_guide.png`: structural motion guide. Use it for pose, support foot, arm opposition, tail lag, baseline, and phase only. Do not draw the grey guide.
{motion_lines}

Generate one sprite candidate sheet:

- 6 frames in a 6x1 horizontal row for smoke. Use `create_provider_brief.py --frames 12` for production keypose briefs.
- each cell: {args.cell}
- full sheet: {cell[0] * 6}x{cell[1]}
- solid #00ff00 background outside the character
- no checkerboard, transparency, text, labels, borders, panels, frame numbers, UI, duplicate figures, or neighbor fragments

{brief_text}

After generation, save the provider output as:

`{packet_dir / 'generated_sheet.png'}`

Then run provider preflight and the SoFunny gates:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/preflight_provider_output.py \\
  --input "{packet_dir / 'generated_sheet.png'}" \\
  --run-dir "{run_dir}" \\
  --expected-frames 6 \\
  --canvas {args.cell}

python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/run_provider_result_gates.py \\
  --run-dir "{run_dir}" --frames 6 --canvas {args.cell}
```
"""
    (packet_dir / "PROVIDER_PROMPT.md").write_text(prompt, encoding="utf-8")
    write_json(
        packet_dir / "action_phase_review.template.json",
        {
            "schema_version": "sofunny-action-phase-review.v1",
            "action": "small_jog_front",
            "status": "manual_required",
            "reviewer": "",
            "frames": [
                {
                    "frame": index,
                    "expected_phase": phase,
                    "phase_pass": False,
                    "identity_pass": False,
                    "notes": "",
                }
                for index, phase in enumerate(
                    [
                        "left_contact_down",
                        "left_push_off",
                        "flight_passing_left_to_right",
                        "right_contact_down",
                        "right_push_off",
                        "flight_recover_to_left_contact",
                    ]
                )
            ],
            "required_global_checks": {
                "arm_leg_opposition": False,
                "tail_lag": False,
                "shadow_contact_logic": False,
                "frame_5_loops_to_frame_0": False,
                "same_character_all_frames": False,
            },
            "pass_rule": "Set status=pass only when every frame and global check is true after direct visual review.",
        },
    )
    write_json(
        packet_dir / "provider_packet_manifest.json",
        {
            "schema_version": "sofunny-provider-packet.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "reference": str(canonical_copy),
            "anchor_magenta": str(packet_dir / "02_anchor_magenta.png"),
            "pose_guide": str(pose_guide),
            "motion_references": [str(path) for path in motion_copies],
            "prompt": str(packet_dir / "PROVIDER_PROMPT.md"),
            "codex_image_gen_instruction": str(codex_instruction),
            "codex_image_gen_runner": str(codex_runner),
            "action_phase_review_template": str(packet_dir / "action_phase_review.template.json"),
            "expected_output": str(packet_dir / "generated_sheet.png"),
            "reference_required_for_generation": True,
        },
    )
    print(str(packet_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
