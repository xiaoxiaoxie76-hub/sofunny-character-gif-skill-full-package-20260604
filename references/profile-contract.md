# Profile Contract

Profiles separate reusable fixed-character animation flow from project-specific defaults.

## Contents

- Required Fields
- Unknown Keys
- Action Contracts
- Thresholds
- Priority
- Profile Responsibilities
- Use

## Required Fields

Every profile JSON must contain:

```text
schema_version
profile_name
profile_type
unknown_keys_policy
default_canvas
default_background
default_keypose_count
style_rules
identity_features
motion_defaults
thresholds
asset_paths
```

`schema_version` must be:

```text
sofunny-profile.v1
```

`profile_type` must be:

```text
production | generic
```

`unknown_keys_policy` must be:

```text
fail | warn | ignore
```

Production profiles must use:

```text
unknown_keys_policy: fail
```

## Unknown Keys

Unknown top-level keys are handled by the active profile:

```text
fail: validation fails
warn: validation may continue, but the field is not part of the contract
ignore: validation ignores unknown fields
```

Use `fail` unless there is a deliberate migration window. The default SoFunny production profile must fail on unknown keys.

## Action Contracts

Every action in `motion_defaults.actions` must define:

```text
requires_manual_phase_review
phases_N for at least one supported frame count
phase_semantics
required_visual_changes
required_global_checks
```

Each phase name used in `phases_6`, `phases_12`, or another `phases_N` list must exist in `phase_semantics`.

`required_visual_changes` describes what must visibly change for the action to count as real motion. These are action-quality requirements, not prompt suggestions.

`required_global_checks` describes review checks that apply to the whole sequence, such as identity stability, loop return, tail attachment, or contact/shadow logic.

## Thresholds

Thresholds are validated as typed numeric values with non-negative or bounded ranges. Required groups:

```text
provider_preflight
jitter
visual_stability
body_tail
identity_consistency
action_contract
```

Ratio-like thresholds such as alpha-area ratios and SSIM/color limits must stay within their expected numeric ranges. Pixel thresholds must be non-negative. Alpha/color tolerances must stay in `0..255` where applicable.

## Priority

Parameter priority is:

```text
CLI args > profile values > built-in defaults
```

SoFunny remains the default profile. Use `--profile default-character-gif` for a generic baseline or pass an absolute path to a custom JSON profile.

## Profile Responsibilities

`default_canvas`:
Default fixed frame/cell size, e.g. `384x384`.

`default_background`:
Provider interchange background, e.g. `#00ff00`.

`default_keypose_count`:
Object with `smoke` and `production` counts.

`style_rules`:
Project-level style constraints used for prompts, reviews, and routing.

`identity_features`:
Feature checklist for identity lock. These are not pixel-similarity rules.

`motion_defaults`:
Default action, duration, action phases, and manual review requirements.

`thresholds`:
Numerical routing/admission thresholds for provider preflight, visual stability, body/tail consistency, identity consistency, and action contracts.

`asset_paths`:
Optional project paths, such as local character libraries, GIF donor folders, and timing references.

## Use

Validate:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/validate_profile.py \
  --profile sofunny
```

Inspect resolved profile:

```bash
python3 /Users/xiexiaoxiao/.codex/skills/sofunny-character-gif/scripts/load_profile.py \
  --profile sofunny
```

Scripts that participate in admission, contracts, freeze, export, or routing should accept `--profile`, default to `sofunny`, and allow CLI flags to override profile values.
