# External Pose Animation Adapters

Use this reference when provider prompts are not enough to preserve action logic, hand timing, or grounded body mechanics.

## Pain This Solves

These adapters address failures such as:

- atlas frames are visually nice but physically inconsistent
- standing frames randomly shrink or stretch
- hands do not join/release according to the action phase
- bow, walk, wave, or prop actions need real body/hand timing
- prompt-only generation keeps clipping or drifting after retries

## Adapter Roles

`mmpose_dwpose`:

```text
input = self-owned or de-identified motion video / frame sequence
output = pose-only guides, body keypoints, hand keypoints, face keypoints, foot keypoints
use = action logic source before image generation
does_not_output = final character art
```

Use this when the missing dependency is real action logic. For `gentle_bow_flower_sway`, it should provide:

- stable ground/bottom baseline
- visible height curve from standing -> bow -> standing
- hand distance curve: separate -> joined -> separate
- head/torso forward bend timing

`animate_anyone`:

```text
input = canonical character reference + pose guide sequence
output = candidate animation/video frames
use = pose-conditioned full character animation
must_return_through = import_candidate_sheet.py or import_video_provider_frames.py
```

Use this when full-frame image-gen cannot follow the pose sequence. It may improve physical timing, but the output is still candidate-only until SoFunny gates pass.

`magic_animate`:

```text
input = canonical character reference + DensePose/motion condition
output = candidate animation/video frames
use = dense pose-conditioned character animation
must_return_through = import_candidate_sheet.py or import_video_provider_frames.py
```

Use this when DensePose-style body conditioning is stronger than sparse keypoints for a full-body action.

`tooncrafter`:

```text
input = approved endpoint keyposes
output = in-between frames
use = smooth interpolation only after keyposes are approved
must_not = invent action endpoints
```

Use this after the key poses are already correct. It does not solve bad bow physics or broken hands in the endpoint frames.

## Required Skill Flow

```text
canonical character
-> measure_character_identity.py
-> action_contracts/<action>.json
-> create_pose_adapter_packet.py
-> external adapter execution
-> extracted PNG frames or candidate sheet
-> import_candidate_sheet.py / import_video_provider_frames.py
-> source_cell_margin_report.json
-> source_proportion_report.json
-> audit_action_semantics.py
-> freeze_keyposes.py
-> export_locked_gif.py
```

## Do Not

- Do not let adapter output bypass SoFunny gates.
- Do not use donor identity frames directly; convert to pose-only guides.
- Do not treat pose-conditioned video as production approval.
- Do not repair atlas clipping with GIF export settings.
- Do not use ToonCrafter to hide wrong action endpoints.
