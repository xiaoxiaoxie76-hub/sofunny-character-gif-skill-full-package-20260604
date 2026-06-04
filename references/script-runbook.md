# SoFunny Script Runbook

Use this reference for exact script commands. Replace `/path/to/run` and input paths with absolute paths.
SoFunny is the default profile. Add `--profile default-character-gif` or `--profile /path/to/profile.json` when reusing the framework elsewhere.

## Contents

- Asset-Driven Provider Packet
- Run Setup
- Source Animation MVP
- Provider Preflight
- Pose-Only Guides
- Candidate Intake
- Keypose Freeze
- Routing Metrics
- Preview And Audit
- Stabilization And Timing
- Locked GIF Export
- Local Fallbacks
- Provider Packets
- Finalization

## Asset-Driven Provider Packet

Index SoFunny character and animation assets:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/index_sofunny_assets.py \
  --character-dir /Users/xiexiaoxiao/Desktop/SoFunnyWork/Lili角色 \
  --gif-dir "/Users/xiexiaoxiao/Desktop/SoFunnyWork/Lili gif" \
  --output-dir /path/to/sofunny_asset_index
```

Select motion references:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/select_motion_reference.py \
  --asset-index /path/to/sofunny_asset_index/asset_index.json \
  --target-character beav_buy \
  --target-action small_jog_front \
  --direction front \
  --output-dir /path/to/motion_refs \
  --top 10
```

Build a phase-level motion atlas:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/build_motion_atlas.py \
  --selection /path/to/motion_reference_selection.json \
  --output-dir /path/to/motion_atlas \
  --top 5 \
  --phase-count 6 \
  --cell 192x220
```

Create the full packet in one command when local SoFunny libraries are available:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/create_asset_driven_provider_packet.py \
  --character-dir /Users/xiexiaoxiao/Desktop/SoFunnyWork/Lili角色 \
  --gif-dir "/Users/xiexiaoxiao/Desktop/SoFunnyWork/Lili gif" \
  --reference /path/to/canonical_character.png \
  --character-name beav_buy \
  --action small_jog_front \
  --direction front \
  --run-dir /path/to/run \
  --frames 6 \
  --canvas 384x384 \
  --top-donors 5
```

The packet path is the preferred route when the user has local SoFunny character and GIF libraries.

## Run Setup

Inspect active profile defaults:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/load_profile.py \
  --profile sofunny
```

Validate a profile:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/validate_profile.py \
  --profile sofunny
```

Initialize a run:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/init_sofunny_run.py \
  --run-dir /path/to/run \
  --character-name beav \
  --reference /path/to/canonical_character.png \
  --action push_glasses \
  --frames 12 \
  --canvas 384x384 \
  --provider undecided
```

Validate planning state:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/validate_sofunny_run.py \
  --run-dir /path/to/run \
  --stage planning
```

Use `--stage admission` only when final visual artifacts exist.

## Source Animation MVP

Use this route before keypose generation when production identity stability matters. It is a pseudo-rig/component-transform MVP, not a full Spine/Live2D/DragonBones rig.

Select the source route before generating or importing keyposes:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/select_source_animation_route.py \
  --action small_jog_front \
  --run-type production \
  --run-dir /path/to/run
```

This blocks production full-frame redraw unless the run is smoke/exploration or identity drift is explicitly acceptable.

Select an external or local adapter only after the source route is selected:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/select_route_adapter.py \
  --route interpolation_route \
  --adapter tooncrafter \
  --approved-keyposes \
  --reimport-through-gates \
  --run-dir /path/to/run
```

For large-action video adapters, require de-identified input and re-import:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/select_route_adapter.py \
  --route external_animation_provider_candidate \
  --adapter animate_x_wan \
  --deidentified-input \
  --reimport-through-gates \
  --run-dir /path/to/run
```

Hosted Hugging Face or external upload use requires explicit `--external-upload-allowed`.

Create an Animate-X packet only for de-identified large full-body action candidates:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/create_animatex_packet.py \
  --run-dir /path/to/run \
  --canonical-reference /path/to/canonical_character.png \
  --motion-video /path/to/deidentified_motion.mp4 \
  --action large_full_body_action \
  --deidentified-motion
```

After running Animate-X, extract the output video to PNG frames first. Then import the extracted frames as candidate provider frames:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/import_animatex_video_frames.py \
  --run-dir /path/to/run \
  --frames-dir /path/to/animatex_output_png_frames \
  --target-canvas 384x384 \
  --background none
```

The provider-neutral alias is also available for future video adapters:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/import_video_provider_frames.py \
  --run-dir /path/to/run \
  --frames-dir /path/to/video_provider_png_frames \
  --target-canvas 384x384
```

