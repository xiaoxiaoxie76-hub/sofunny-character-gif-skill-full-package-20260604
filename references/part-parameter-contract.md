# Part Parameter Contract

Use this reference to turn lively-motion principles into reusable motion curves.

## Contents

- Purpose
- Required JSON
- Parameter Semantics
- Curve Families
- Limits
- Blocking Conditions

## Purpose

Part parameters make SoFunny source animation behave like a simple parameter-driven 2D puppet.

This borrows the structure of systems such as Inochi2D without adding a production dependency: parameters drive part transforms, bounded deformation, and layered composition. The skill owns the contract and the renderer.

## Required JSON

`part_parameter_contract.json`:

```json
{
  "schema_version": "sofunny-part-parameter-contract.v1",
  "parameters": {
    "body_bob": {
      "parts": ["torso"],
      "translate_y_px": [-2, 2],
      "curve": "ease_in_out_sine",
      "phase_offset": 0
    },
    "head_follow": {
      "parts": ["head"],
      "translate_y_px": [-3, 3],
      "rotation_deg": [-2, 2],
      "curve": "ease_out_quad",
      "phase_offset": 0.15
    },
    "tail_lag": {
      "parts": ["tail"],
      "rotation_deg": [-8, 8],
      "curve": "ease_out_back",
      "phase_offset": 0.25,
      "must_remain_attached": true
    },
    "arm_counter_swing": {
      "parts": ["left_arm", "right_arm"],
      "rotation_deg": [-10, 10],
      "curve": "sine_loop",
      "phase_offset": 0.5,
      "mirror_pairs": [["left_arm", "right_arm"]]
    },
    "torso_squash_stretch": {
      "parts": ["torso"],
      "scale_x": [0.985, 1.015],
      "scale_y": [0.985, 1.015],
      "curve": "ease_in_out_sine",
      "phase_offset": 0
    },
    "blink": {
      "parts": ["face"],
      "frames": [9, 10],
      "approved_variant_required": true
    }
  }
}
```

## Parameter Semantics

- `body_bob`: root/body vertical motion coupled to contact and push-off.
- `head_follow`: delayed head reaction, not lockstep torso motion.
- `tail_lag`: delayed tail rotation with attachment preserved.
- `arm_counter_swing`: arms oppose body or prop motion.
- `torso_squash_stretch`: subtle compression/stretch inside identity-safe limits.
- `blink`: optional approved expression variant, never a new face design.

## Curve Families

Supported P0 curves:

- `ease_in_out_sine`
- `ease_out_quad`
- `ease_out_back`
- `overshoot_settle`
- `sine_loop`

The implementation should live in `scripts/sofunny_anim/easing.py`. Do not vendor `tween.js`; port only the small equations needed by this workflow.

## Limits

Every generated curve must be clamped by `movable_parts_contract.json`.

If a parameter exceeds the movable-part limit, the generator must either clamp and report the clamp or fail when `--strict-limits` is used.

## Blocking Conditions

Block curve generation when:

- `parameters` is missing or not an object
- a parameter targets a part not declared in `movable_parts_contract.json`
- a range is not two numeric values
- a curve name is unknown
- `approved_variant_required` is true but no approved variant is available
- a parameter tries to alter color, costume, face design, line weight, or full-frame pixels
