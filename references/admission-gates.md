# SoFunny Admission Gates

Use this reference before any final verdict. Metrics support the decision; they do not replace visual review.

## Contents

- Required Visual Artifacts
- Keypose Freeze Requirement
- Identity Gate
- Motion Gate
- Small Jog Front Contract
- Smoke Vs Admission
- Blocked Acceptance

## Required Visual Artifacts

Review these directly:

```text
contact_sheet.png
animation.gif
animation_checker.gif
identity_feature_comparison.png
body_tail_debug_sheet.png
```

Final admission requires:

```text
style_lock_report.json
jitter_diagnostics.json
offset_normalization_report.json when a sheet was imported or normalized
visual_stability_report.json
body_tail_consistency_report.json
identity_feature_lock_report.json
action_validation_report.json for action-specific motions
component_integrity_report.json for source-animation routes
lively_motion_report.json for source-animation routes
prop_action_contact_report.json for prop action routes
visual-review.json
sofunny-run-manifest.json with production_approved: true
```

Treat `manual_identity_review_required` and `manual_action_review_required` as incomplete, not approved.

## Keypose Freeze Requirement

Final GIF admission requires:

```text
provider_preflight_report.json
keypose_freeze_manifest.json
keypose_freeze_report.json
accepted_keyposes/
keypose_contact_sheet.png
keypose_checker_preview.gif
locked_gif_export_report.json
```

GIF timing, interpolation, stabilization, palette, compression, and transparent export must happen after `keypose_freeze_manifest.json` exists. If a candidate fails identity, action, body/tail, placement, or background checks, fix it before freeze or start a new candidate round.

## Identity Gate

Identity lock is reviewed by character features, not static-pose pixel similarity.

Must preserve:

- face shape and facial features
- body shape and proportions
- hat, hair, costume, accessories
- tail attachment, tail volume, and tail readability
- palette, line weight, and SoFunny icon style

Reject:

- face redraw or wrong expression language
- changed silhouette or costume
- missing accessory
- unstable tail
- wrong palette or line weight
- fake transparency
- checkerboard, pink, black, or white contamination

Do not implement production identity lock by pasting the canonical PNG as a static upper-body layer. That can reduce jitter but usually kills action quality.

## Motion Gate

Lively motion requires coherent frame-to-frame changes with readable phases:

```text
anticipation -> main action -> overshoot -> settle -> loop return
```

Reject:

- static keyposes toggling
- only 3-4 visual poses repeated across many frames
- whole-body translation without action mechanics
- motion lines used as a substitute for body or limb motion
- broken hands, unreadable props, detached limbs, or clipped body parts

For fixed-canvas GIFs, use profile thresholds; center movement must be small and justified by the action.

For normalized sheets, require `offset_normalization_report.json`; target:

```text
bbox_bottom_range_px <= thresholds.jitter.max_bbox_bottom_range_px
anchor_center_x_range_px <= thresholds.jitter.max_anchor_center_x_range_px
```

Visual stability targets:

```text
upper-body/head x range <= thresholds.visual_stability.max_top_centroid_x_range_px
torso/face x range <= thresholds.visual_stability.max_mid_centroid_x_range_px
bbox top range <= thresholds.visual_stability.max_bbox_top_range_px
foreground height range <= thresholds.visual_stability.max_bbox_height_range_px
```

Body and tail consistency targets:

```text
foreground/body width range <= thresholds.body_tail.max_bbox_width_range_px
height range <= thresholds.body_tail.max_bbox_height_range_px
alpha area ratio <= thresholds.body_tail.max_alpha_area_ratio
no clipped, partial, detached, or unstable tail
```

## Small Jog Front Contract

`small_jog_front` requires true action phases:

```text
contact -> down -> passing -> up -> contact -> recover
```

The candidate must show:

- alternating feet
- contact/down/passing/up/recover phases
- body bounce coupled to foot contact
- tail lag that stays attached to the character
- no decorative motion-line artifacts near the tail or lower-right canvas

Blocked small-jog acceptance:

- same legs in every frame
- whole-body squash or translation only
- motion lines substitute for leg motion
- tail or shadow artifacts create abnormal lower-right texture
- no `production_approved: true` verdict

Offset metrics alone cannot approve `small_jog_front`.

## Smoke Vs Admission

`generate_candidate_sheet.py`, `generate_reference_locked_jog.py`, and `generate_atlas_retargeted_jog.py` may prove file workflow, background cleanup, offset normalization, and reporting. They do not prove production action quality by default.

Use these labels clearly:

```text
PIPELINE_SMOKE_ONLY
FIX_ROUND_REQUIRED
ADMISSION_PENDING_MANUAL_REVIEW
PRODUCTION_APPROVED
```

Pipeline smoke output must not be marked as admission pass.

## Blocked Acceptance

Do not call the run complete when any of these are true:

- no canonical reference was used
- output is text-only, prompt-only, or procedural placeholder
- provider output was imported without provider preflight
- final GIF was produced without keypose freeze
- final GIF lacks `locked_gif_export_report.json`
- `action_validation_report.json` is missing or not `pass` for action-specific admission
- source-animation keyposes have missing or non-pass `component_integrity_report.json`
- source-animation keyposes have missing or non-pass `lively_motion_report.json`
- prop action keyposes have missing or non-pass `prop_action_contact_report.json`
- character is animated but no longer the same SoFunny character
- motion is static keypose toggling without coherent in-betweens
- action-specific contract is unmet
- GIF passes export checks but fails visual identity or motion review
- `jitter_diagnostics.json` passes but `visual_stability_report.json` fails
- candidate sheet has visible offset drift and no `offset_normalization_report.json`
- `style_lock_report.json`, `jitter_diagnostics.json`, or `visual-review.json` is missing at final admission
- `identity_feature_lock_report.json` is missing or not `pass` at final admission
- `body_tail_consistency_report.json` is missing or not `pass` at final admission

After direct visual review, set `style_lock_report.json` and `visual-review.json` to `pass` only when identity and action readability both pass. A metric pass is not enough if the contact sheet still looks wrong.