Audit the imported video-provider frames before provider/source preflight or keypose admission:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/audit_video_provider_frames.py \
  --run-dir /path/to/run
```

Animate-X output is always candidate-only. It cannot directly set production approval and cannot replace visual review, keypose freeze, locked GIF export, or final admission.

Create an IPAdapter/ComfyUI local part repair packet when a specific part is broken:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/create_ipadapter_part_repair_packet.py \
  --run-dir /path/to/run \
  --part-name glasses \
  --failure-reason "glasses shape deformed" \
  --failed-frame /path/to/failed_frame.png \
  --part-mask /path/to/glasses_mask.png \
  --canonical-reference /path/to/canonical_character.png
```

After local ComfyUI/IPAdapter repair, import the output through the mask:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/import_ipadapter_part_repair.py \
  --run-dir /path/to/run \
  --packet-dir /path/to/run/ipadapter_part_repair_packets/glasses \
  --repair-output /path/to/comfyui_output.png \
  --part-name glasses
```

Then rerun source-animation checks, especially `audit_part_consistency.py`. IPAdapter output cannot become production approval directly.

Build ToonCrafter interpolation pairs only after keyposes are frozen:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/build_interpolation_pairs.py \
  --run-dir /path/to/run
```

Create a ToonCrafter packet for one approved pair:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/create_tooncrafter_packet.py \
  --run-dir /path/to/run \
  --pair-id pair_000_001
```

After running ToonCrafter externally or locally, extract output to PNG frames and import it as a candidate segment:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/import_tooncrafter_segment.py \
  --run-dir /path/to/run \
  --pair-id pair_000_001 \
  --segment-dir /path/to/tooncrafter_png_frames \
  --target-canvas 384x384
```

Audit the imported segment before candidate admission or a new freeze:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/audit_interpolated_segment.py \
  --run-dir /path/to/run \
  --pair-id pair_000_001
```

ToonCrafter output is always candidate-only; it cannot directly set production approval.

Build part masks and default contracts from a canonical character image:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/build_part_masks.py \
  --canonical /path/to/canonical_character.png \
  --run-dir /path/to/run \
  --character-name beav_buy \
  --action small_jog_front \
  --canvas 384x384 \
  --frames 12 \
  --write-default-contracts
```

Validate the part map and contracts:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/validate_part_map.py \
  --run-dir /path/to/run
```

Generate source-animation keyposes from approved parts:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/generate_component_keyposes.py \
  --run-dir /path/to/run
```

Audit part consistency before GIF export:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/audit_part_consistency.py \
  --run-dir /path/to/run
```

If part consistency fails, create a local repair packet:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/create_local_part_repair_packet.py \
  --run-dir /path/to/run
```

Do not enter GIF export when `part_consistency_report.json` is missing or not `pass`.

When the same route or same failure class repeats, create a retry taxonomy report before another generation attempt:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/retry_tax_report.py \
  --attempt full_frame_redraw:identity_drift \
  --attempt full_frame_redraw:identity_drift \
  --run-dir /path/to/run
```

A non-zero exit means prompt polishing is blocked; switch route or narrow to part-level repair.

## Candidate Intake

## Provider Preflight

Run this before importing image-gen/provider output:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/preflight_provider_output.py \
  --input /path/to/provider_output.png \
  --run-dir /path/to/run \
  --expected-frames 12 \
  --canvas 384x384
```

For a smoke run, use `--expected-frames 6`. A failing report means the output must be regenerated or routed through `references/failure-routing.md`; do not import an output with `PROVIDER_LAYOUT_FAIL`.

## Pose-Only Guides

Convert donor motion references before attaching them to image-gen:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/make_pose_only_guides.py \
  --motion-reference /path/to/reference.gif \
  --output-dir /path/to/run/pose_guides \
  --frames 12 \
  --canvas 384x384
```

Attach `pose_only_guide_sheet.png` as POSE ONLY. Do not attach another character's original sheet or GIF directly.

Normalize an existing `game-character-sprites` sheet:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/normalize_candidate_sheet.py \
  --input /path/to/game-character-sprites-output.png \
  --run-dir /path/to/run \
  --frames 6 \
  --canvas 384x384 \
  --action push_glasses \
  --character-name beav_buy \
  --background checker
```

Use this when action logic is good but character placement shifts. It preserves pose art and fixes baked checker background, frame extraction, scaling, bottom anchor, and lower-body center alignment.

Preferred SoFunny-owned import:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/import_candidate_sheet.py \
  --input /path/to/candidate-sheet.png \
  --run-dir /path/to/run \
  --frames 6 \
  --canvas 384x384 \
  --action small_jog_front \
  --character-name beav_buy \
  --background green \
  --route imported_candidate \
  --admission-eligible
