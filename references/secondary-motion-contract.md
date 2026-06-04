# Secondary Motion Contract

Use this reference after `part_map.json`, `movable_parts_contract.json`, and `action_component_plan.json` exist.

## Contents

- Purpose
- Allowed Secondary Motion
- Forbidden Changes
- Required Inputs
- Required Outputs
- Blocking Conditions

## Purpose

Secondary motion adds life to an already valid primary action without full-frame redraw.

It must preserve identity, style, segmentation, and attachments. It is not a cleanup pass for dirty parts, broken hands, missing tails, or bad layer extraction.

## Allowed Secondary Motion

Allowed only when the part is present and permitted by `movable_parts_contract.json`:

- `head_follow`: small delayed y movement and small rotation.
- `torso_squash_stretch`: subtle squash/stretch inside identity-safe limits.
- `arm_counter_swing`: arms counter the torso or prop action.
- `tail_lag`: tail trails torso/root movement.
- `tail_overshoot`: tail goes slightly past the target before settling.
- `hair_ear_follow_through`: hair or ear tips follow the head with smaller delayed rotation.
- `approved_blink`: a locked expression variant that has already passed identity review.
- `eye_micro_movement`: only if eyes are a declared movable part and the variant is approved.

## Forbidden Changes

Secondary motion must not:

- full-frame redraw
- redesign face shape
- change glasses shape or placement identity
- change outfit design
- recolor the character
- change line weight
- invent missing parts
- repair dirty segmentation
- move a fixed identity part unless it is explicitly declared movable
- detach tail, limbs, ears, hair, or props from their anchor
- hide jitter by adding global placement movement

## Required Inputs

Recommended P0 flow:

```text
action_component_plan.json
movable_parts_contract.json
part_parameter_contract.json
-> generate_part_motion_curves.py
-> part_motion_curves.json
component_keyposes/ or action_component_plan.json
part_map.json
part_motion_curves.json
-> add_secondary_motion_pass.py
```

The pass may modify phase transforms only for declared movable parts.

## Required Outputs

`add_secondary_motion_pass.py` must write:

- updated `action_component_plan.json` or a caller-provided output plan
- `secondary_motion_pass_report.json`

When image keyposes are available and the caller requests a separate output directory, it may write:

- `lively_component_keyposes/`

## Blocking Conditions

Block the pass when:

- `movable_parts_contract.json` is missing
- a requested secondary parameter targets an undeclared part
- a transform exceeds the part limit
- `local_redraw_allowed` is true
- a blink or eye variant is requested without approval
- the pass attempts to change immutable style, color, clothing, glasses, or face design
- the source part is already known dirty by `component_integrity_report.json`
