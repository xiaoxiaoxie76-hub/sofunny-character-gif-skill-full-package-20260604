#!/usr/bin/env python3
"""Generate bounded part motion curves from source-animation contracts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sofunny_anim.easing import SUPPORTED_CURVES, curve_between


DEFAULT_PART_PARAMETER_CONTRACT = {
    "schema_version": "sofunny-part-parameter-contract.v1",
    "parameters": {
        "body_bob": {
            "parts": ["torso"],
            "translate_y_px": [-2, 2],
            "curve": "ease_in_out_sine",
            "phase_offset": 0,
        },
        "head_follow": {
            "parts": ["head"],
            "translate_y_px": [-3, 3],
            "rotation_deg": [-2, 2],
            "curve": "ease_out_quad",
            "phase_offset": 0.15,
        },
        "tail_lag": {
            "parts": ["tail"],
            "rotation_deg": [-8, 8],
            "curve": "ease_out_back",
            "phase_offset": 0.25,
            "must_remain_attached": True,
        },
        "arm_counter_swing": {
            "parts": ["left_arm", "right_arm"],
            "rotation_deg": [-10, 10],
            "curve": "sine_loop",
            "phase_offset": 0.5,
            "mirror_pairs": [["left_arm", "right_arm"]],
        },
        "torso_squash_stretch": {
            "parts": ["torso"],
            "scale_x": [0.985, 1.015],
            "scale_y": [1.015, 0.985],
            "curve": "ease_in_out_sine",
            "phase_offset": 0,
        },
    },
}


def read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        if default is None:
            raise FileNotFoundError(str(path))
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def numeric_range(value: Any, field: str) -> tuple[float, float]:
    if not (isinstance(value, list) and len(value) == 2 and all(isinstance(item, (int, float)) for item in value)):
        raise ValueError(f"{field} must be [min, max] numeric values")
    return float(value[0]), float(value[1])


def movable_limits(contract: dict[str, Any]) -> dict[str, dict[str, float]]:
    limits: dict[str, dict[str, float]] = {}
    for entry in contract.get("movable_parts", []):
        if isinstance(entry, str):
            limits[entry] = {"max_translation_px": 4.0, "max_rotation_deg": 4.0}
            continue
        if isinstance(entry, dict) and entry.get("part"):
            part = str(entry["part"])
            limits[part] = {
                "max_translation_px": float(entry.get("max_translation_px", 4.0) or 4.0),
                "max_rotation_deg": float(entry.get("max_rotation_deg", 4.0) or 4.0),
                "max_scale_delta": float(entry.get("max_scale_delta", 0.08) or 0.08),
            }
    return limits


def mirror_sign(part: str, mirror_pairs: list[Any]) -> float:
    for pair in mirror_pairs:
        if isinstance(pair, list) and len(pair) == 2:
            left, right = str(pair[0]), str(pair[1])
            if part == left:
                return 1.0
            if part == right:
                return -1.0
    return 1.0


def clamp_with_report(value: float, limit: float, field: str, part: str, clamps: list[str]) -> float:
    clamped = max(-limit, min(limit, value))
    if clamped != value:
        clamps.append(f"{part}.{field} clamped from {round(value, 4)} to {round(clamped, 4)}")
    return clamped


def apply_delta(target: dict[str, Any], field: str, value: float) -> None:
    if field == "translate_y_px":
        translate = target.setdefault("translate", [0.0, 0.0])
        translate[1] = round(float(translate[1]) + value, 4)
    elif field == "rotation_deg":
        target["rotate"] = round(float(target.get("rotate", 0.0) or 0.0) + value, 4)
    elif field == "scale_x":
        scale = target.setdefault("scale", [1.0, 1.0])
        scale[0] = round(float(scale[0]) * value, 5)
    elif field == "scale_y":
        scale = target.setdefault("scale", [1.0, 1.0])
        scale[1] = round(float(scale[1]) * value, 5)


def validate_parameters(parameters: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(parameters, dict) or not parameters:
        raise ValueError("part_parameter_contract.parameters must be a non-empty object")
    for name, spec in parameters.items():
        if not isinstance(spec, dict):
            raise ValueError(f"parameter {name} must be an object")
        parts = spec.get("parts")
        if not isinstance(parts, list) or not parts or not all(isinstance(part, str) for part in parts):
            raise ValueError(f"parameter {name}.parts must be a non-empty list of part names")
        curve = str(spec.get("curve", "sine_loop"))
        if curve not in SUPPORTED_CURVES:
            raise ValueError(f"parameter {name}.curve is unsupported: {curve}")
    return parameters


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--action-plan", default="action_component_plan.json")
    parser.add_argument("--movable-contract", default="movable_parts_contract.json")
    parser.add_argument("--part-parameter-contract", default="part_parameter_contract.json")
    parser.add_argument("--output", default="part_motion_curves.json")
    parser.add_argument("--strict-limits", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    action_plan = read_json(run_dir / args.action_plan)
    movable = read_json(run_dir / args.movable_contract)
    parameter_contract = read_json(run_dir / args.part_parameter_contract, DEFAULT_PART_PARAMETER_CONTRACT)

    phases = action_plan.get("phases", [])
    if not isinstance(phases, list) or len(phases) < 2:
        raise ValueError("action_component_plan.phases must contain at least two phases")
    limits = movable_limits(movable)
    parameters = validate_parameters(parameter_contract.get("parameters"))

    curves: dict[str, list[dict[str, Any]]] = {}
    clamps: list[str] = []
    findings: list[str] = []
    frame_count = len(phases)
    denominator = max(1, frame_count - 1)

    for index, phase in enumerate(phases):
        frame = int(phase.get("frame", index))
        progress = index / denominator
        for parameter_name, spec in parameters.items():
            curve = str(spec.get("curve", "sine_loop"))
            phase_offset = float(spec.get("phase_offset", 0.0) or 0.0)
            mirror_pairs = spec.get("mirror_pairs", [])
            for part in spec["parts"]:
                if part not in limits:
                    findings.append(f"parameter {parameter_name} targets undeclared movable part {part}")
                    continue
                target = curves.setdefault(part, [])
                while len(target) <= index:
                    target.append({"frame": phases[len(target)].get("frame", len(target)), "translate": [0.0, 0.0], "rotate": 0.0, "scale": [1.0, 1.0], "sources": []})
                record = target[index]
                sign = mirror_sign(part, mirror_pairs)
                for field in ("translate_y_px", "rotation_deg", "scale_x", "scale_y"):
                    if field not in spec:
                        continue
                    low, high = numeric_range(spec[field], f"{parameter_name}.{field}")
                    value = curve_between(low, high, curve, progress, phase_offset)
                    if field == "rotation_deg":
                        value = clamp_with_report(value * sign, limits[part].get("max_rotation_deg", 4.0), "rotation_deg", part, clamps)
                    elif field == "translate_y_px":
                        value = clamp_with_report(value, limits[part].get("max_translation_px", 4.0), "translate_y_px", part, clamps)
                    elif field in {"scale_x", "scale_y"}:
                        max_delta = limits[part].get("max_scale_delta", 0.08)
                        value = max(1.0 - max_delta, min(1.0 + max_delta, value))
                    apply_delta(record, field, value)
                record["sources"].append(parameter_name)

    status = "pass"
    if findings or (args.strict_limits and clamps):
        status = "fail"
    payload = {
        "schema_version": "sofunny-part-motion-curves.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "action_plan": args.action_plan,
        "movable_contract": args.movable_contract,
        "part_parameter_contract": args.part_parameter_contract if (run_dir / args.part_parameter_contract).exists() else "default",
        "frame_count": frame_count,
        "curves": curves,
        "principles": {
            "parameter_driven_secondary_motion": True,
            "full_frame_redraw": False,
            "curve_families": sorted({str(spec.get("curve", "sine_loop")) for spec in parameters.values()}),
        },
        "clamps": clamps,
        "findings": findings,
    }
    write_json(run_dir / args.output, payload)
    if status != "pass":
        for finding in findings + clamps:
            print(f"- {finding}")
        return 1
    print(json.dumps({"status": "pass", "output": args.output, "parts": sorted(curves)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
