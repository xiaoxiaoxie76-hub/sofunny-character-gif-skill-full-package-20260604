# Prop Action Component Contract

Use this reference for actions where a character manipulates a visible prop.

## Coin Flip Deal Nod

`coin_flip_deal_nod` and versioned variants such as `coin_flip_deal_nod_v3` must not use a two-part `full_character + coin_prop` route for production. That route can preserve identity, but it cannot prove hand release, eye follow, body anticipation, tail lag, catch, present, and settle.

Required route:

```text
prop_action_component_route
```

Required parts:

```text
head or face/head group
torso or body root
left_arm or left_hand
right_arm or right_hand
left_leg or left_foot
right_leg or right_foot
tail
coin_prop
```

Required reports:

```text
component_integrity_report.json: pass
prop_action_contact_report.json: pass
```

Required phases:

```text
ready
anticipation
toss_release
coin_rise
coin_peak
deal_nod_down
catch_receive
present
settle
loop_return
```

Required visual changes:

- head and eyes follow the coin path
- body compresses before release
- arm/hand releases the coin and later catches or presents it
- torso nod is offset from head motion
- tail lags behind body motion and overshoots on settle
- coin prop follows a readable arc and rotation
- legs/feet maintain support instead of sliding as a full-body placement move
- final pose returns to the first pose without dead-frame holds

Blocking conditions:

- route selected as `small_expression`
- route selected as `local_part_transform_or_masked_edit`
- part map renders only `full_character` plus `coin_prop`
- component parts come from flat PNG box split without clean segmentation provenance
- no `left_hand` / `right_hand` part or explicit hand anchors exist for release/catch/present
- coin contact distances fail `prop_action_contact_report.json`
- `lively_motion_report.json` is missing or not `pass`
- `component_integrity_report.json` is missing or not `pass`
- `prop_action_contact_report.json` is missing or not `pass`
- `action_component_plan.json` lacks the required phase semantics