```

This writes `component_cleanup_report.json` and `offset_normalization_report.json`.

## Preview And Audit

Export previews:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/export_sofunny_previews.py \
  --run-dir /path/to/run \
  --duration-ms 90
```

Audit motion:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/audit_sofunny_motion.py \
  --run-dir /path/to/run \
  --duration-ms 90
```

Audit visual stability:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/audit_visual_stability.py \
  --run-dir /path/to/run
```

Audit feature-level identity lock:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/audit_identity_feature_lock.py \
  --reference /path/to/canonical_character.png \
  --run-dir /path/to/run \
  --status manual_required
```

This writes `identity_feature_lock_report.json`, `identity_feature_lock_review.md`, and `identity_feature_comparison.png`.

Audit body and tail consistency:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/audit_body_tail_consistency.py \
  --run-dir /path/to/run
```

This writes `body_tail_consistency_report.json` and `body_tail_debug_sheet.png`.

Validate action contract:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/validate_action_contract.py \
  --run-dir /path/to/run \
  --action small_jog_front
```

Validate manifest:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/validate_sofunny_manifest.py \
  --run-dir /path/to/run
```

## Keypose Freeze

Freeze only after provider preflight and keypose admission reports pass or receive explicit manual approval:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/freeze_keyposes.py \
  --run-dir /path/to/run/candidate_import \
  --canvas 384x384 \
  --duration-ms 90
```

This writes:

```text
accepted_keyposes/
keypose_contact_sheet.png
keypose_checker_preview.gif
keypose_freeze_manifest.json
keypose_freeze_report.json
```

If direct visual review approves despite a `manual_required` report, record the exception:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/freeze_keyposes.py \
  --run-dir /path/to/run/candidate_import \
  --canvas 384x384 \
  --manual-approved \
  --manual-note "reviewed contact sheet, action phases, body/tail, and identity manually"
```

After this point, do not image-gen, redraw, face repair, body repair, or broad-regenerate the frozen keyposes. Create a new candidate/freeze round for art defects.

## Routing Metrics

Score identity/style consistency for routing only:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/score_identity_consistency.py \
  --run-dir /path/to/run/candidate_import \
  --reference /path/to/canonical_character.png
```

This writes `identity_consistency_score.json`. It can hint `IDENTITY_DRIFT`, `SIZE_DRIFT`, or `BODY_SHAPE_DRIFT`, but it cannot approve production.

Classify the primary failure route:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/classify_failure_reason.py \
  --run-dir /path/to/run/candidate_import
```

This writes `failure_classification_report.json` with a primary code and route. Use it to choose the next repair, not to approve the candidate.

## Stabilization And Timing

Create a stabilized copy when motion is readable but the whole character shakes:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/stabilize_visual_jitter.py \
  --run-dir /path/to/frozen_keypose_run \
  --output-run-dir /path/to/run_stabilized_v1 \
  --duration-ms 90
```

If stabilized output fails only because lower-body or shadow alpha flickers, normalize existing alpha:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/normalize_alpha_volume.py \
  --run-dir /path/to/run_stabilized_v1 \
  --output-run-dir /path/to/run_stabilized_alpha_v1 \
  --duration-ms 90
```

Use this only for small residual volume flicker. It must not hide bad drawing, cropped tails, broken identity, or unreadable action.

Retime previews against a real Lili GIF:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/retime_preview_to_reference_gif.py \
  --run-dir /path/to/frozen_keypose_run \
  --output-run-dir /path/to/run_lili_timing \
  --reference-gif "/Users/xiexiaoxiao/Desktop/SoFunnyWork/Lili gif/beav_gacha/beav_gacha-action_walk_01_front.gif"
```

If duplicated timing feels choppy, generate or import more clean keyposes first. For `small_jog_front`, prefer 12 clean keyposes before timing to the official Lili cadence.

Create no-ghost in-betweens from approved keyposes:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/interpolate_keyframes_no_ghost.py \
  --run-dir /path/to/frozen_12_keypose_run \
  --output-run-dir /path/to/no_ghost_40f_run \
  --reference-gif "/Users/xiexiaoxiao/Desktop/SoFunnyWork/Lili gif/beav_gacha/beav_gacha-action_walk_01_front.gif"
```

If interpolation causes bottom drift, run `stabilize_visual_jitter.py` afterward with `--duration-ms 30 --height-amplitude 0`, then rerun admission gates.

Add local upper-body life and in-between frames from accepted keyposes:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/add_lively_inbetweens.py \
  --run-dir /path/to/frozen_keypose_run \
  --output-run-dir /path/to/lively_40f_run \
  --reference-gif "/Users/xiexiaoxiao/Desktop/SoFunnyWork/Lili gif/beav_gacha/beav_gacha-action_walk_01_front.gif" \
  --transition-start 0.35 \
  --micro-strength 0.45
