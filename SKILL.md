---
name: sofunny-character-gif
description: Build, validate, repair, or package SoFunny one-character-to-GIF workflows from a canonical character image. Use for identity-locked lively GIFs, sprite sequences, action contracts, provider packets, candidate-sheet intake, offset normalization, visual QA, admission reports, local redraw, ComfyUI, LoRA, codex-image-gen, or game-character-sprites handoff.
---

# SoFunny Character GIF

## Core Rule

A run is successful only when all three gates pass:

```text
identity lock -> lively motion -> export/admission QA
```

If the canonical character image is unavailable, stop. Do not invent the character from text.

This skill is the SoFunny-specific production layer. External providers and `game-character-sprites` may create candidate art, but this skill owns identity/style lock, action contracts, offset normalization, visual QA, admission, and repair decisions.

Do not treat a clean exported GIF, normalized offsets, or a passing smoke run as production approval. Production approval requires direct visual review plus `production_approved: true` in `sofunny-run-manifest.json`.

## Load References

Load only the reference needed for the current task:

- `references/contracts.md`: required run artifacts and JSON schemas.
- `references/profile-contract.md`: profile schema and parameter priority.
- `references/provider-routing.md`: provider choice, route failure signals, and pivot rules.
- `references/route-adapter-registry.md`: GitHub, Hugging Face, ComfyUI, interpolation, video, and rig tools as route adapters.
- `references/ipadapter-local-repair-route.md`: IPAdapter/ComfyUI for masked local part identity/style repair.
- `references/animatex-provider-route.md`: Animate-X as a large full-body video candidate adapter.
- `references/external-adapter-license-notes.md`: license, IP, and hosted-upload boundary notes for external adapters.
- `references/provider-output-contract.md`: exact provider output requirements before import.
- `references/pose-only-guide-contract.md`: required de-identification rules before using motion references.
- `references/source-animation-route.md`: when production GIFs must use part-based source animation instead of full-frame redraw.
- `references/source-animation-route-matrix.md`: action-to-source-route selection and full-frame redraw blocking.
- `references/tooncrafter-interpolation-route.md`: ToonCrafter as an approved-keypose in-between candidate adapter.
- `references/identity-parts-contract.md`: fixed identity parts that may not be redesigned frame-to-frame.
- `references/movable-parts-contract.md`: movable parts, allowed transforms, and attachment limits.
- `references/action-component-plan.md`: action phases mapped to part transforms before keypose generation.
- `references/component-integrity-contract.md`: clean component segmentation gate before lively motion and freeze.
- `references/lively-motion-contract.md`: source-animation liveliness gate after part consistency and before keypose freeze.
- `references/prop-action-component-contract.md`: prop actions such as coin toss/deal that require component-level acting.
- Optional liveliness references: `lively-motion-principles.md`, `part-parameter-contract.md`, `secondary-motion-contract.md`, and `future-rigging-research-notes.md` are for targeted repair/research, not default generation gates.
- `references/keypose-freeze-gate.md`: freeze boundary between image-gen candidates and GIF export.
- `references/failure-routing.md`: fixed route for identity, pose, placement, tail, transparency, timing, and export failures.
- `references/generation-attempt-budget.md`: retry budget and forced pivots after repeated route/failure repeats.
- `references/gif-export-contract.md`: deterministic locked export rules after freeze.
- `references/script-runbook.md`: exact commands for run init, candidate import, provider packets, audits, preview export, timing, stabilization, and finalization.
- `references/admission-gates.md`: visual QA thresholds, blocked acceptance, small-jog action semantics, smoke-vs-admission rules.

Keep references one hop from this file. Do not duplicate detailed command recipes in `SKILL.md`.

## Reference Routing

Use this small routing table before loading detailed references:

```text
route selection: source-animation-route-matrix.md + route-adapter-registry.md
retry/pivot decision: generation-attempt-budget.md + failure-routing.md
external adapter use: route-adapter-registry.md + external-adapter-license-notes.md + the adapter-specific route reference
source animation build: source-animation-route.md + identity-parts-contract.md + movable-parts-contract.md + action-component-plan.md + component-integrity-contract.md + lively-motion-contract.md
provider import/preflight: provider-output-contract.md + pose-only-guide-contract.md
freeze/export: keypose-freeze-gate.md + gif-export-contract.md
final admission: admission-gates.md + failure-routing.md
```

## Required Inputs

Minimum:

```text
canonical_character_image
action_name
target_output: gif | sprite_sequence | fixed_cell_sheet
profile: sofunny unless specified
```

Preferred:

```text
motion_reference_gif_or_notes
style_reference_image
provider_constraint: local_only | external_api_allowed | undecided
target_canvas: from profile unless specified
target_frames: from profile unless specified
```

For internal or unpublished SoFunny IP, choose local ComfyUI, local LoRA, or local redraw unless the user explicitly allows external upload.

## Workflow

1. Lock scope: action, output type, frame count, canvas, facing direction, and provider constraint. Keep first proof to one character, one action, one direction.
2. Create identity lock: record immutable character facts and forbidden drift in `identity-lock.json`. Identity lock means fixed character features, not a frozen source pose.
3. Write motion contract: define phases, anchor rules, loop return, and action-specific semantics. For lively motion, require coherent frame-to-frame changes, not static pose toggling.
4. Choose route: read `references/provider-routing.md`, `references/source-animation-route-matrix.md`, and `references/route-adapter-registry.md` when choosing between source animation, local redraw, component rig, ComfyUI, LoRA, image provider, candidate-sheet intake, or `game-character-sprites`. Convert any donor motion reference through `references/pose-only-guide-contract.md` first.
   Run `select_source_animation_route.py` before provider generation in production/admission runs. Run `retry_tax_report.py` before retrying a failed route; if `pivot_required: true`, do not continue the same route.
