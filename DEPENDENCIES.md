# Dependencies

## Runtime

- Python 3.10+
- Pillow
- numpy
- scikit-image

## Optional External Tools

Some adapter/provider routes may require external tools or services:

- `codex-image-gen` runner for image generation packet execution
- local ComfyUI/IPAdapter routes when using local repair adapters
- external adapter repositories such as ToonCrafter or Animate-X only when explicitly selected

These optional adapters are documented under `references/`.

## Internal Modules

The internal Python package lives at:

`scripts/sofunny_anim/`

Scripts are designed to be run from the skill root or with paths under this repository.

