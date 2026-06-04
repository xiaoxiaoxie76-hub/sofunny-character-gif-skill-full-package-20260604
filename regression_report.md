# SoFunny Regression Report

Generated: 2026-06-04T15:38:52.839899+00:00
Status: `pass`

## Command Checks

- PASS: `quick_validate_skill` returncode=0
- PASS: `validate_profile_sofunny` returncode=0
- PASS: `validate_profile_default` returncode=0
- PASS: `audit_admission_enforcement` returncode=0
- PASS: `route_select_small_jog` returncode=0
- PASS: `route_select_blocks_production_full_frame_redraw` returncode=1
- PASS: `route_select_sherry_tail_wave_greeting` returncode=0
- PASS: `route_select_catch_falling_petal` returncode=0
- PASS: `route_select_catch_falling_petal_blocks_candidate_pseudo_rig` returncode=1
- PASS: `route_select_catch_falling_petal_blocks_pseudo_rig` returncode=1
- PASS: `route_select_coin_flip_prop_action` returncode=0
- PASS: `route_select_coin_flip_blocks_local_transform` returncode=1
- PASS: `adapter_select_tooncrafter_requires_approved_keyposes` returncode=1
- PASS: `adapter_select_tooncrafter_with_approved_keyposes` returncode=0
- PASS: `adapter_select_animate_requires_deid_reimport` returncode=1
- PASS: `adapter_select_ipadapter_external_upload_blocked` returncode=1
- PASS: `adapter_select_spine_blocks_first_round_mvp` returncode=1
- PASS: `retry_tax_single_attempt_allows_continue` returncode=0
- PASS: `retry_tax_repeated_identity_drift_requires_pivot` returncode=1
- PASS: `retry_tax_same_route_two_failures_requires_pivot` returncode=1
- PASS: `retry_tax_same_failure_two_routes_requires_pivot` returncode=1
- PASS: `animatex_blocks_small_action` returncode=1
- PASS: `tooncrafter_interpolation_smoke` returncode=0
- PASS: `ipadapter_part_repair_smoke` returncode=0
- PASS: `animatex_video_provider_smoke` returncode=0
- PASS: `hard_split_component_plan_blocks_by_default` returncode=1
- PASS: `catch_falling_petal_hard_split_blocks_generation` returncode=1
- PASS: `component_generation_gate_smoke` returncode=0
- PASS: `freeze_enforcement_smoke` returncode=0
- PASS: `coin_flip_deal_nod_action_contract_smoke` returncode=0

## Cases

### PASS: identity_drift_fail

Identity drift must block production approval.

Evidence:

- finalize_returncode=1
- production_approved=False
- finalize_stdout_last=- keypose_freeze_manifest.json.requirements.identity must be pass, got fail
- validate_admission=skipped
- validate_manifest=skipped

### PASS: lively_motion_near_duplicate_end_frames_fail

Near-duplicate dead frames at the end of a loop must fail lively motion audit.

Evidence:

- audit_lively_motion_returncode=1
- audit_lively_motion_stdout_last=- near-duplicate dead-frame run detected: [5, 6]

### PASS: lively_motion_secondary_motion_pass

A component plan repaired with bounded secondary motion should pass part consistency and lively motion audit.

Evidence:

- add_secondary_motion_pass.py_returncode=0
- add_secondary_motion_pass.py_stdout_last=}
- generate_component_keyposes.py_returncode=0
- generate_component_keyposes.py_stdout_last=/private/var/folders/w4/6zr8c7wj5z3fdcwvh5wnk7jw0000gn/T/sofunny_regression_suite_40ronokm/lively_motion_secondary_motion_pass/component_keyposes
- audit_part_consistency.py_returncode=0
- audit_part_consistency.py_stdout_last=PASS: part consistency audit
- audit_lively_motion.py_returncode=0
- audit_lively_motion.py_stdout_last=PASS: lively motion audit

### PASS: lively_motion_tail_locked_fail

A declared tail that stays locked to the torso must fail lively motion audit.

Evidence:

- audit_lively_motion_returncode=1
- audit_lively_motion_stdout_last=- tail is declared but visually locked

### PASS: lively_motion_whole_body_bob_only_fail

Whole-body bob/placement motion without internal part articulation must fail lively motion audit.

Evidence:

- audit_lively_motion_returncode=1
- audit_lively_motion_stdout_last=- near-duplicate dead frames near loop end: [5]

### PASS: manual_required_fail

manual_required identity review must block production approval.

Evidence:

- finalize_returncode=1
- production_approved=False
- finalize_stdout_last=- keypose_freeze_manifest.json.requirements.identity must be pass, got manual_required
- validate_admission=skipped
- validate_manifest=skipped

### PASS: missing_visual_review_fail

Missing visual-review.json must block production approval.

Evidence:

- finalize_returncode=1
- production_approved=False
- finalize_stdout_last=- visual-review.json must confirm animation_reviewed=true
- validate_admission=skipped
- validate_manifest=skipped

### PASS: pass

Evidence-complete run should finalize and validate as production-approved.

Evidence:

- finalize_returncode=0
- production_approved=True
- finalize_stdout_last=/private/var/folders/w4/6zr8c7wj5z3fdcwvh5wnk7jw0000gn/T/sofunny_regression_suite_40ronokm/pass
- validate_admission_returncode=0
- validate_admission_stdout_last=PASS: admission validation
- validate_manifest_returncode=0
- validate_manifest_stdout_last=PASS: manifest validation

### PASS: retry_budget_identity_drift_pivot

Production approval must fail when retry_tax_report.json requires a route pivot.

Evidence:

- finalize_returncode=1
- production_approved=False
- finalize_stdout_last=- retry_tax enforcement status must be pass for production approval, got pivot_required
- validate_admission=skipped
- validate_manifest=skipped

### PASS: route_selector_missing_report_fail

Production approval must fail when source_route_selection_report.json is missing.

Evidence:

- finalize_returncode=1
- production_approved=False
- finalize_stdout_last=- route_selection enforcement status must be pass for production approval, got missing
- validate_admission=skipped
- validate_manifest=skipped

### PASS: smoke_fail

Pipeline-smoke route must not be production-approved.

Evidence:

- finalize_returncode=1
- production_approved=False
- finalize_stdout_last=- keypose_freeze_manifest.json.requirements.lively_motion must be pass, got not_required
- validate_admission=skipped
- validate_manifest=skipped

### PASS: source_animation_missing_part_map_fail

Source-animation production route must fail when part_map.json is missing.

Evidence:

- finalize_returncode=1
- production_approved=False
- finalize_stdout_last=- action_component_plan enforcement status must be pass for production approval, got missing
- validate_admission=skipped
- validate_manifest=skipped

### PASS: source_animation_part_consistency_fail

Source-animation production route must fail when part_consistency_report.json is not pass.

Evidence:

- finalize_returncode=1
- production_approved=False
- finalize_stdout_last=- part_consistency enforcement status must be pass for production approval, got fail
- validate_admission=skipped
- validate_manifest=skipped

### PASS: tooncrafter_missing_audit_fail

ToonCrafter adapter output must fail production approval when interpolated_segment_audit.json is missing.

Evidence:

- finalize_returncode=1
- production_approved=False
- finalize_stdout_last=- tooncrafter_audit enforcement status must be pass for production approval, got missing
- validate_admission=skipped
- validate_manifest=skipped
