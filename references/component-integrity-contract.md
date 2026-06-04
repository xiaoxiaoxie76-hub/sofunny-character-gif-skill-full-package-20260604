# Component Integrity Contract

Use this reference before `lively_motion_report.json` and before keypose freeze.

## Purpose

Component motion is only valid when the parts are clean animation layers. A flat PNG chopped into overlapping rectangles is a diagnostic candidate, not a production source.

`lively_motion_report.json` proves that parts moved. It does not prove that the parts are clean.

## Required Report

Production source-animation routes require:

```text
component_integrity_report.json: pass
```

If the report is missing, warn, fail, manual_required, or diagnostic_only, keypose freeze must fail.

## Required Checks

`audit_component_integrity.py` must check:

- segmentation provenance: `manual_clean_layer`, `masked_redraw_layer`, or equivalent clean source
- flat PNG box split is diagnostic-only
- neutral reconstruction against `source/canonical-normalized.png`
- missing alpha pixels
- extra alpha pixels
- pairwise part overlap
- max overlap depth
- required visual groups: head, torso, arm, leg, tail
- declared anchors/pivots for component rotation

## Blocking Conditions

Block production freeze when:

- parts come from unknown or flat box-split provenance
- part map lacks anchors or pivots
- overlap ratio exceeds threshold
- overlap depth exceeds threshold
- head/torso/arm/tail/leg contain large undeclared overlaps
- neutral reconstruction has holes or extra alpha beyond threshold
- render order is doing hidden cleanup for bad parts

## Repair Route

Do not fix component-integrity failures with GIF export, timing, or finalizer changes.

Use one of:

- clean manual layers
- masked local redraw for one broken part
- provider-generated component layers
- hand/prop anchor creation before action validation
- new candidate round before freeze

