#!/usr/bin/env python3
"""Report repeated generation failures and enforce pivot budgets."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


MAX_SAME_ROUTE_ATTEMPTS = 2
MAX_SAME_FAILURE_CLASS = 2

PIVOT_ACTIONS = {
    "identity_drift": "pivot_to_source_animation_route",
    "pose_weak": "revise_action_component_plan",
    "tail_artifact": "part-level tail repair or tail rig",
    "loop_pop": "revise recover phase before GIF export",
    "choppy_timing": "increase approved keyposes before timing",
    "part_map_manual_required": "manual part map or narrower part-level repair",
    "part_consistency_fail": "create local part repair packet before freeze",
    "provider_layout_fail": "fix provider layout or re-import through SoFunny intake",
}


def normalize(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def parse_attempt(value: str) -> dict[str, Any]:
    parts = value.split(":")
    if len(parts) < 2:
        raise argparse.ArgumentTypeError("attempt must be route:failure_class or route:failure_class:status")
    route, failure_class = normalize(parts[0]), normalize(parts[1])
    status = normalize(parts[2]) if len(parts) > 2 else "fail"
    return {"route": route, "failure_class": failure_class, "status": status}


def load_history(path: str) -> list[dict[str, Any]]:
    if not path:
        return []
    data = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if isinstance(data, list):
        attempts = data
    else:
        attempts = data.get("attempts", [])
    if not isinstance(attempts, list):
        raise ValueError("history attempts must be a list")
    normalized: list[dict[str, Any]] = []
    for item in attempts:
        if not isinstance(item, dict):
            raise ValueError("each attempt must be an object")
        normalized.append({
            "route": normalize(str(item.get("route", "unknown"))),
            "failure_class": normalize(str(item.get("failure_class", item.get("failure", "unknown")))),
            "status": normalize(str(item.get("status", "fail"))),
        })
    return normalized


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_report(attempts: list[dict[str, Any]]) -> tuple[dict[str, Any], int]:
    failed = [item for item in attempts if item.get("status") not in {"pass", "passed", "ok"}]
    blockers: list[str] = []
    warnings: list[str] = []
    route_counts = Counter(item.get("route", "unknown") for item in failed)
    failure_counts = Counter(item.get("failure_class", "unknown") for item in failed)
    latest = failed[-1] if failed else None

    recommended_action = "continue_current_route"
    latest_route = latest.get("route", "unknown") if latest else None
    latest_failure = latest.get("failure_class", "unknown") if latest else None
    same_route_count = route_counts.get(latest_route, 0) if latest_route else 0
    same_failure_count = failure_counts.get(latest_failure, 0) if latest_failure else 0

    if latest:
        recommended_action = PIVOT_ACTIONS.get(latest_failure or "unknown", "switch_route_or_scope_to_part_level_repair")
        if same_route_count >= MAX_SAME_ROUTE_ATTEMPTS:
            blockers.append(f"same route reached budget: {latest_route} count={same_route_count}")
        if same_failure_count >= MAX_SAME_FAILURE_CLASS:
            blockers.append(f"same failure class reached budget: {latest_failure} count={same_failure_count}")
        if latest_failure == "unknown":
            warnings.append("latest failure class is unknown; classify before another generation attempt")

    pivot_required = bool(blockers)
    status = "pivot_required" if pivot_required else "pass"
    prompt_polishing_allowed = not pivot_required
    prohibited_next_actions = []
    next_allowed_actions = ["continue_current_route"] if not pivot_required else []
    if pivot_required:
        prohibited_next_actions = [
            "same_route_generation",
            "prompt_polishing",
            "best_of_n_same_route_retry",
            "gif_timing_palette_or_compression_tweak_as_source_fix",
        ]
        next_allowed_actions = [
            recommended_action,
            "switch_route",
            "narrow_to_part_level_repair",
            "revise_source_animation_contract",
        ]
    report = {
        "schema_version": "sofunny-retry-tax-report.v1",
        "status": status,
        "pivot_required": pivot_required,
        "prompt_polishing_allowed": prompt_polishing_allowed,
        "budget": {
            "max_same_route_attempts": MAX_SAME_ROUTE_ATTEMPTS,
            "max_same_failure_class": MAX_SAME_FAILURE_CLASS,
        },
        "attempt_count": len(attempts),
        "failed_attempt_count": len(failed),
        "latest_route": latest_route,
        "latest_failure_class": latest_failure,
        "same_route_count": same_route_count,
        "same_failure_class_count": same_failure_count,
        "recommended_action": recommended_action,
        "next_allowed_actions": next_allowed_actions,
        "prohibited_next_actions": prohibited_next_actions,
        "route_counts": dict(route_counts),
        "failure_class_counts": dict(failure_counts),
        "blockers": blockers,
        "warnings": warnings,
    }
    return report, 1 if blockers else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", default="")
    parser.add_argument("--attempt", action="append", type=parse_attempt, default=[])
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    attempts = load_history(args.history) + list(args.attempt)
    report, code = build_report(attempts)
    output = args.output
    if not output and args.run_dir:
        output = str(Path(args.run_dir) / "retry_tax_report.json")
    if output:
        write_json(Path(output).expanduser().resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
