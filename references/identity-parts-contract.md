# Identity Parts Contract

Use this reference before generating or assembling keyposes for a source-animation route.

## Contents

- Purpose
- Required JSON
- Default SoFunny Parts
- Allowed Changes
- Blocking Conditions
- Review Checklist

## Purpose

Identity parts are character-defining visual structures. They must not be redesigned frame-to-frame.

Examples:

- head shape
- face features
- glasses or accessories
- torso suit or costume silhouette
- tail base and attachment
- palette and line style

`image-gen` must not turn an identity part into a new design. For source animation, fixed identity parts can only be copied, translated, rotated, or lightly warped within the declared allowance.

## Required JSON

`identity_parts_contract.json`:

```json
{
  "schema_version": "sofunny-identity-parts.v1",
  "character_name": "beav_buy",
  "fixed_identity_parts": [
    {
      "part": "head",
      "must_preserve": true,
      "allowed_change": "minor vertical bob and small rotation only",
      "max_rotation_deg": 4,
      "max_translation_px": 8,
      "max_area_delta_ratio": 0.08
    }
  ],
  "forbidden_changes": [
    "redesigned face",
    "changed glasses shape",
    "changed body silhouette",
    "detached tail",
    "new costume structure"
  ]
}
```

## Default SoFunny Parts

For a front-facing small jog MVP, start with:

```text
head
face
glasses
torso
tail
```

These are fixed identity parts by default. Arms and legs may be movable if the `movable_parts_contract.json` allows them.

## Allowed Changes

Allowed fixed-part changes:

- translate with body or head anchor
- rotate within `max_rotation_deg`
- minor squash/stretch only when declared
- alpha-preserving local warp that does not alter silhouette beyond threshold

Forbidden fixed-part changes:

- regenerate the whole part into a new design
- change facial layout without approved expression variants
- remove or redraw glasses
- detach tail root
- alter palette or line style across frames

## Blocking Conditions

Block source-animation approval when:

- a fixed part listed in the contract is missing from `part_map.json`
- a fixed part image is missing from `parts/`
- a generated keypose appears to redraw a fixed part
- area, bbox, or attachment drift exceeds thresholds
- the review status is `manual_required`, `warn`, `fail`, or missing

## Review Checklist

Before keypose freeze, verify:

- fixed parts exist in every assembled keypose
- fixed part positions follow the declared action transform
- face and glasses are not redesigned
- body proportions remain stable
- tail root remains attached
- any expression changes are explicitly approved

