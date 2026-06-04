# GIF Export Contract

Use this reference after keypose freeze and before final GIF/WebP/spritesheet export.

## Locked Source

GIF export must read from:

```text
accepted_keyposes/
keypose_freeze_manifest.json
```

Before export, verify every accepted keypose file still matches the SHA-256 hash recorded in `keypose_freeze_manifest.json`.

Export has two stages:

- `candidate`: default diagnostic export from candidate freeze. It is useful for judging continuity and acting. It must write `candidate_only: true`.
- `production`: strict export from production freeze. It is the only export stage eligible for final admission.

## Allowed After Freeze

Allowed GIF-stage operations:

- timing
- loop
- palette
- compression
- transparent export
- spritesheet packaging
- duplicated-frame cadence expansion

These operations must not alter the source keypose PNG files.

## Forbidden After Freeze

Forbidden GIF-stage operations:

- image-gen
- redraw
- face repair
- body repair
- identity repair
- broad provider regeneration
- alpha normalization to hide art defects
- tail/body repair through export settings

If frozen art needs repair, create a new candidate round, repair before freeze, and run `freeze_keyposes.py` again.

## Required Export Report

`export_locked_gif.py` must write:

```text
animation.gif
animation_checker.gif
animation.webp
sheet-transparent.png
locked_gif_export_report.json
```

The report must include:

- source freeze manifest
- source keypose hashes before export
- source keypose hashes after export
- duration and frame count
- whether duplicated timing frames were used
- whether optional optimizer was used
- confirmation that frozen source PNG hashes did not change

## Approval Boundary

Export success is not production approval. Final admission still requires direct visual review and `production_approved: true`.

Candidate export success is specifically not production approval. A production run must use `--stage production` at freeze and export.
