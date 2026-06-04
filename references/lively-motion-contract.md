# Lively Motion Contract

Use this reference after `part_consistency_report.json` passes and before keypose freeze.

## Purpose

Identity stability is not enough for production animation. A production SoFunny GIF must show internal acting at the component-keypose layer before export timing, palette, transparency, or loop settings are considered.

The lively motion gate blocks candidates that are technically stable but read as whole-body placement motion, frozen limbs, locked tail, or dead-frame holds.

## Required Production Motion

Production source animation must include all of these:

- `primary_action_phase`: the main readable action, with a clear start, action, and result.
- `secondary_motion`: smaller delayed movement on head, torso, arms, tail, hair, ears, clothing, or expression.
- `part_level_articulation`: at least two non-root movable part groups change internally, not only foreground bbox position.
- `anticipation`: a preparatory pose before the primary action.
- `overshoot_settle`: motion goes slightly past the target and settles back.
- `loop_return`: the last keypose returns coherently to the first pose without snapping.
- `no_whole_body_bob_only`: full-character y/x translation cannot be the main source of visual change.
- `no_near_duplicate_dead_frame_run`: consecutive near-identical frames, especially at the end of the loop, are not production motion.

## Required Reports

Before `freeze_keyposes.py`:

```text
part_consistency_report.json: pass
lively_motion_report.json: pass
```

If `lively_motion_report.json.status` is missing, warn, fail, or manual_required, keypose freeze must fail.

## Required Metrics

`lively_motion_report.json` must include:

- `unique_visual_pose_count`
- `near_duplicate_consecutive_frames`
- `whole_body_translation_vs_internal_part_movement_ratio`
- `head_torso_phase_offset`
- `arm_leg_movement_readability`
- `tail_lag_and_attachment`
- `loop_closure`
- `findings`
- `blocks_keypose_freeze`

## Blocking Conditions

Block keypose freeze when:

- fewer than four unique visual poses exist in a production cycle
- the final frames contain near-duplicate dead holds
- whole-body translation dominates internal part articulation
- head and torso move in lockstep with no offset
- arms and legs are visually locked for an action that requires body acting
- a declared tail is locked, disappears, or has no lag/follow-through
- loop return is missing or snaps
- the candidate only changes duration, palette, export timing, or global placement

## Repair Route

Do not repair lively motion failures through GIF export parameters or finalizer changes.

Use one of:

- `generate_part_motion_curves.py` for parameter-driven part curves
- `add_secondary_motion_pass.py` for bounded part-transform secondary motion
- provider regeneration with a stronger action-component plan
- localized part repair for one broken movable part
- route pivot if two attempts hit the same lively-motion failure class
