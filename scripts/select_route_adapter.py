#!/usr/bin/env python3
"""Select and enforce a route adapter for a SoFunny source route."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AdapterRule:
    name: str
    origin: str
    allowed_routes: tuple[str, ...]
    allowed_use: str
    candidate_only: bool = True
    local_preferred: bool = True
    hosted_upload_possible: bool = False
    requires_approved_keyposes: bool = False
    requires_deidentification: bool = False
    requires_reimport: bool = True
    long_term_only: bool = False
    freeze_required: bool = True
    admission_required: bool = True


ADAPTERS: dict[str, AdapterRule] = {
    "ipadapter_comfyui": AdapterRule(
        name="ipadapter_comfyui",
        origin="local_comfyui_or_hf_model",
        allowed_routes=(
            "local_part_transform_or_masked_edit",
            "part_transform_with_local_hand_glasses_repair",
            "lora_ipadapter_or_component_rig_candidate",
        ),
        allowed_use="local part identity lock, local part redraw, or missing part generation",
        hosted_upload_possible=True,
    ),
    "tooncrafter": AdapterRule(
        name="tooncrafter",
        origin="github_or_hf_interpolation_tool",
        allowed_routes=("interpolation_route",),
        allowed_use="in-between generation between approved keyposes",
        hosted_upload_possible=True,
        requires_approved_keyposes=True,
    ),
    "animate_x_wan": AdapterRule(
        name="animate_x_wan",
        origin="github_or_hf_video_animation_tool",
        allowed_routes=("external_animation_provider_candidate",),
        allowed_use="large full-body action candidate video, then extracted candidate frames",
        hosted_upload_possible=True,
        requires_deidentification=True,
        requires_reimport=True,
    ),
    "spine_live2d_dragonbones": AdapterRule(
        name="spine_live2d_dragonbones",
        origin="manual_or_tool_assisted_true_rig",
        allowed_routes=("lora_ipadapter_or_component_rig_candidate",),
        allowed_use="long-term true rig production for repeated characters",
        hosted_upload_possible=False,
        long_term_only=True,
    ),
}


def normalize(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_report(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    adapter_name = normalize(args.adapter)
    route = normalize(args.route)
    blockers: list[str] = []
    warnings: list[str] = []
    rule = ADAPTERS.get(adapter_name)

    if rule is None:
        blockers.append(f"unknown adapter: {adapter_name}")
        report = {
            "schema_version": "sofunny-route-adapter-report.v1",
            "status": "fail",
            "adapter": adapter_name,
            "route": route,
            "blockers": blockers,
            "warnings": warnings,
        }
        return report, 1

    if route not in rule.allowed_routes:
        blockers.append(f"adapter {adapter_name} is not allowed for route {route}")

    if rule.requires_approved_keyposes and not args.approved_keyposes:
        blockers.append(f"adapter {adapter_name} requires approved endpoint keyposes")

    if rule.requires_deidentification and not args.deidentified_input:
        blockers.append(f"adapter {adapter_name} requires de-identified input")

    if rule.requires_reimport and not args.reimport_through_gates:
        blockers.append(f"adapter {adapter_name} output must be re-imported through SoFunny gates")

    if args.hosted_external and not args.external_upload_allowed:
        blockers.append("hosted external adapter upload is blocked without explicit permission")

    if args.hosted_external and not rule.hosted_upload_possible:
        blockers.append(f"adapter {adapter_name} is not a hosted external upload adapter")

    if rule.long_term_only and not args.allow_long_term_rig:
        blockers.append(f"adapter {adapter_name} is long-term rig scope, not first-round MVP")

    if rule.candidate_only:
        warnings.append("adapter output is candidate-only and cannot set production_approved")

    status = "pass" if not blockers else "fail"
    report = {
        "schema_version": "sofunny-route-adapter-report.v1",
        "status": status,
        "adapter": adapter_name,
        "origin": rule.origin,
        "route": route,
        "allowed_routes": list(rule.allowed_routes),
        "allowed_use": rule.allowed_use,
        "candidate_only": rule.candidate_only,
        "local_preferred": rule.local_preferred,
        "hosted_external": args.hosted_external,
        "external_upload_allowed": args.external_upload_allowed,
        "approved_keyposes": args.approved_keyposes,
        "deidentified_input": args.deidentified_input,
        "reimport_through_gates": args.reimport_through_gates,
        "freeze_required": rule.freeze_required,
        "admission_required": rule.admission_required,
        "blockers": blockers,
        "warnings": warnings,
    }
    return report, 0 if status == "pass" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", required=True)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--approved-keyposes", action="store_true")
    parser.add_argument("--deidentified-input", action="store_true")
    parser.add_argument("--reimport-through-gates", action="store_true")
    parser.add_argument("--hosted-external", action="store_true")
    parser.add_argument("--external-upload-allowed", action="store_true")
    parser.add_argument("--allow-long-term-rig", action="store_true")
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    report, code = build_report(args)
    output = args.output
    if not output and args.run_dir:
        output = str(Path(args.run_dir) / "route_adapter_report.json")
    if output:
        write_json(Path(output).expanduser().resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
