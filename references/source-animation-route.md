# Source Animation Route

Use this reference when a SoFunny production GIF must preserve one character identity across multiple frames.

## Contents

- Production Rule
- Full-Frame Redraw Boundary
- Required Contracts
- Route Flow
- Blocking Conditions
- MVP Scope

## Production Rule

For production GIF animation of the same character, prefer source animation over full-frame redraw only when the source is clean enough to animate.

Source animation means:

```text
canonical reference
-> part_map.json
-> identity_parts_contract.json
-> movable_parts_contract.json
-> action_component_plan.json
-> generate or repair only approved parts
-> assembled keyposes
-> provider/source preflight
-> keypose freeze
-> deterministic GIF export
-> admission
```

The goal is to stop `image-gen` from reinterpreting the whole character on every frame. Fixed identity parts may translate, rotate, or receive minor warp only. Movable parts may change only within the approved contract.

Do not treat single-image auto box-split as a production source. Cutting `head`, `torso`, `arm`, `tail`, or `leg` from one flattened PNG is diagnostic-only unless the route also supplies clean masks, underpaint/backfill, anchors/pivots, and a passing neutral reconstruction audit.

For contact actions such as `catch_falling_petal`, do not route an unknown action through `manual_route_override` into a component pseudo-rig. Real hand shape, sleeve connection, and hand/prop occlusion must come from provider keyposes, local redraw keyposes, or clean animation layers.

## Full-Frame Redraw Boundary

Full-frame redraw is allowed only for:

- smoke tests
- rough motion exploration
- one-off concept animation
- actions where identity drift is explicitly acceptable

Full-frame redraw is not production-eligible for repeated SoFunny character GIFs unless the route manifest records `admission_eligible: false` or `identity_drift_acceptable: true`.

Do not fix repeated identity drift by:

- adding more GIF export checks
- retiming bad frames
- palette or compression changes
- best-of-N selection without a source animation contract
- broad prompt polishing

## Required Contracts

A source-animation candidate must include:

```text
part_map.json
identity_parts_contract.json
movable_parts_contract.json
action_component_plan.json
part_consistency_report.json
component_integrity_report.json
lively_motion_report.json
```

The route may also include:

```text
parts/*.png
source_animation_manifest.json
component_keyposes/
component_keypose_contact_sheet.png
local_part_repair_packet/
```

Production component animation additionally requires clean-layer evidence:

```text
clean part masks or provider layer packet
hidden-area underpaint/backfill
anchors/pivots
neutral reconstruction pass
```

## Route Flow

1. Build or load a clean part map. If the only input is a flattened PNG, do not auto-split it into production components.
2. Mark fixed identity parts that must not be redesigned.
3. Mark movable parts and transform limits.
4. Write an action component plan with per-phase part transforms and loop-return semantics.
5. Generate keyposes by copying fixed identity parts and transforming approved movable parts.
6. Use local redraw, ComfyUI, LoRA, IPAdapter, or external image edit only for missing or broken local parts.
7. Audit part consistency before any GIF export.
8. Continue through provider preflight, keypose freeze, locked GIF export, and final admission.

## Blocking Conditions

Block production source animation when:

- `part_map.json` is missing or invalid
- a fixed identity part is missing from `parts/`
- an action phase references a part not declared in the contracts
- a fixed identity part changes beyond allowed transform limits
- a movable part detaches when `must_remain_attached` is true
- image generation rewrites the full character frame
- `part_consistency_report.json` is missing or not `pass`
- `component_integrity_report.json` is missing or not `pass`
- `lively_motion_report.json` is missing or not `pass`
- the component source is single-image hard split without clean masks, underpaint/backfill, anchors/pivots, and reconstruction pass

If part consistency or lively motion fails, do not enter GIF export. Create a local part repair packet, add a secondary-motion pass, split the part map into real movable components, or start a new candidate round.

## MVP Scope

The first MVP is intentionally narrow:

```text
one character
one action: small_jog_front
canvas: 384x384
keyposes: 12
route: pseudo-rig / component transform
not: full Spine, Live2D, or DragonBones rig
```

This MVP should prove that the animation source can preserve identity before broader provider or rig investment.
