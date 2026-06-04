# Failure Routing

Use this reference when a candidate fails. Do not repair every failure with GIF timing, alpha normalization, or broad provider regeneration.

## Failure Codes

`IDENTITY_DRIFT`:
Use single-frame masked repair or regenerate only the affected phase keypose. Do not broadly regenerate the whole strip unless multiple phases drift.

Routing evidence can include `identity_consistency_score.json`, but metrics are advisory only.

`POSE_WEAK`:
Regenerate the target phase keypose with a stronger pose-only guide. Do not use timing or interpolation to compensate for missing action mechanics.

`PLACEMENT_DRIFT`:
Run offset normalization. Preserve the art if the action and identity are good.

`SIZE_DRIFT`:
Run `normalize_bbox_size.py`, then inspect. Reject if normalization flattens intentional motion or distorts identity.

`TAIL_ARTIFACT`:
Use masked local redraw for the affected frame or phase. Do not use alpha normalization to hide clipped, detached, partial, or malformed tails.

`FAKE_TRANSPARENCY`:
Run cleanup or re-export from provider with solid `#00ff00`. If contamination is baked into the character, regenerate the affected frame.

`CHOPPY_TIMING`:
Generate or import more clean keyposes. Do not keep retiming six held poses and call it smooth.

`EXPORT_ONLY_FAIL`:
Change only GIF/WebP/palette/compression/transparent export settings. Do not reopen image-gen.

Use `export_locked_gif.py` for admission-facing output. It must not change frozen keypose PNG hashes.

`PROVIDER_LAYOUT_FAIL`:
Regenerate provider output using `references/provider-output-contract.md`. Do not attempt ad hoc splitting.

`CHECKERBOARD_CONTAMINATION`:
Regenerate with solid `#00ff00` or clean before import only if contamination is clearly background-connected.

## Route Order

Classify the failure first:

```text
layout/background -> identity -> action -> body/tail -> placement/size -> timing -> export
```

Do not invert this order. Export and timing cannot fix identity, action, or body/tail defects.

## Repair Boundary

Before freeze, targeted repair is allowed:

- single-frame masked repair
- regenerate one phase keypose
- offset normalization
- bbox normalization with inspection
- deterministic background cleanup

After freeze, only deterministic GIF-stage operations are allowed. If a frozen keypose needs redraw, create a new candidate round and freeze again.
