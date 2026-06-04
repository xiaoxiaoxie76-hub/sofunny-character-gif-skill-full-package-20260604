# ToonCrafter Interpolation Route

Use this route only for in-between frames between already approved SoFunny keyposes.

## Contents

- Fit Assessment
- Allowed Use
- Forbidden Use
- Required Flow
- Packet Contract
- Import Contract
- Audit Contract
- Admission Boundary

## Fit Assessment

ToonCrafter is a cartoon interpolation adapter. The project describes interpolation between two cartoon images using image-to-video diffusion priors, with a 16-frame 512x320 style inference configuration.

This fits SoFunny only when both endpoints are already approved keyposes and the problem is unsmooth transition between keyposes.

It does not fit direct one-image-to-final-GIF production.

## Allowed Use

Allowed:

```text
approved keypose A
+ approved keypose B
-> candidate in-between frames
```

Use it when:

- keyposes have already passed identity or part consistency
- endpoints are frozen or otherwise explicitly approved
- the remaining defect is choppy timing or unnatural transition
- the output will be re-imported and audited as candidate material

## Forbidden Use

Do not use ToonCrafter to:

- generate a full GIF from one character image
- replace unapproved keyposes
- fix identity drift
- fix broken face, glasses, hands, costume, or detached tail
- bypass part consistency, keypose freeze, deterministic export, or final admission
- mark remote or generated video output as production approved

## Required Flow

```text
keypose_freeze_manifest.json
-> build_interpolation_pairs.py
-> create_tooncrafter_packet.py
-> external/local ToonCrafter execution
-> import_tooncrafter_segment.py
-> audit_interpolated_segment.py
-> candidate admission or new freeze
-> deterministic GIF export
-> final admission
```

## Packet Contract

A ToonCrafter packet must include:

```text
start_frame.png
end_frame.png
prompt.txt
tooncrafter_packet.json
README.md
```

The packet must record:

- source pair id
- source keypose hashes
- source canvas
- ToonCrafter target resolution
- expected frame count
- candidate-only status
- re-import requirement
- admission requirement

## Import Contract

Imported ToonCrafter output must be stored as candidate segment frames, not accepted keyposes.

The import report must record:

- source segment directory
- imported frame count
- frame size
- whether canvas conversion happened
- pair id
- candidate-only status

## Audit Contract

Audit must check:

- enough frames exist
- frames are nonblank
- endpoint similarity is plausible
- no exact duplicate-only segment
- frame-to-frame changes are present
- output remains candidate-only

Passing this audit is not production approval. It only means the interpolated segment can enter candidate admission or a new freeze round.

## Admission Boundary

ToonCrafter output is always:

```text
candidate_only = true
production_approved = false
```

After import, continue through SoFunny gates. Never let ToonCrafter replace visual review, keypose freeze, locked GIF export, or final admission.
