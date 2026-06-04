# SoFunny Run Contracts

## Contents

- identity-lock.json
- motion-contract.json
- keypose_freeze_manifest.json
- locked_gif_export_report.json
- admission JSON files

## identity-lock.json

Required fields:

```json
{
  "character_name": "beav",
  "canonical_reference": {
    "source_type": "local_file",
    "source": "/absolute/path/to/canonical.png",
    "used_for_generation": false
  },
  "must_keep": {
    "face": [],
    "body_shape": [],
    "headwear_or_hair": [],
    "tail": [],
    "accessories": [],
    "palette": [],
    "line_style": [],
    "proportions": []
  },
  "forbidden_drift": [
    "changed face",
    "changed body silhouette",
    "missing accessory",
    "unstable tail",
    "wrong palette",
    "fake transparency",
    "checkerboard artifact"
  ],
  "review_status": "draft"
}
```

Set `review_status` to `pass` only after direct visual inspection.

## motion-contract.json

Required fields:

```json
{
  "action_name": "push_glasses",
  "target_frames": 12,
  "canvas": {
    "width": 384,
    "height": 384,
    "transparent": true
  },
  "phases": [
    {"name": "anticipation", "frames": [0, 2], "description": "small prepare motion"},
    {"name": "main_action", "frames": [3, 7], "description": "readable action peak"},
    {"name": "settle", "frames": [8, 10], "description": "return with overshoot"},
    {"name": "loop_return", "frames": [11, 11], "description": "connects back to frame 0"}
  ],
  "anchor_rules": {
    "fixed_ground_contact": true,
    "max_bbox_bottom_range_px": 1,
    "center_x_rule": "small coherent movement only"
  },
  "review_status": "draft"
}
```

## admission JSON files

## keypose_freeze_manifest.json

Required after keypose admission and before deterministic GIF export:

```json
{
  "schema_version": "sofunny-keypose-freeze.v1",
  "source_run": "/absolute/path/to/candidate_import",
  "accepted_keyposes": "/absolute/path/to/candidate_import/accepted_keyposes",
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
  ]
}
```

Frame hashes are the acceptance boundary. If frozen art changes, create a new candidate/freeze round.

## locked_gif_export_report.json

Required for admission-facing GIF/WebP/spritesheet export:

```json
{
  "schema_version": "sofunny-locked-gif-export.v1",
  "status": "pass",
  "freeze_manifest": "/absolute/path/to/keypose_freeze_manifest.json",
  "source_keypose_count": 12,
  "export_frame_count": 40,
  "duration_ms": 30,
  "duplicated_timing_frames": true,
  "source_keyposes_unchanged": true,
  "outputs": {
    "animation_gif": "/absolute/path/to/animation.gif",
    "animation_checker_gif": "/absolute/path/to/animation_checker.gif",
    "animation_webp": "/absolute/path/to/animation.webp",
    "sheet_transparent": "/absolute/path/to/sheet-transparent.png"
  }
}
```

Export success is not production approval.

`style_lock_report.json`:

```json
{
  "status": "pass",
  "identity_match": "pass",
  "drift_findings": [],
  "notes": []
}
```

`jitter_diagnostics.json`:

```json
{
  "status": "pass",
  "frame_count": 12,
  "bbox_bottom_range_px": 0,
  "center_x_range_px": 4,
  "loop_delta_sum": 0,
  "findings": []
}
```

`visual-review.json`:

```json
{
  "status": "pass",
  "contact_sheet_reviewed": true,
  "animation_reviewed": true,
  "identity": "pass",
  "motion": "pass",
  "export_quality": "pass",
  "required_fixes": []
}
```
