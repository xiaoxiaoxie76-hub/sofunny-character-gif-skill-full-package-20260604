# Action Contract Schema

Use action contracts to keep action knowledge out of provider scripts.

## Shape

```json
{
  "schema_version": "sofunny-action-contract.v1",
  "action": "gentle_bow_flower_sway",
  "default_frames": 16,
  "anchor_policy": "fit-ground",
  "atlas_contract": {
    "layout": "grid",
    "rows": 4,
    "columns": 4,
    "safe_margin_ratio": 0.12,
    "gutter_required": true,
    "forbid_edge_touching": true
  },
  "projection_contract": {
    "height_curve": "decrease_hold_increase",
    "max_adjacent_height_delta_ratio": 0.13,
    "max_standing_height_delta_ratio": 0.02,
    "bottom_anchor": "stable",
    "scale": "sequence_locked"
  },
  "phases": [
    {
      "frame": 0,
      "name": "standing_ready",
      "body": "upright",
      "hands": "separate"
    }
  ],
  "hard_requirements": [],
  "reject_if": [],
  "semantic_audit": {
    "height_curve": {
      "standing_lock_frames": [0, 1],
      "max_standing_height_delta_ratio": 0.02,
      "max_adjacent_height_delta_ratio": 0.13
    }
  }
}
```

## Rules

- `anchor_policy` selects the placement adapter before GIF export.
- `atlas_contract` controls provider sheet generation and preflight expectations.
- `projection_contract` defines allowed pose projection, not random redraw drift.
- `phases` are the provider-facing motion plan and the audit-facing expected sequence.
- Hand, prop, face, or body semantics that cannot be detected robustly must be marked as manual review requirements instead of guessed from pixels.

## Boundary

Do not encode character identity inside an action contract. Character identity comes from `measure_character_identity.py` output plus user/provider notes.
