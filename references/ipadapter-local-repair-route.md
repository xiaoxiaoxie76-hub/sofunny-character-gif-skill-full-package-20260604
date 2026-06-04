# IPAdapter Local Repair Route

Use this route when a single local part has failed and the canonical character identity or style must be preserved.

## Contents

- Fit Assessment
- Allowed Use
- Forbidden Use
- Required Flow
- Packet Contract
- Import Contract
- Audit Boundary
- Admission Boundary

## Fit Assessment

ComfyUI IPAdapter Plus is a ComfyUI reference implementation for IPAdapter models. Its README describes IPAdapter as image-to-image conditioning that can transfer the subject or style of reference images into generation, like a one-image LoRA. Its node documentation also supports attention masks for limiting the area of influence.

This fits SoFunny local repair when the problem is:

- one broken hand
- one deformed glasses region
- one detached or damaged tail region
- one missing local part

It does not fit full-frame character redraw.

## Allowed Use

Allowed:

```text
canonical reference image
+ failed frame
+ part mask
-> repaired part or masked repaired frame
```

Use it for:

- `part-level repair`
- `masked local redraw`
- `missing part generation`

The canonical reference is for identity or style conditioning. The mask is the repair boundary.

## Forbidden Use

Do not use IPAdapter / ComfyUI to:

- redraw the full character frame for production
- alter unmasked pixels
- replace approved keyposes
- fix action phase logic
- fix loop pop through image redesign
- bypass `audit_part_consistency.py`
- mark output as production approved

## Required Flow

```text
failed_frame.png
+ canonical_reference.png
+ part_mask.png
-> create_ipadapter_part_repair_packet.py
-> local ComfyUI / IPAdapter execution
-> import_ipadapter_part_repair.py
-> validate_part_map.py if parts changed
-> generate_component_keyposes.py if source parts changed
-> audit_part_consistency.py
-> keypose freeze or candidate admission
```

## Packet Contract

An IPAdapter part repair packet must include:

```text
canonical_reference.png
failed_frame.png
part_mask.png
previous_frame.png optional
next_frame.png optional
prompt.txt
negative_prompt.txt
ipadapter_part_repair_packet.json
README.md
```

The packet must record:

- part name
- failure reason
- mask coverage
- canonical source
- candidate-only status
- full-frame redraw prohibition
- required post-import audits

## Import Contract

Imported repair output can be:

- a repaired full canvas, composited only through `part_mask.png`
- a repaired part image, pasted into the mask bbox

Regardless of source format, the final imported output must preserve unmasked pixels from the failed frame. Any unmasked pixel changes are a blocker.

## Audit Boundary

After import, run `audit_part_consistency.py`. If the repair changed source parts, rerun `validate_part_map.py` and `generate_component_keyposes.py` first.

IPAdapter import success means only that the local repair was bounded to the mask. It does not mean identity, action, part consistency, freeze, or final admission passed.

## Admission Boundary

IPAdapter repair output is always:

```text
candidate_only = true
production_approved = false
full_frame_redraw = false
```

The repaired result must continue through SoFunny gates. Never let an IPAdapter output directly become a production GIF.