```

This can add head bob, two-hand counter motion, tail lag, and 40-frame timing, but it cannot invent production-quality anatomy from weak poses.

Normalize provider keypose size drift before timing/admission:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/normalize_bbox_size.py \
  --run-dir /path/to/frozen_keypose_run \
  --output-run-dir /path/to/lively_size_norm_run \
  --duration-ms 100
```

Inspect the result because excessive normalization can flatten intentional motion.

These GIF-stage scripts require `keypose_freeze_manifest.json` by default. Use `--allow-unfrozen` only for explicit diagnostics, not admission.

## Locked GIF Export

Use the locked exporter for admission-facing GIF/WebP/spritesheet output:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/export_locked_gif.py \
  --run-dir /path/to/frozen_keypose_run \
  --duration-ms 90
```

To match official Lili timing while preserving frozen keypose pixels:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/export_locked_gif.py \
  --run-dir /path/to/frozen_keypose_run \
  --reference-gif "/Users/xiexiaoxiao/Desktop/SoFunnyWork/Lili gif/beav_gacha/beav_gacha-action_walk_01_front.gif"
```

This writes `locked_gif_export_report.json` and verifies accepted keypose hashes before and after export. Export success is still not production approval.

## Local Fallbacks

Generate a local fallback candidate sheet:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/generate_candidate_sheet.py \
  --reference /path/to/canonical_character.png \
  --run-dir /path/to/run \
  --action small_jog_front \
  --character-name beav_buy \
  --frames 6 \
  --canvas 384x384
```

Then pass `candidate_sheets/<action>-candidate-sheet.png` into `normalize_candidate_sheet.py`. This tests the pipeline but is not admission-eligible for actions that need real new limb poses.

Generate a reference-locked diagnostic candidate:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/generate_reference_locked_jog.py \
  --reference /path/to/canonical_character.png \
  --run-dir /path/to/run \
  --character-name beav_buy \
  --action small_jog_front \
  --frames 6 \
  --canvas 384x384 \
  --duration-ms 90
```

Generate an official-motion retarget diagnostic candidate:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/generate_atlas_retargeted_jog.py \
  --reference /path/to/canonical_character.png \
  --motion-atlas /path/to/motion_atlas.json \
  --run-dir /path/to/run \
  --character-name beav_buy \
  --action small_jog_front \
  --donor-rank 1 \
  --canvas 384x384 \
  --duration-ms 90
```

These routes are diagnostic or research fallbacks by default. They still require direct visual review and normal admission gates.

## Provider Packets

Create a provider brief:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/create_provider_brief.py \
  --reference /path/to/canonical_character.png \
  --run-dir /path/to/run \
  --character-name beav_buy \
  --action small_jog_front \
  --frames 6 \
  --canvas 384x384
```

Create a provider packet with multiple references:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/create_provider_packet.py \
  --run-dir /path/to/run \
  --reference /path/to/canonical_character.png \
  --brief /path/to/provider_briefs/small_jog_front.md \
  --motion-reference /path/to/sofunny_walk_motion_reference.png \
  --motion-reference /path/to/best_existing_action_candidate_sheet.png \
  --cell 384x384
```

Use this pattern for `codex-image-gen` packets:

```text
@01_canonical_reference.png -> EXACT character and style
@03_small_jog_pose_guide.png -> POSE ONLY
@04/05_motion_reference_*.png -> MOTION/ACTION ONLY
Do not blend identities.
```

Run provider-result gates after saving provider output as `provider_packet/generated_sheet.png`:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/run_provider_result_gates.py \
  --run-dir /path/to/run
```

If the sheet is missing, the script writes `provider_result_pending_report.md` and `provider_result_gate_report.json`. If the sheet exists, it runs provider preflight first, then imports, cleans, normalizes, exports previews, runs audits, copies the action review template, and validates the action contract. The result candidate is written to `/path/to/run/candidate_import/`.


Diagnose provider availability or use installed `codex-image-gen` route:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/execute_provider_packet.py \
  --run-dir /path/to/run
```

Run `RUN_CODEX_IMAGE_GEN.sh` only when the user accepts ChatGPT image-generation quota cost. Inspect selected output before copying it to `provider_packet/generated_sheet.png`.

## Finalization

Finalize after direct visual review:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/finalize_sofunny_candidate.py \
  --run-dir /path/to/run \
  --reference /path/to/canonical_character.png \
  --style-status warn \
  --visual-status warn \
  --identity-match warn \
  --motion-status pass \
  --export-status pass \
  --required-fix "identity drift from canonical reference; regenerate with provider reference image attached"
```

Use `--production-approved` only when direct contact-sheet and animation review pass identity, motion, and export quality.
