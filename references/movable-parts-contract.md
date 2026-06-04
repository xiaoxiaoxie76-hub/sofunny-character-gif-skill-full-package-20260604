# Movable Parts Contract

Use this reference when defining which SoFunny character parts may move during source animation.

## Contents

- Purpose
- Required JSON
- Default Small Jog Parts
- Transform Limits
- Attachment Rules
- Blocking Conditions

## Purpose

Movable parts are the only parts allowed to carry action changes. They must be declared before keypose generation.

The animation should move parts, not randomly redraw the full character.

## Required JSON

`movable_parts_contract.json`:

```json
{
  "schema_version": "sofunny-movable-parts.v1",
  "character_name": "beav_buy",
  "movable_parts": [
    {
      "part": "head",
      "motion": ["bob_y", "small_rotation"],
      "max_rotation_deg": 4,
      "max_translation_px": 8,
      "must_remain_attached": true
    }
  ]
}
```

## Default Small Jog Parts

For `small_jog_front`, start with:

```text
head: bob_y, small_rotation
torso: bob_y, squash_stretch
left_arm: swing, counter_motion
right_arm: swing, touch_glasses optional
left_leg: contact, passing, lift
right_leg: contact, passing, lift
tail: lag, small_rotation
```

## Transform Limits

Recommended MVP limits:

```text
head.max_rotation_deg: 4
head.max_translation_px: 8
torso.max_translation_px: 8
arm.max_rotation_deg: 25
leg.max_translation_px: 12
tail.max_rotation_deg: 14
```

These are starting limits, not production proof. If action readability requires more movement, update the contract before generation.

## Attachment Rules

Parts with `must_remain_attached: true` must keep their anchor within the declared threshold.

Typical anchor pairs:

```text
head -> torso
left_arm -> torso
right_arm -> torso
left_leg -> torso
right_leg -> torso
tail -> torso
glasses -> head
face -> head
```

## Blocking Conditions

Block source-animation approval when:

- an action phase moves an undeclared part
- movement exceeds transform limits
- a required attachment breaks
- a part disappears from any keypose
- a fixed identity part is used as a free-moving part without explicit approval

