# Lively Motion Principles

Use this reference before `action_component_plan.json` and before any secondary motion pass.

## Contents

- Purpose
- Required Principles
- Rejection Rules
- Planning Fields
- Provider Boundary
- Audit Boundary

## Purpose

Stable identity is not the same as living animation.

Production source animation must show intentional acting: a primary action with cause and result, plus bounded secondary motion that follows the character's body mechanics. The goal is to prevent a stable character from becoming a mechanical stack of moving layers.

This layer sits before numeric audit:

```text
action intent
-> lively-motion-principles
-> action_component_plan.json
-> part_motion_curves.json
-> component_keyposes/
-> lively_motion_report.json
-> keypose freeze
```

## Required Principles

Every production source-animation plan must include:

- `anticipation`: a preparatory pose before the main action.
- `primary_action`: the readable action the viewer should understand first.
- `overlap`: major parts must not all start and stop in the same frame.
- `follow_through`: tail, ears, hair, clothing edges, head, or arms continue after the primary body motion.
- `secondary_motion`: smaller motion supports the main action; it must not become random noise.
- `part_level_articulation`: internal parts move relative to the torso/root, not only the whole character bbox.
- `identity_safe_squash_stretch`: subtle squash/stretch is allowed only inside declared transform limits.
- `overshoot`: motion may go slightly past its target for energy.
- `settle`: overshoot must return to a coherent resting pose.
- `loop_return`: the final pose must connect back to the first pose without snapping or dead holds.

## Rejection Rules

Reject these before generation or freeze:

- `whole_body_bob_only`: the character only moves as one global placement layer.
- `linear_movement_only`: all spacing is even and mechanical.
- `same_phase_parts`: head, torso, arms, legs, and tail all move in lockstep.
- `tail_locked_to_body`: declared tail has no lag, overshoot, or attachment-aware follow-through.
- `static_arms_or_legs`: limbs stay visually static in an action that requires body acting.
- `near_duplicate_dead_frames`: consecutive frames, especially near the loop end, are visually identical.
- `no_anticipation`: action starts without a preparatory pose.
- `no_settle`: action ends abruptly or holds dead frames instead of settling.
- `secondary_noise`: parts move without a visual reason.
- `broken_layer_motion`: a dirty or unapproved part is moved to hide segmentation defects.

## Planning Fields

Each phase in `action_component_plan.json` should include:

- `acting_intent`: what the character is doing in this phase.
- `primary_driver`: the body part or prop causing the phase.
- `motion_reason`: why secondary parts move in this phase.
- `spacing_curve`: the curve family used by the main motion.
- `overlap_group`: which parts should lead or lag.
- `required_visual_change`: the visible change the frame must prove.

These fields are not final visual QA. They make the action explainable before numeric gates run.

## Provider Boundary

Do not solve liveliness by adding another image provider.

Provider candidates may supply art or pose ideas, but production liveliness must be expressed through contracts, part transforms, curves, and gates. A candidate that is lively but unsegmented must be reworked into approved parts or rejected.

## Audit Boundary

`lively-motion-principles.md` is a planning layer. `lively-motion-contract.md` and `audit_lively_motion.py` are the enforcement layer.

Do not convert every principle into a hard numeric gate immediately. Convert only measurable failures into audit checks. Keep subjective acting notes as plan fields and review evidence.
