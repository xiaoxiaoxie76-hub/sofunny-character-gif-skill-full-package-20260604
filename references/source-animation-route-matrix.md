# Source Animation Route Matrix

Use this matrix when choosing the source route before keypose generation. It is an enforcement reference, not a provider wish list.

## Contents

- Production Rule
- Route Matrix
- Full-Frame Redraw Boundary
- External Candidate Boundary
- Admission Boundary
- Script Contract

## Production Rule

Production SoFunny GIFs must start from the lowest-drift source that can express the action.

Preferred order:

```text
local part transform / masked edit
-> clean component layer packet + action component plan
-> provider keypose candidate re-imported through SoFunny gates
-> interpolation between approved keyposes
-> adapter candidate re-imported through SoFunny gates
```

Full-frame redraw is not the default production route.
Single-image auto box-split/pseudo-rig is diagnostic-only unless clean component reconstruction passes.

## Route Matrix

`idle`, `blink`, `small_expression`:

```text
source route = local_part_transform_or_masked_edit
reason = small local change; full character redraw is unnecessary
```

`push_glasses`:

```text
source route = part_transform_with_local_hand_glasses_repair
reason = face and glasses must remain stable while hand motion changes
```

`small_jog_front`:

```text
source route = component_pseudo_rig_action_component_plan
reason = alternating feet, body bounce, and tail lag need phase-level control
```

`sherry_tail_wave_greeting`:

```text
source route = provider_keypose_candidate by default
component route = clean_layer_component_route only after clean component layer packet + reconstruction pass
primary action = tail wave + greeting arm + head follow
support action = grounded legs and small torso bounce
reason = this is not a jog, and single-image hard-splitting head/torso/arm/tail creates broken puppet motion
minimum candidate readability = tail rotation range, greeting arm rotation range, and head follow must be visible before any 40-frame timing expansion
blocked = single-image auto-split component_pseudo_rig_action_component_plan as a normal route
```

`catch_falling_petal`:

```text
source route = provider_keypose_candidate by default
local repair route = local_redraw_keypose_candidate for hand, sleeve opening, and petal contact frames
component route = clean_layer_component_route only after clean component layer packet + reconstruction pass
primary action = notice falling petal -> hand lift -> open palm -> partial hand/petal occlusion -> caught hold -> settle -> loop return
reason = the action depends on real palm shape, sleeve connection, and contact occlusion; box-moving a single-image arm cannot create those semantics
blocked = manual_route_override from unknown action into source_animation_component_plan_with_local_hand_redraw
blocked = single-image auto-split component_pseudo_rig_action_component_plan as a normal route
```

`coin_flip_deal_nod`, `coin_flip_deal_nod_v3`:

```text
source route = prop_action_component_route
condition = requires component parts for head, torso/body, arms/hands, legs/feet, tail, and coin prop
reason = coin prop action needs hand release/catch, eye/head follow, body anticipation, tail lag, overshoot, settle, and loop return
blocked = local_part_transform_or_masked_edit with only full_character + coin_prop
```

`large_full_body_action`:

```text
source route = external_animation_provider_candidate
condition = candidate must be de-identified and re-imported
reason = large action may need a provider, but provider output is still only a candidate
```

`approved_keypose_in_between`:

```text
source route = interpolation_route
condition = endpoints must already be approved keyposes
reason = in-between generation must not redesign the character
```

`repeated_production_character`:

```text
source route = lora_ipadapter_or_component_rig_candidate
condition = still requires freeze and admission
reason = reuse may justify adapters, but adapters do not replace gates
```

## Full-Frame Redraw Boundary

Full-frame redraw is allowed only for:

- smoke tests
- rough motion exploration
- one-off concept animation
- actions where identity drift is explicitly acceptable

For production runs, full-frame redraw must be rejected unless the run explicitly records `identity_drift_acceptable: true` and is not asking for normal SoFunny production approval.

## External Candidate Boundary

External animation providers can produce candidate motion for large actions. Before candidate import:

- de-identify any donor character source
- convert donor motion to pose-only or part-level guidance
- re-import extracted frames through SoFunny provider/source preflight
- do not mark provider video output as production-approved by itself

## Admission Boundary

Every selected route still flows through:

```text
component_keyposes or imported keyposes
-> keypose freeze
-> deterministic GIF export
-> final admission
```

Route selection can improve candidate quality. It cannot bypass admission gates.

## Script Contract

`scripts/select_source_animation_route.py` must:

- map known action types to an allowed source route
- block production proposed routes that do not match the required route for the action
- block production full-frame redraw when identity drift is not acceptable
- mark large external provider output as candidate-only until re-imported
- report whether keypose freeze and admission are still required
- write a machine-readable route selection report when requested
