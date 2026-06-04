# Action Component Plan

Use this reference to translate an action contract into source-animation part transforms.

## Contents

- Purpose
- Required JSON
- Small Jog MVP
- Phase Semantics
- Loop Rules
- Blocking Conditions

## Purpose

An action component plan binds the action to declared parts. It must exist before source-animation keypose generation.

It answers:

```text
which part moves
when it moves
how far it moves
how it returns to loop start
which parts must stay fixed
```

## Required JSON

`action_component_plan.json`:

```json
{
  "schema_version": "sofunny-action-component-plan.v1",
  "action_name": "small_jog_front",
  "frames": 12,
  "canvas": {"width": 384, "height": 384},
  "background": "#00ff00",
  "phases": [
    {
      "name": "contact_left",
      "frame": 0,
      "acting_intent": "plant and compress before push-off",
      "primary_driver": "left_leg",
      "motion_reason": "tail and head lag the body compression",
      "spacing_curve": "ease_in_out_sine",
      "overlap_group": "tail/head follow torso with offset",
      "body_y": 0,
      "head_y": 1,
      "head_rotation": -1,
      "arm_rotation": 8,
      "leg_phase": "contact",
      "tail_rotation": 5,
      "tail_lag": -0.4,
      "squash_stretch": [1.01, 0.99],
      "optional_expression_variant": null,
      "transforms": {
        "head": {"translate": [0, 1], "rotate": -1},
        "torso": {"translate": [0, 0], "scale": [1.01, 0.99]},
        "left_leg": {"translate": [-5, 0]},
        "right_leg": {"translate": [5, -4]},
        "tail": {"rotate": 5}
      },
      "required_visual_change": "left foot contact, opposite leg lifted, tail lags"
    }
  ],
  "loop": {
    "first_last_match": true,
    "max_loop_delta_px": 2
  }
}
```

## Small Jog MVP

For the MVP, use 12 keyposes:

```text
0 contact_left
1 push_left
2 passing_left
3 airborne_left
4 contact_right
5 push_right
6 passing_right
7 airborne_right
8 contact_left_return
9 settle_up
10 settle_down
11 loop_return
```

The plan may use procedural transforms, but every transform must reference declared parts.

## Phase Semantics

Each phase must include:

- `name`
- `frame`
- `acting_intent`
- `primary_driver`
- `motion_reason`
- `spacing_curve`
- `overlap_group`
- `body_y`
- `head_y`
- `head_rotation`
- `arm_rotation`
- `leg_phase`
- `tail_rotation`
- `tail_lag`
- `squash_stretch`
- `optional_expression_variant`
- `transforms`
- `required_visual_change`

Each transform may include:

- `translate`: `[x, y]` pixels
- `rotate`: degrees
- `scale`: `[x, y]`
- `pivot`: optional named anchor
- `local_redraw_allowed`: boolean, default false

The semantic fields are not decoration. They make the plan auditable before freeze:

- `acting_intent` must state the visible purpose of the phase.
- `primary_driver` must identify the body part or prop causing the phase.
- `motion_reason` must explain why secondary motion exists; random motion is not allowed.
- `spacing_curve` must name the intended curve family for non-linear spacing.
- `overlap_group` must describe which parts lead or lag.
- `body_y` and `head_y` must not be identical across all phases.
- `head_rotation` should show delayed head follow-through when the action allows it.
- `arm_rotation` and `leg_phase` must make limb motion readable for body actions.
- `tail_rotation` and `tail_lag` must show delayed tail response when a tail is declared.
- `squash_stretch` must stay within the movable-parts contract and cannot hide identity drift.
- `optional_expression_variant` may only name an approved variant such as a locked blink; it cannot introduce a new face design.

## Loop Rules

For looping GIFs:

- first and last pose must be visually compatible
- no identity part may change design at the loop
- tail and limbs must return coherently, not snap
- `loop.max_loop_delta_px` must be declared

## Blocking Conditions

Block keypose generation when:

- a phase references an unknown part
- a transform exceeds the movable-part contract
- a fixed identity part is locally redrawn
- acting intent, primary driver, motion reason, or overlap group is missing
- `required_visual_change` is missing
- loop rules are missing for a looping action
