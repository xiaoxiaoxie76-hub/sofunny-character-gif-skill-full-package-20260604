# Provider Output Contract

Use this reference before asking image-gen, ComfyUI, LoRA, or an external provider for a candidate sheet.

## Required Output Shape

Provider output must be one of:

- separate PNG frames
- an exact fixed-cell sheet

Defaults come from the active profile:

```text
production keyposes: default_keypose_count.production
smoke keyposes: default_keypose_count.smoke
cell: default_canvas
background: default_background
```

Each frame or cell must exactly match `default_canvas` unless overridden by CLI. A sheet must be exactly divisible into the requested grid. If layout cannot be deterministically split, mark `PROVIDER_LAYOUT_FAIL` and regenerate.

## Required Background

Use the profile's solid chroma background. SoFunny defaults to:

```text
#00ff00
```

Do not use:

- checkerboard
- transparent background
- magenta background
- white/grey page background
- generated canvas texture

The solid background is an interchange contract, not final art. It exists so cleanup is deterministic.

## Forbidden Output Content

Reject provider output with:

- text
- watermark
- UI controls
- labels
- borders
- frame numbers
- duplicate figures in a cell
- neighbor-frame fragments
- cropped body or tail
- edge touching

## Preflight

Run `preflight_provider_output.py --profile sofunny` before import or normalization.

Required checks:

- image size
- exact grid
- frame count
- background type
- component count
- bbox range
- edge touching
- fake transparency
- checkerboard contamination

The report is:

```text
provider_preflight_report.json
```

Only `status: pass` can proceed to candidate import. `warn` requires explicit manual approval. `fail` must be regenerated or routed through `references/failure-routing.md`.
