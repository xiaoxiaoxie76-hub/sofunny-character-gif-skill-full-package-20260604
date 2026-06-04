#!/usr/bin/env python3
"""Select and enforce the source-animation route for a SoFunny action."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FULL_FRAME_ROUTES = {"full_frame_redraw", "image_gen_full_frame_redraw", "full-frame-redraw"}
FULL_FRAME_ALLOWED_RUN_TYPES = {"smoke", "rough_motion_exploration", "one_off_concept"}


@dataclass(frozen=True)
class RouteRule:
    action: str
    route: str
    reason: str
    alternate_routes: tuple[str, ...] = ()
    candidate_only: bool = False
    de_identification_required: bool = False
    reimport_required: bool = False
    freeze_required: bool = True
    admission_required: bool = True


ROUTE_MATRIX: dict[str, RouteRule] = {
    "idle": RouteRule(
        action="idle",
        route="local_part_transform_or_masked_edit",
        reason="small local change; full character redraw is unnecessary",
    ),
    "blink": RouteRule(
        action="blink",
        route="local_part_transform_or_masked_edit",
        reason="small local change; full character redraw is unnecessary",
    ),
    "small_expression": RouteRule(
        action="small_expression",
        route="local_part_transform_or_masked_edit",
        reason="small local expression change; face identity must remain locked",
    ),
    "push_glasses": RouteRule(
        action="push_glasses",
        route="part_transform_with_local_hand_glasses_repair",
        reason="face and glasses must remain stable while hand motion changes",
    ),
    "small_jog_front": RouteRule(
        action="small_jog_front",
        route="component_pseudo_rig_action_component_plan",
        reason="alternating feet, body bounce, and tail lag need phase-level control",
    ),
    "sherry_tail_wave_greeting": RouteRule(
        action="sherry_tail_wave_greeting",
        route="provider_keypose_candidate",
        reason="single-image auto-split pseudo-rig is too brittle for Sherry; generate real action keyposes or import a clean layer packet before component animation",
        alternate_routes=("clean_layer_component_route",),
        candidate_only=True,
        reimport_required=True,
    ),
    "catch_falling_petal": RouteRule(
        action="catch_falling_petal",
        route="provider_keypose_candidate",
        reason="petal catch requires real hand shape, sleeve connection, and hand/petal occlusion; single-image hard-split pseudo-rig cannot create contact semantics",
        alternate_routes=("local_redraw_keypose_candidate", "clean_layer_component_route"),
        candidate_only=True,
        reimport_required=True,
    ),
    "coin_flip_deal_nod": RouteRule(
        action="coin_flip_deal_nod",
        route="prop_action_component_route",
        reason="coin prop action needs hand/arm release, eye/head follow, body anticipation, tail lag, catch/present, and loop settle",
    ),
    "coin_flip_deal_nod_v3": RouteRule(
        action="coin_flip_deal_nod_v3",
        route="prop_action_component_route",
        reason="coin prop action needs hand/arm release, eye/head follow, body anticipation, tail lag, catch/present, and loop settle",
    ),
    "large_full_body_action": RouteRule(
        action="large_full_body_action",
        route="external_animation_provider_candidate",
        reason="large motion may need a provider, but output is candidate-only until re-imported",
        candidate_only=True,
        de_identification_required=True,
        reimport_required=True,
    ),
    "approved_keypose_in_between": RouteRule(
        action="approved_keypose_in_between",
        route="interpolation_route",
        reason="in-betweening must use already approved keypose endpoints",
    ),
    "repeated_production_character": RouteRule(
        action="repeated_production_character",
        route="lora_ipadapter_or_component_rig_candidate",
        reason="reuse may justify adapters, but freeze and admission still apply",
    ),
}


def normalize_action(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_report(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    action = normalize_action(args.action)
    blockers: list[str] = []
    warnings: list[str] = []
    rule = ROUTE_MATRIX.get(action)

    if rule is None:
        blockers.append(f"unknown action route: {action}")
        report: dict[str, Any] = {
            "schema_version": "sofunny-route-selection-report.v1",
            "status": "fail",
            "action": action,
            "run_type": args.run_type,
            "recommended_route": None,
            "proposed_route": args.proposed_route,
            "identity_drift_acceptable": args.identity_drift_acceptable,
            "freeze_required": True,
            "admission_required": True,
            "blockers": blockers,
            "warnings": warnings,
        }
        return report, 1

    proposed = args.proposed_route.strip() if args.proposed_route else None
    proposed_normalized = proposed.lower().replace(" ", "_") if proposed else None
    if proposed_normalized in FULL_FRAME_ROUTES:
        allowed = args.run_type in FULL_FRAME_ALLOWED_RUN_TYPES or args.identity_drift_acceptable
        if not allowed:
            blockers.append("production full-frame redraw is blocked; pivot to source animation route")
        else:
            warnings.append("full-frame redraw is not admission-eligible unless marked smoke/exploration or identity drift acceptable")
    elif args.run_type in {"production", "production_candidate"} and proposed_normalized:
        allowed_routes = {rule.route, *rule.alternate_routes}
        if proposed_normalized not in allowed_routes:
            blockers.append(f"proposed route {proposed_normalized} does not match allowed routes {sorted(allowed_routes)} for {action}")

    if args.run_type == "production" and rule.candidate_only:
        warnings.append("selected route is candidate-only until de-identified and re-imported through SoFunny gates")

    status = "pass" if not blockers else "fail"
    report = {
        "schema_version": "sofunny-route-selection-report.v1",
        "status": status,
        "action": action,
        "run_type": args.run_type,
        "recommended_route": rule.route,
        "route_reason": rule.reason,
        "proposed_route": proposed,
        "identity_drift_acceptable": args.identity_drift_acceptable,
        "candidate_only": rule.candidate_only,
        "de_identification_required": rule.de_identification_required,
        "reimport_required": rule.reimport_required,
        "freeze_required": rule.freeze_required,
        "admission_required": rule.admission_required,
        "blockers": blockers,
        "warnings": warnings,
    }
    return report, 0 if status == "pass" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", required=True)
    parser.add_argument(
        "--run-type",
        default="production",
        choices=["production", "production_candidate", "smoke", "rough_motion_exploration", "one_off_concept"],
    )
    parser.add_argument("--proposed-route", default="")
    parser.add_argument("--identity-drift-acceptable", action="store_true")
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    report, code = build_report(args)
    output = args.output
    if not output and args.run_dir:
        output = str(Path(args.run_dir) / "source_route_selection_report.json")
    if output:
        output_path = Path(output).expanduser().resolve()
        write_json(output_path, report)
        if args.run_dir and output_path.name == "source_route_selection_report.json":
            write_json(output_path.parent / "route_selection_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
