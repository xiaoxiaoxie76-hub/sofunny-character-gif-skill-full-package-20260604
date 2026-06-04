# Route Adapter Registry

Use this registry when attaching external GitHub, Hugging Face, local ComfyUI, or rigging tools to a selected source-animation route.

Read `references/external-adapter-license-notes.md` before any hosted upload or production dependency decision.

## Contents

- Adapter Rule
- Adapter Matrix
- Candidate Boundary
- Upload Boundary
- MVP Boundary
- Script Contract

## Adapter Rule

Adapters are implementation helpers for a selected route. They are not production routes by themselves.

Every adapter output is candidate material until it returns through:

```text
SoFunny source/provider preflight
-> keypose freeze
-> deterministic GIF export
-> final admission
```

No GitHub or Hugging Face tool may set `production_approved: true`.

## Adapter Matrix

`ipadapter_comfyui`:

```text
source = local ComfyUI / IPAdapter style or identity conditioning
allowed_use = local part identity lock, local part redraw, missing part generation
allowed_routes = local_part_transform_or_masked_edit, part_transform_with_local_hand_glasses_repair, lora_ipadapter_or_component_rig_candidate
must_not = full-frame production redraw
output_status = candidate parts or candidate keyposes
route_reference = references/ipadapter-local-repair-route.md
```

`tooncrafter`:

```text
source = interpolation adapter
allowed_use = in-between generation between approved keyposes
allowed_routes = interpolation_route
requires = approved endpoint keyposes
must_not = invent new identity or replace unapproved endpoints
output_status = candidate in-betweens
route_reference = references/tooncrafter-interpolation-route.md
```

`animate_x_wan`:

```text
source = external or local video animation candidate adapter
allowed_use = large full-body action candidate video
allowed_routes = external_animation_provider_candidate
requires = de-identified motion input and re-import through SoFunny gates
must_not = direct final GIF approval
output_status = candidate video or extracted candidate frames
route_reference = references/animatex-provider-route.md
```

`mmpose_dwpose`:

```text
source = GitHub pose-estimation adapter
allowed_use = whole-body / hand / face keypoint extraction from self-owned or de-identified motion references; pose-only guide generation before provider image generation
allowed_routes = pose_conditioned_provider_candidate, external_animation_provider_candidate
requires = de-identified motion input when donor material is used
must_not = copy donor identity, costume, face, or body proportions
output_status = pose-only guides and pose metrics, never final art
route_reference = references/external-pose-animation-adapters.md
```

`animate_anyone`:

```text
source = GitHub pose-conditioned image-to-video character animation adapter
allowed_use = reference-image character animation from pose guide sequence
allowed_routes = pose_conditioned_provider_candidate, external_animation_provider_candidate
requires = pose guide sequence, re-imported extracted frames, and SoFunny gates
must_not = direct final GIF approval or hosted upload without explicit permission
output_status = candidate video or extracted candidate frames
route_reference = references/external-pose-animation-adapters.md
```

`spine_live2d_dragonbones`:

```text
source = true rig production system
allowed_use = long-term repeated production character route
allowed_routes = lora_ipadapter_or_component_rig_candidate
requires = explicit long-term rig scope and manual rig assets
must_not = first-round MVP shortcut
output_status = rig candidate or rig-exported candidate frames
```

## Candidate Boundary

Adapter output must record:

- adapter name
- selected source route
- whether output is candidate-only
- de-identification status when donor motion is used
- re-import requirement
- freeze requirement
- admission requirement

Production approval remains blocked until SoFunny admission artifacts pass.

## Upload Boundary

For unpublished SoFunny IP:

- local ComfyUI / local adapter execution is preferred
- hosted Hugging Face or external uploads require explicit user permission
- donor character material must be converted to pose-only or de-identified input before adapter use
- external output must be re-imported; do not treat a remote video/GIF as final

## MVP Boundary

First-round MVP is still:

```text
pseudo-rig / component transform
+ local part repair packet
+ part consistency audit
```

Do not implement or require full Spine, Live2D, DragonBones, ToonCrafter, Animate-X, Wan Animate, or hosted Hugging Face execution for the MVP. Registering an adapter only defines how it may be used later.

## Script Contract

`scripts/select_route_adapter.py` must:

- accept a selected source route and requested adapter
- reject adapters that are incompatible with the route
- require approved keypose endpoints for interpolation adapters
- require de-identification and re-import for external animation provider candidates
- reject hosted external upload unless explicitly allowed
- reject long-term rig adapters unless long-term rig scope is explicitly allowed
- write a machine-readable adapter selection report when requested
