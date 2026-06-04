# Animate-X Provider Route

Use this route only when a SoFunny action needs a large full-body video motion candidate.

## Contents

- Fit
- Non-Fit
- Required Flow
- Packet Contract
- Import Contract
- Audit Contract
- Candidate Boundary
- Script Contract

## Fit

Animate-X is a universal character image animation framework. The official repository describes it as a latent-diffusion animation framework for varied character types, including anthropomorphic characters. Its default inference path uses one reference image plus a driving dance video and writes a 32-frame mp4 at 768x512.

This is useful for:

- `large_full_body_action`
- `dance`
- `jump`
- `run_large_body_motion`
- `complex_dynamic_pose`

Use it when the current route fails because the body motion is too large or too pose-driven for small keypose edits.

## Non-Fit

Do not use Animate-X for:

- precise SoFunny small actions
- glasses, face, tail, costume, or hand identity repair
- part-level local redraw
- transparent GIF direct production
- approved keypose in-between interpolation
- prompt polishing after repeated identity failures

Animate-X output is video-like candidate material, not a natural sprite sheet and not an admitted final GIF.

## Required Flow

```text
canonical_character.png
+ de-identified motion video or pose-only motion source
-> create_animatex_packet.py
-> external/local Animate-X execution
-> extract mp4/video output to PNG frames
-> import_animatex_video_frames.py
-> audit_video_provider_frames.py
-> provider/source preflight
-> keypose admission
-> freeze accepted keyposes
-> locked GIF export
-> final admission
```

Never skip SoFunny gates after the external provider returns frames.

## Packet Contract

An Animate-X packet must include:

- canonical reference image
- de-identified motion source
- action name
- prompt
- target resolution
- expected frame count
- explicit `candidate_only: true`
- explicit `production_approved: false`
- `requires_sofunny_gates: true`
- `requires_reimport: true`
- `direct_gif_export_allowed: false`

Block packet creation if the motion source has not been marked de-identified.

## Import Contract

Import only extracted PNG frames.

Do not hide video decoding inside the import step. If the provider returns mp4, first extract frames using a deterministic video tool, then pass the frame directory to `import_animatex_video_frames.py`.

The import step may:

- convert frames to RGBA
- remove transparent, green, or checker background when requested
- resize to the target SoFunny canvas
- write normalized candidate frames

The import step may not:

- set production approval
- infer visual approval from frame count
- bypass provider/source preflight

## Audit Contract

`audit_video_provider_frames.py` checks only provider-frame readiness:

- enough PNG frames exist
- frames are nonblank
- frame sizes are consistent
- frame-to-frame motion is nonzero
- output remains candidate-only

Passing this audit means the extracted frames may continue into SoFunny provider/source preflight and keypose admission. It does not mean identity, action semantics, freeze, export, or final admission passed.

## Candidate Boundary

Animate-X output is always:

```text
candidate_only = true
production_approved = false
requires_reimport = true
requires_sofunny_gates = true
```

If Animate-X fails twice on the same failure class, stop prompt polishing and pivot by `references/generation-attempt-budget.md`.

## Script Contract

The scripts must enforce:

- only supported large full-body actions can create packets
- `--deidentified-motion` is required
- direct GIF production is blocked
- imported provider frames remain candidate-only
- audit output cannot approve production
