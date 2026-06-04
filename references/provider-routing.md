# Provider Routing

Use this file when choosing between external image edit, local ComfyUI, local LoRA, local redraw, component rigging, and `game-character-sprites`.

## Default route

```text
canonical image
-> identity lock
-> 4-6 keyposes or parts
-> pose-only guide for donor motion references
-> provider preflight when image-gen is used
-> style-lock review
-> keypose admission
-> freeze accepted keyposes
-> jitter diagnostics
-> GIF / sprite packaging
```

## Route selection

`local_redraw`:
Use when only a few frames, hands, face, prop, or tail need repair. This is the lowest-drift option when the base image is strong.

`component_rig`:
Use when the character can be separated into stable parts. Best for wave, coffee, thumbs-up, tail motion, body squash, small walk loops, and other actions where identity must stay exact.

`comfyui`:
Use when unpublished IP cannot leave local infrastructure, or when the team already has a workflow JSON and GPU worker path.

`local_lora`:
Use when a character or style will be reused often enough to justify training and evaluation.

`openai_image_edit`:
Use only when external upload is allowed. Treat it as a keypose, masked-edit, or part-generation provider. Do not ask it to directly output the accepted final 40-frame GIF.

`game-character-sprites`:
Use for downstream fixed-cell sprite packaging, transparent preview export, contact sheets, manifest discipline, and per-strip validation after SoFunny identity and motion gates are credible.

Use it earlier as the preferred candidate generator when its action logic is better than local component-rig output. In that case, route through SoFunny offset normalization:

```text
game-character-sprites candidate sheet
-> normalize_candidate_sheet.py
-> offset_normalization_report.json
-> visual QA
-> admission or localized redraw
```

Do not throw away a strong action candidate only because the character is not aligned. First normalize bottom and lower-body center anchors, then decide whether the remaining problem is pose art, identity drift, or export hygiene.

The SoFunny skill now owns the copied workflow mechanics through:

```text
import_candidate_sheet.py
export_sofunny_previews.py
audit_sofunny_motion.py
validate_sofunny_manifest.py
validate_action_contract.py
```

Use external or old skills only to produce better candidate art. Do not require them for SoFunny cleanup, preview, audit, or admission.

Acceptance order:

```text
motion/action readability
-> offset normalization
-> visual identity/style review
-> keypose freeze
-> export hygiene
```

Do not invert this order. A candidate with good motion and bad offset is repairable. A candidate with clean offset and bad motion is not a good base.

`generate_candidate_sheet.py`:
Use as the local deterministic fallback when the user provides only a canonical PNG and asks to test the SoFunny skill. It creates a candidate sheet for supported simple actions such as `small_jog_front`, then the normal `normalize_candidate_sheet.py` route handles offset stability and QA.

This fallback is not a replacement for image generation. It is a stable motion-base generator for pipeline testing, anchor QA, and local component-rig proofs. It must set `admission_eligible: false` for actions requiring real new limb poses.

For real `small_jog_front`, the candidate generator must create or preserve:

```text
alternating feet
contact/down/passing/up/recover phases
body bounce coupled to foot contact
tail lag that stays attached to the character
no decorative motion-line artifacts near the tail or lower-right canvas
```

If these are absent, the correct verdict is `FIX_ROUND_REQUIRED` or `PIPELINE_SMOKE_ONLY`, even if offset metrics pass.

## Route failure signals

Pivot when any signal repeats:

- face, hat, tail, or costume changes across candidates
- body silhouette changes between frames
- hand or prop becomes unreadable
- bottom anchor jumps after cleanup
- animation is only 3-4 poses toggling
- export is clean but the character no longer looks like the source
- offset still drifts after `normalize_candidate_sheet.py` and the contact sheet confirms body-center instability

Use `references/generation-attempt-budget.md` when a route or failure class repeats twice. At that point another same-route prompt attempt is blocked.

## Future adapters

These are adapters or long-term routes, not first-round MVP requirements:

- `IPAdapter` / `ComfyUI`: local identity lock and local redraw for parts
- `ToonCrafter`: in-between interpolation between approved keyposes
- `Animate-X` / `Wan Animate`: large-action candidate video, then frame extraction through SoFunny gates
- `Spine` / `Live2D` / `DragonBones`: long-term true rig production route

First-round source animation MVP remains:

```text
pseudo-rig / component transform
+ local part repair packet
+ part consistency audit
```
