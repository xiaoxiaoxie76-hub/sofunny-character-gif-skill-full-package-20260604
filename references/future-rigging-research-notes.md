# Future Rigging Research Notes

This is a research-only reference. Do not add production dependencies from this file without a separate route contract and regression suite.

## Contents

- Purpose
- Useful Ideas
- Not Production Defaults
- Migration Boundary

## Purpose

Long-term SoFunny animation may benefit from more formal 2D rigging and mesh extraction, but the current production path should remain contract-driven source animation.

## Useful Ideas

- Inochi2D: parameter-driven 2D puppet structure, layered art, mesh deformation, and transform parameters.
- APES-style articulated part discovery: recognizing head, torso, limbs, and joints from sprite poses.
- SpriteToMesh-style mesh generation: contour-aware vertex placement and lightweight deformation.
- Sketch-guided in-betweening: rough silhouette or limb path guides before interpolation.

## Not Production Defaults

Do not make these the default SoFunny route:

- automatic mesh extraction as a hard dependency
- full external rig runtime
- full-frame video generation for small SoFunny actions
- provider-driven identity lock

## Migration Boundary

Promote a research route to production only after it has:

- explicit input/output contract
- license and upload boundary review
- deterministic import path
- component integrity audit
- part consistency audit
- lively motion audit
- regression cases for pass, fail, and adapter misuse
