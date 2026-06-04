# Generation Attempt Budget

Use this reference when repeated generation attempts are producing the same class of failure. It prevents prompt polishing from replacing route correction.

## Contents

- Budget Rule
- Failure Classes
- Pivot Actions
- Blocking Conditions
- Script Contract

## Budget Rule

Do not spend unlimited attempts on the same route.

```json
{
  "max_same_route_attempts": 2,
  "max_same_failure_class": 2
}
```

After two failed attempts on the same route or two repeats of the same failure class, the next step must be a route pivot or a narrower part-level repair.

When the budget is reached:

```text
pivot_required = true
prompt_polishing_allowed = false
```

## Failure Classes

Use stable failure class names in reports:

```text
identity_drift
pose_weak
tail_artifact
loop_pop
choppy_timing
part_map_manual_required
part_consistency_fail
provider_layout_fail
```

Unknown failures should be recorded as `unknown` plus a concrete note. Unknown does not permit continued prompt polishing when the same route is already at budget.

## Pivot Actions

```json
{
  "repeat_identity_drift": "pivot_to_source_animation_route",
  "repeat_pose_weak": "revise_action_component_plan",
  "repeat_tail_artifact": "part-level tail repair or tail rig",
  "repeat_loop_pop": "revise recover phase before GIF export",
  "repeat_choppy_timing": "increase approved keyposes before timing"
}
```

## Blocking Conditions

Block another same-route generation attempt when:

- same route failed twice
- same failure class appeared twice
- production candidate still depends on full-frame redraw after identity drift
- loop pop is being retimed without a recover phase fix
- choppy timing is being stretched without more approved keyposes

When blocked, create a retry taxonomy report and change route or scope.

Blocked reports must prohibit:

- another same-route generation
- prompt-only wording changes
- best-of-N retries without a route change
- GIF timing, palette, or compression tweaks as a substitute for source repair

## Script Contract

`scripts/retry_tax_report.py` must:

- read attempt history from JSON or explicit CLI attempts
- count same-route failures
- count same failure-class repeats
- map repeated failures to a required pivot action
- return non-zero when another same-route attempt is blocked
- report `prompt_polishing_allowed: false` when blocked
- report concrete `next_allowed_actions`
- write a machine-readable retry taxonomy report when requested
