# Keypose Freeze Gate

Use this reference when moving from image-generated candidate art to GIF export. The goal is to stop image-gen defects from leaking into timing, interpolation, or export repair.

## Contents

- Gate Model
- Freeze Requirements
- Manifest Contract
- After Freeze

## Gate Model

Provider or image-gen output can only enter:

```text
candidate_preflight/
```

It becomes production input only after:

```text
provider preflight
-> candidate import or normalization
-> identity/action/body-tail/placement/background/part-consistency/lively-motion checks
-> freeze accepted keyposes
-> deterministic GIF export
```

After freeze, the accepted source is:

```text
accepted_keyposes/
keypose_freeze_manifest.json
```

The GIF stage must read from frozen keyposes or from a run that contains `keypose_freeze_manifest.json`.

There are two freeze stages:

- `candidate`: default diagnostic freeze. It may produce a coherent GIF for review even when production reports are missing, warn, or fail. It must write `candidate_only: true` and cannot feed production approval.
- `production`: strict freeze. It requires all production prerequisites to pass and is the only freeze stage eligible for final admission.

## Freeze Requirements

Before production freeze, these must be pass or explicitly manually approved:

- provider layout and background: `provider_preflight_report.json`
- placement: `jitter_diagnostics.json` and `visual_stability_report.json`
- identity: `identity_feature_lock_report.json`
- action: `action_validation_report.json`
- body/tail: `body_tail_consistency_report.json`
- source animation consistency: `part_consistency_report.json` when a part-map route is used
- component integrity: `component_integrity_report.json` when a part-map route is used
- lively source motion: `lively_motion_report.json` when a part-map route is used
- prop contact/action semantics: `prop_action_contact_report.json` when a prop route is used

Manual approval must be explicit and recorded in `keypose_freeze_report.json`. Missing reports are incomplete by default for `--stage production`. For production source-animation routes, `identity_feature_lock_report.json`, `body_tail_consistency_report.json`, `jitter_diagnostics.json`, `visual_stability_report.json`, `part_consistency_report.json`, `component_integrity_report.json`, and `lively_motion_report.json` are hard requirements and cannot be bypassed by manual approval. For prop routes, `prop_action_contact_report.json` is also hard. Manual approval on failed production source-animation writes diagnostic-only failure, not a production freeze.

For `--stage candidate`, freeze is allowed to create reviewable GIF inputs. Candidate freeze does not mean approval and must be blocked by final admission.

## Manifest Contract

`keypose_freeze_manifest.json` must record:

```json
{
  "schema_version": "sofunny-keypose-freeze.v1",
  "source_run": "/absolute/path/to/candidate_import",
  "accepted_keyposes": "/absolute/path/to/accepted_keyposes",
  "frame_count": 12,
  "canvas": {"width": 384, "height": 384},
  "frames": [
    {
      "index": 0,
      "file": "accepted_keyposes/000.png",
      "sha256": "frame hash",
      "phase": "contact"
    }
  ],
  "allowed_after_freeze": [
    "timing",
    "loop",
    "palette",
    "compression",
    "transparent_export",
    "anchor_normalization"
  ],
  "forbidden_after_freeze": [
    "image_gen",
    "redraw",
    "face_repair",
    "body_repair",
    "identity_redraw",
    "broad_provider_regeneration"
  ],
  "freeze_stage": "production",
  "candidate_only": false
}
```

Frame hashes define the accepted keypose identity. If a frame changes after freeze, create a new candidate round and freeze again.

## After Freeze

Allowed:

- timing and retiming
- loop alignment
- palette and compression settings
- transparent GIF/WebP/sheet export
- anchor normalization that does not redraw art
- interpolation or local in-betweening only when it preserves the frozen keypose identity and writes a derived-run report

Forbidden:

- image-gen on frozen keyposes
- broad redraw or provider regeneration
- face repair
- body repair
- hiding tail/body defects with alpha normalization
- calling GIF export settings a fix for identity, action, or body/tail failures

If identity, action, or body/tail fails after freeze, route using `references/failure-routing.md` and create a new candidate/freeze round.
