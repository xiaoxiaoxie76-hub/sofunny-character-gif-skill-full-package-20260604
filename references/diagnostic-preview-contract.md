# Diagnostic Preview Contract

Use this reference when the user wants to see a quick sequence-frame preview before production source animation exists.

## Rule

Diagnostic previews are allowed for motion-direction review only. They are not production candidates.

Use:

```text
scripts/create_diagnostic_sequence_preview.py
```

Do not write one-off `generate_<character>_<action>_sequence.py` scripts for user-facing skill output. If a local experiment is unavoidable, it must be clearly isolated outside production admission and must not replace this diagnostic preview contract.

Diagnostic preview is also not a semantic action generator. If the action requires feet, hands, tail, prop contact, accessories, or expression changes, this route must fail by default instead of returning a weak whole-character bob.

## Required Boundary

A diagnostic preview run must write:

```text
candidate_boundary_report.json
diagnostic_preview_report.json
semantic_capability_report.json
sofunny-run-manifest.json
identity-lock.json
motion-contract.json
sequence_frames/
contact_sheet.png
animation_checker.gif
```

The boundary report must include:

```json
{
  "status": "diagnostic_only",
  "admission_eligible": false,
  "blocks_production_admission": true
}
```

The manifest generation block must include:

```json
{
  "route": "diagnostic_sequence_preview",
  "generator": "create_diagnostic_sequence_preview.py",
  "generator_type": "skill_diagnostic_preview",
  "diagnostic_only": true,
  "admission_eligible": false,
  "ad_hoc_local_generator": false
}
```

`semantic_capability_report.json` must be `pass` only when the target action can be represented as rough whole-character motion. It must be `fail` when the target action requires:

- foot articulation, walking, stepping, running, jogging, or skirt/foot occlusion
- tail articulation or tail lag
- hand/prop contact
- pearl, bow, hair, ear, or accessory secondary motion
- blink, wink, or facial expression variants

## Blocking Conditions

Block production admission when:

- `semantic_capability_report.status` is `fail`
- `candidate_boundary_report.status` is `diagnostic_only`
- `candidate_boundary_report.admission_eligible` is `false`
- `sofunny-run-manifest.json.generation.diagnostic_only` is `true`
- the route starts with `diagnostic_`
- `ad_hoc_local_generator` is `true`
- the run lacks source-animation contracts, freeze, locked export, or final visual review

Block sequence generation itself unless the user explicitly passes `--force-diagnostic` when:

- the action name implies walking, stepping, running, jogging, hand contact, prop contact, tail motion, accessory secondary motion, blink, wink, or expression changes
- the only selected preset is whole-character translation/scale/rotation

`--force-diagnostic` is for debugging only. It may generate frames, but `semantic_capability_report.status` remains `fail`.

## What This Solves

This prevents a quick preview from being mistaken for the latest production skill path. It also prevents temporary hand-written scripts from bypassing route selection, component integrity, lively motion, keypose freeze, locked GIF export, and admission gates. Most importantly, it prevents a weak whole-body bob from being presented as a walk, hand action, tail action, prop action, or accessory animation.
