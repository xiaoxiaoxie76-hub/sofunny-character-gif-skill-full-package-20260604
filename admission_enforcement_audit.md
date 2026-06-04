# Admission Enforcement Audit

Generated: 2026-06-04T15:38:50.465308+00:00
Status: `pass`

## Required Final Artifacts

### SKILL.md:Admission Boundary

- `action_component_plan.json`
- `action_validation_report.json`
- `body_tail_consistency_report.json`
- `component_integrity_report.json`
- `identity_feature_lock_report.json`
- `identity_parts_contract.json`
- `jitter_diagnostics.json`
- `keypose_freeze_manifest.json`
- `lively_motion_report.json`
- `locked_gif_export_report.json`
- `movable_parts_contract.json`
- `part_consistency_report.json`
- `part_map.json`
- `prop_action_contact_report.json`
- `provider_preflight_report.json`
- `sofunny-run-manifest.json`
- `style_lock_report.json`
- `visual-review.json`

### admission-gates.md:Required Visual Artifacts

- `action_validation_report.json`
- `animation.gif`
- `animation_checker.gif`
- `body_tail_consistency_report.json`
- `body_tail_debug_sheet.png`
- `component_integrity_report.json`
- `contact_sheet.png`
- `identity_feature_comparison.png`
- `identity_feature_lock_report.json`
- `jitter_diagnostics.json`
- `lively_motion_report.json`
- `offset_normalization_report.json`
- `prop_action_contact_report.json`
- `sofunny-run-manifest.json`
- `style_lock_report.json`
- `visual-review.json`
- `visual_stability_report.json`

### admission-gates.md:Keypose Freeze Requirement

- `keypose_checker_preview.gif`
- `keypose_contact_sheet.png`
- `keypose_freeze_manifest.json`
- `keypose_freeze_report.json`
- `locked_gif_export_report.json`
- `provider_preflight_report.json`

### admission-gates.md:Blocked Acceptance

- `action_validation_report.json`
- `body_tail_consistency_report.json`
- `component_integrity_report.json`
- `identity_feature_lock_report.json`
- `jitter_diagnostics.json`
- `lively_motion_report.json`
- `locked_gif_export_report.json`
- `offset_normalization_report.json`
- `prop_action_contact_report.json`
- `style_lock_report.json`
- `visual-review.json`
- `visual_stability_report.json`

### keypose-freeze-gate.md:Freeze Requirements

- `action_validation_report.json`
- `body_tail_consistency_report.json`
- `component_integrity_report.json`
- `identity_feature_lock_report.json`
- `jitter_diagnostics.json`
- `keypose_freeze_report.json`
- `lively_motion_report.json`
- `part_consistency_report.json`
- `prop_action_contact_report.json`
- `provider_preflight_report.json`
- `visual_stability_report.json`

### keypose-freeze-gate.md:Manifest Contract

- `accepted_keyposes/`
- `keypose_freeze_manifest.json`

### gif-export-contract.md:Locked Source

- `keypose_freeze_manifest.json`

### gif-export-contract.md:Required Export Report

- `animation.gif`
- `animation.webp`
- `animation_checker.gif`
- `locked_gif_export_report.json`
- `sheet-transparent.png`

## Findings

No enforcement mismatches found.
## Negative Tests

### PASS: missing visual-review.json blocks finalization

Expected: finalize exits non-zero and does not write production_approved:true

- returncode=1
- production_approved_written=False
- stdout=- visual-review.json must confirm animation_reviewed=true

### PASS: manual_required identity_feature_lock_report blocks finalization

Expected: finalize exits non-zero and does not write production_approved:true

- returncode=1
- production_approved_written=False
- stdout=- keypose_freeze_manifest.json.requirements.identity must be pass, got manual_required

### PASS: smoke run blocks production approval

Expected: finalize exits non-zero and does not write production_approved:true

- returncode=1
- production_approved_written=False
- stdout=- keypose_freeze_manifest.json.requirements.lively_motion must be pass, got not_required

## Static Coverage

```json
{
  "scripts": {
    "finalize_sofunny_candidate.py": {
      "has_failure_path": true,
      "reads_required_artifacts": [
        "accepted_keyposes/",
        "action_component_plan.json",
        "action_validation_report.json",
        "animation.gif",
        "animation.webp",
        "animation_checker.gif",
        "body_tail_consistency_report.json",
        "component_integrity_report.json",
        "contact_sheet.png",
        "identity_feature_lock_report.json",
        "identity_parts_contract.json",
        "jitter_diagnostics.json",
        "keypose_checker_preview.gif",
        "keypose_contact_sheet.png",
        "keypose_freeze_manifest.json",
        "keypose_freeze_report.json",
        "lively_motion_report.json",
        "locked_gif_export_report.json",
        "movable_parts_contract.json",
        "offset_normalization_report.json",
        "part_consistency_report.json",
        "part_map.json",
        "prop_action_contact_report.json",
        "provider_preflight_report.json",
        "sheet-transparent.png",
        "sofunny-run-manifest.json",
        "style_lock_report.json",
        "visual-review.json",
        "visual_stability_report.json"
      ],
      "mentions_required_artifacts": [
        "accepted_keyposes/",
        "action_component_plan.json",
        "action_validation_report.json",
        "animation.gif",
        "animation.webp",
        "animation_checker.gif",
        "body_tail_consistency_report.json",
        "component_integrity_report.json",
        "contact_sheet.png",
        "identity_feature_lock_report.json",
        "identity_parts_contract.json",
        "jitter_diagnostics.json",
        "keypose_checker_preview.gif",
        "keypose_contact_sheet.png",
        "keypose_freeze_manifest.json",
        "keypose_freeze_report.json",
        "lively_motion_report.json",
        "locked_gif_export_report.json",
        "movable_parts_contract.json",
        "offset_normalization_report.json",
        "part_consistency_report.json",
        "part_map.json",
        "prop_action_contact_report.json",
        "provider_preflight_report.json",
        "sheet-transparent.png",
        "sofunny-run-manifest.json",
        "style_lock_report.json",
        "visual-review.json",
        "visual_stability_report.json"
      ],
      "production_approved_cli_flag_lines": [
        302
      ]
    },
    "validate_sofunny_run.py": {
      "mentions_required_artifacts": [
        "accepted_keyposes/",
        "action_validation_report.json",
        "animation.gif",
        "animation.webp",
        "animation_checker.gif",
        "body_tail_consistency_report.json",
        "component_integrity_report.json",
        "contact_sheet.png",
        "identity_feature_lock_report.json",
        "jitter_diagnostics.json",
        "keypose_checker_preview.gif",
        "keypose_contact_sheet.png",
        "keypose_freeze_manifest.json",
        "keypose_freeze_report.json",
        "lively_motion_report.json",
        "locked_gif_export_report.json",
        "prop_action_contact_report.json",
        "provider_preflight_report.json",
        "sheet-transparent.png",
        "sofunny-run-manifest.json",
        "style_lock_report.json",
        "visual-review.json",
        "visual_stability_report.json"
      ],
      "missing_required_gate_artifacts": [],
      "uses_non_strict_admission_eligible_check": false
    },
    "validate_sofunny_manifest.py": {
      "mentions_required_artifacts": [
        "accepted_keyposes/",
        "sofunny-run-manifest.json"
      ],
      "optional_artifact_declaration_check": false
    }
  }
}
```
