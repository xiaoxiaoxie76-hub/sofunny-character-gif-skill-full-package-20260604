# Pose-Only Guide Contract

Use this reference before passing any motion reference to image generation.

## Rule

Do not pass another character's sprite sheet or GIF directly as a motion reference. Convert it into a pose-only guide first.

Allowed information:

- stick figure or simplified silhouette
- joint or anchor points
- foot contact and ground line
- body center and bbox hints
- phase labels
- arrows showing timing or direction

Forbidden information:

- face
- costume
- color palette
- original donor character identity
- texture, markings, accessories, or props
- readable donor silhouette if it still identifies the donor

## Required Artifacts

`make_pose_only_guides.py` must write:

```text
pose_only_guide_sheet.png
pose_only_guide_manifest.json
```

The manifest must state:

```json
{
  "identity_removed": true,
  "forbidden_source_traits": ["face", "costume", "color", "donor_identity", "texture"],
  "allowed_traits": ["anchor_points", "phase_labels", "stick_figure", "ground_contact", "motion_timing"]
}
```

## Provider Packet Rule

When using image-gen edit mode, attach references with explicit roles:

```text
canonical_character.png -> EXACT CHARACTER AND STYLE
pose_only_guide_sheet.png -> POSE ONLY
motion_atlas_contact_sheet.png -> DO NOT ATTACH until converted to pose-only
```

If a motion reference has not been converted, stop and create a pose-only guide first.