5. Plan source animation: for production GIFs, read `references/source-animation-route.md`; define `part_map.json`, fixed identity parts, movable parts, and action-specific component transforms before keypose generation. Full-frame redraw is smoke-only unless identity drift is acceptable. Use optional liveliness references only when a candidate is stable but mechanically dead.
6. Generate or import candidate: use `references/provider-output-contract.md`; default keypose counts, canvas, and background come from the active profile. For source animation, generate or repair only approved parts, then assemble keyposes. Use `add_secondary_motion_pass.py` only as targeted repair when liveliness is missing. For IPAdapter local repair, read `references/ipadapter-local-repair-route.md` and constrain edits to the part mask. For ToonCrafter interpolation, read `references/tooncrafter-interpolation-route.md` and use only approved keypose pairs. For Animate-X, read `references/animatex-provider-route.md`; use it only for de-identified large full-body video candidates.
7. Run provider/source preflight: do not import output that fails deterministic layout, frame count, background, bbox, component integrity, part consistency, lively motion, edge, fake-transparency, or checkerboard checks.
   If an adapter route is used, its packet/import/audit report is mandatory before keypose freeze.
8. Run keypose admission: import/normalize, then audit identity, action, body/tail, placement, and background.
9. Freeze accepted keyposes: create `accepted_keyposes/` and `keypose_freeze_manifest.json` before any GIF timing, interpolation, stabilization, or export. Default freeze is `--stage candidate` so a coherent GIF can be reviewed even while production reports are still diagnostic. Use `--stage production` only when production gates should hard-block. For production source-animation routes, `part_consistency_report.json`, `component_integrity_report.json`, and `lively_motion_report.json` must be `pass`; for prop routes, `prop_action_contact_report.json` must also be `pass`.
10. Deterministic GIF export: only after freeze, allow timing, loop, palette, compression, transparent export, and anchor normalization. Default export is candidate-only; use `--stage production` only from a production freeze. Use `references/keypose-freeze-gate.md` and `references/gif-export-contract.md`.
11. Final admission: production approval, targeted repair before a new freeze, provider regeneration, route pivot, or `PIPELINE_SMOKE_ONLY`. Use `references/admission-gates.md` and `references/failure-routing.md`.

## Candidate Handling

When `game-character-sprites` or a provider produces strong action logic but unstable placement, do not discard it. Preserve the pose logic and run SoFunny-owned intake:

```text
candidate sheet
-> preflight_provider_output.py
-> import_candidate_sheet.py or normalize_candidate_sheet.py
-> stable transparent sequence_frames/
-> offset_normalization_report.json
-> contact_sheet.png + animation_checker.gif
-> freeze_keyposes.py
-> deterministic GIF export, localized redraw before new freeze, or regeneration
```

Use `generate_candidate_sheet.py`, `generate_reference_locked_jog.py`, or `generate_atlas_retargeted_jog.py` as local fallback or diagnostic routes unless the reference explicitly marks the output admission-eligible. Label weak local fallback output as pipeline smoke.

For fixed-cell sprite output, pass accepted SoFunny-gated frames or strips to `game-character-sprites` packaging conventions only after identity, motion, and admission gates are credible.

## Admission Boundary

Never call a run complete if any of these are true:

- no canonical reference was used
- output is text-only, prompt-only, or procedural placeholder
- production source animation used full-frame redraw without an explicit smoke-only or identity-drift-acceptable route
- `part_map.json`, `identity_parts_contract.json`, `movable_parts_contract.json`, or `action_component_plan.json` is required by the route but missing before keypose generation
- `part_consistency_report.json` is missing or not `pass` for a source-animation route
- `component_integrity_report.json` is missing or not `pass` for a source-animation route
- `lively_motion_report.json` is missing or not `pass` for a source-animation route
- `prop_action_contact_report.json` is missing or not `pass` for a prop action route
- provider output lacks `provider_preflight_report.json` with `status: pass`
- accepted final GIF was produced without `keypose_freeze_manifest.json`
- final GIF was not exported through a locked export path or lacks `locked_gif_export_report.json`
- `style_lock_report.json`, `jitter_diagnostics.json`, `visual-review.json`, `identity_feature_lock_report.json`, or `body_tail_consistency_report.json` is missing at final admission
- action-specific `action_validation_report.json` is missing or not `pass`
- metrics pass but direct visual review shows identity drift, visible jitter, broken face/hands/tail, fake transparency, checkerboard residue, cropped body parts, or pose-only toggling
- `sofunny-run-manifest.json` lacks `production_approved: true`

Read `references/admission-gates.md` before making any final verdict.

## Pivot Rules

If whole-character redraw keeps drifting, stop prompt polishing and pivot to source animation: fixed identity parts, movable parts, component transforms, masked part repair, or LoRA/style training for missing parts.

If the same route or same failure class repeats twice, read `references/generation-attempt-budget.md` and switch route or narrow to part-level repair before another generation attempt.

If action quality is strong but frame placement drifts, run offset normalization first. Redraw is for bad art, broken identity, or unreadable action; normalization is for unstable placement.

If timing feels choppy because too few unique keyposes are stretched across a cycle, generate or import more clean keyposes before retiming.

SoFunny is the default profile. Use `--profile default-character-gif` or a custom profile path when applying the framework outside SoFunny.

## Internal Modules

SoFunny-local helpers live under `scripts/sofunny_anim/`:

```text
image_io.py        # loading, checker/background cleanup
frame_layout.py    # sheet splitting and sequence frame IO
anchors.py         # lower-body anchors and offset normalization
previews.py        # GIF/WebP/checker/contact/sheet export
motion_metrics.py  # jitter, edge touch, frame delta metrics
manifests.py       # JSON and run-path helpers
```
