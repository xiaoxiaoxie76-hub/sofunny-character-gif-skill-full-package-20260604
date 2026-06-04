#!/usr/bin/env python3
"""Run SoFunny skill contract and admission regression checks."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from audit_admission_enforcement import manifest_production_approved, run_finalize, write_base_fixture, write_json


ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "regression_cases"


@dataclass
class CommandResult:
    name: str
    command: list[str]
    returncode: int
    passed: bool
    stdout_tail: list[str]
    stderr_tail: list[str]


@dataclass
class CaseResult:
    name: str
    description: str
    passed: bool
    run_dir: str
    expected: dict[str, Any]
    actual: dict[str, Any]
    evidence: list[str]


def run_command(name: str, command: list[str], expected_returncode: int = 0) -> CommandResult:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    return CommandResult(
        name=name,
        command=command,
        returncode=result.returncode,
        passed=result.returncode == expected_returncode,
        stdout_tail=result.stdout.strip().splitlines()[-8:] if result.stdout.strip() else [],
        stderr_tail=result.stderr.strip().splitlines()[-8:] if result.stderr.strip() else [],
    )


def create_tooncrafter_smoke_fixture(temp_root: Path) -> tuple[Path, Path]:
    run_dir = temp_root / "tooncrafter_smoke"
    accepted = run_dir / "accepted_keyposes"
    segment = temp_root / "tooncrafter_segment_frames"
    accepted.mkdir(parents=True)
    segment.mkdir(parents=True)

    frames = []
    for index, x in enumerate((120, 170)):
        image = Image.new("RGBA", (384, 384), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((x, 110, x + 90, 200), fill=(240, 190, 90, 255), outline=(50, 50, 50, 255), width=4)
        draw.rectangle((x + 20, 200, x + 70, 285), fill=(90, 160, 240, 255), outline=(50, 50, 50, 255), width=4)
        path = accepted / f"{index:03d}.png"
        image.save(path)
        frames.append(image)

    manifest = {
        "schema_version": "sofunny-keypose-freeze.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_run": str(run_dir),
        "accepted_keyposes": str(accepted),
        "frame_count": 2,
        "canvas": {"width": 384, "height": 384},
        "frames": [
            {"index": 0, "file": "accepted_keyposes/000.png", "phase": "contact"},
            {"index": 1, "file": "accepted_keyposes/001.png", "phase": "passing"},
        ],
    }
    write_json(run_dir / "keypose_freeze_manifest.json", manifest)

    for index, alpha in enumerate((0.0, 0.33, 0.66, 1.0)):
        blended = Image.blend(frames[0], frames[1], alpha)
        blended.save(segment / f"{index:03d}.png")
    return run_dir, segment


def run_tooncrafter_smoke(temp_root: Path) -> CommandResult:
    run_dir, segment = create_tooncrafter_smoke_fixture(temp_root)
    commands = [
        [sys.executable, str(ROOT / "scripts" / "build_interpolation_pairs.py"), "--run-dir", str(run_dir)],
        [sys.executable, str(ROOT / "scripts" / "create_tooncrafter_packet.py"), "--run-dir", str(run_dir), "--pair-id", "pair_000_001"],
        [
            sys.executable,
            str(ROOT / "scripts" / "import_tooncrafter_segment.py"),
            "--run-dir",
            str(run_dir),
            "--pair-id",
            "pair_000_001",
            "--segment-dir",
            str(segment),
            "--target-canvas",
            "384x384",
        ],
        [sys.executable, str(ROOT / "scripts" / "audit_interpolated_segment.py"), "--run-dir", str(run_dir), "--pair-id", "pair_000_001"],
    ]
    stdout: list[str] = []
    stderr: list[str] = []
    returncode = 0
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        stdout.extend(result.stdout.strip().splitlines() if result.stdout.strip() else [])
        stderr.extend(result.stderr.strip().splitlines() if result.stderr.strip() else [])
        if result.returncode != 0:
            returncode = result.returncode
            break
    return CommandResult(
        name="tooncrafter_interpolation_smoke",
        command=["tooncrafter_interpolation_smoke"],
        returncode=returncode,
        passed=returncode == 0,
        stdout_tail=stdout[-8:],
        stderr_tail=stderr[-8:],
    )


def create_ipadapter_smoke_fixture(temp_root: Path) -> tuple[Path, Path, Path, Path]:
    run_dir = temp_root / "ipadapter_smoke"
    input_dir = temp_root / "ipadapter_inputs"
    run_dir.mkdir(parents=True)
    input_dir.mkdir(parents=True)

    failed = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(failed)
    draw.rectangle((40, 40, 88, 92), fill=(240, 190, 90, 255), outline=(40, 40, 40, 255), width=3)
    draw.line((52, 58, 76, 58), fill=(255, 0, 0, 255), width=3)
    failed_path = input_dir / "failed_frame.png"
    failed.save(failed_path)

    canonical = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canonical)
    draw.rectangle((40, 40, 88, 92), fill=(240, 190, 90, 255), outline=(40, 40, 40, 255), width=3)
    draw.ellipse((52, 55, 64, 67), fill=(30, 30, 30, 255))
    draw.ellipse((68, 55, 80, 67), fill=(30, 30, 30, 255))
    canonical_path = input_dir / "canonical_reference.png"
    canonical.save(canonical_path)

    mask = Image.new("L", (128, 128), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rectangle((50, 52, 82, 70), fill=255)
    mask_path = input_dir / "part_mask.png"
    mask.save(mask_path)

    repair = failed.copy()
    repair_draw = ImageDraw.Draw(repair)
    repair_draw.ellipse((52, 55, 64, 67), fill=(30, 30, 30, 255))
    repair_draw.ellipse((68, 55, 80, 67), fill=(30, 30, 30, 255))
    repair_path = input_dir / "repair_output.png"
    repair.save(repair_path)
    return run_dir, failed_path, canonical_path, mask_path, repair_path


def run_ipadapter_smoke(temp_root: Path) -> CommandResult:
    run_dir, failed, canonical, mask, repair = create_ipadapter_smoke_fixture(temp_root)
    packet_dir = run_dir / "ipadapter_part_repair_packets" / "face"
    commands = [
        [
            sys.executable,
            str(ROOT / "scripts" / "create_ipadapter_part_repair_packet.py"),
            "--run-dir",
            str(run_dir),
            "--part-name",
            "face",
            "--failure-reason",
            "face local feature deformed",
            "--failed-frame",
            str(failed),
            "--part-mask",
            str(mask),
            "--canonical-reference",
            str(canonical),
        ],
        [
            sys.executable,
            str(ROOT / "scripts" / "import_ipadapter_part_repair.py"),
            "--run-dir",
            str(run_dir),
            "--packet-dir",
            str(packet_dir),
            "--repair-output",
            str(repair),
            "--part-name",
            "face",
        ],
    ]
    stdout: list[str] = []
    stderr: list[str] = []
    returncode = 0
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        stdout.extend(result.stdout.strip().splitlines() if result.stdout.strip() else [])
        stderr.extend(result.stderr.strip().splitlines() if result.stderr.strip() else [])
        if result.returncode != 0:
            returncode = result.returncode
            break
    return CommandResult(
        name="ipadapter_part_repair_smoke",
        command=["ipadapter_part_repair_smoke"],
        returncode=returncode,
        passed=returncode == 0,
        stdout_tail=stdout[-8:],
        stderr_tail=stderr[-8:],
    )


def create_animatex_smoke_fixture(temp_root: Path) -> tuple[Path, Path, Path, Path]:
    run_dir = temp_root / "animatex_smoke"
    input_dir = temp_root / "animatex_inputs"
    frames_dir = temp_root / "animatex_output_frames"
    run_dir.mkdir(parents=True)
    input_dir.mkdir(parents=True)
    frames_dir.mkdir(parents=True)

    canonical = Image.new("RGBA", (384, 384), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canonical)
    draw.ellipse((140, 80, 244, 184), fill=(240, 190, 90, 255), outline=(50, 50, 50, 255), width=4)
    draw.rectangle((155, 184, 229, 300), fill=(90, 160, 240, 255), outline=(50, 50, 50, 255), width=4)
    canonical_path = input_dir / "canonical_character.png"
    canonical.save(canonical_path)

    motion_video = input_dir / "deidentified_motion.mp4"
    motion_video.write_bytes(b"deidentified motion placeholder")

    for index in range(8):
        frame = Image.new("RGBA", (768, 512), (0, 0, 0, 0))
        frame_draw = ImageDraw.Draw(frame)
        x = 250 + index * 8
        y = 105 + (index % 3) * 6
        frame_draw.ellipse((x, y, x + 120, y + 120), fill=(240, 190, 90, 255), outline=(50, 50, 50, 255), width=4)
        frame_draw.rectangle((x + 25, y + 120, x + 95, y + 260), fill=(90, 160, 240, 255), outline=(50, 50, 50, 255), width=4)
        frame_draw.line((x + 25, y + 170, x - 25, y + 225), fill=(50, 50, 50, 255), width=8)
        frame_draw.line((x + 95, y + 170, x + 155, y + 215), fill=(50, 50, 50, 255), width=8)
        frame.save(frames_dir / f"{index:03d}.png")
    return run_dir, canonical_path, motion_video, frames_dir


def run_animatex_smoke(temp_root: Path) -> CommandResult:
    run_dir, canonical, motion_video, frames_dir = create_animatex_smoke_fixture(temp_root)
    packet_path = run_dir / "animatex_packets" / "large_full_body_action" / "animatex_packet.json"
    commands_with_expected = [
        (
            [
                sys.executable,
                str(ROOT / "scripts" / "create_animatex_packet.py"),
                "--run-dir",
                str(run_dir),
                "--canonical-reference",
                str(canonical),
                "--motion-video",
                str(motion_video),
                "--action",
                "large_full_body_action",
            ],
            1,
        ),
        (
            [
                sys.executable,
                str(ROOT / "scripts" / "create_animatex_packet.py"),
                "--run-dir",
                str(run_dir),
                "--canonical-reference",
                str(canonical),
                "--motion-video",
                str(motion_video),
                "--action",
                "large_full_body_action",
                "--deidentified-motion",
            ],
            0,
        ),
        (
            [
                sys.executable,
                str(ROOT / "scripts" / "import_animatex_video_frames.py"),
                "--run-dir",
                str(run_dir),
                "--frames-dir",
                str(frames_dir),
                "--packet",
                str(packet_path),
                "--target-canvas",
                "384x384",
                "--expected-min-frames",
                "8",
            ],
            0,
        ),
        (
            [sys.executable, str(ROOT / "scripts" / "audit_video_provider_frames.py"), "--run-dir", str(run_dir), "--min-frames", "8"],
            0,
        ),
    ]
    stdout: list[str] = []
    stderr: list[str] = []
    returncode = 0
    for command, expected in commands_with_expected:
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        stdout.extend(result.stdout.strip().splitlines() if result.stdout.strip() else [])
        stderr.extend(result.stderr.strip().splitlines() if result.stderr.strip() else [])
        if result.returncode != expected:
            returncode = result.returncode
            break
    return CommandResult(
        name="animatex_video_provider_smoke",
        command=["animatex_video_provider_smoke"],
        returncode=returncode,
        passed=returncode == 0,
        stdout_tail=stdout[-8:],
        stderr_tail=stderr[-8:],
    )


def run_hard_split_component_plan_block_smoke(temp_root: Path) -> CommandResult:
    run_dir = temp_root / "hard_split_component_plan_block"
    run_dir.mkdir(parents=True)
    write_json(run_dir / "part_map.json", {
        "schema_version": "sofunny-part-map.v1",
        "review_status": "candidate_review_required",
        "canvas": {"width": 128, "height": 128},
        "parts": [
            {"name": "head", "file": "parts/head.png"},
            {"name": "torso", "file": "parts/torso.png"},
            {"name": "left_arm", "file": "parts/left_arm.png"},
            {"name": "right_arm", "file": "parts/right_arm.png"},
            {"name": "tail", "file": "parts/tail.png"}
        ],
    })
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "create_action_component_plan.py"),
            "--run-dir",
            str(run_dir),
            "--action",
            "sherry_tail_wave_greeting",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    return CommandResult(
        name="hard_split_component_plan_blocks_by_default",
        command=["hard_split_component_plan_blocks_by_default"],
        returncode=result.returncode,
        passed=result.returncode == 1 and "diagnostic-only" in result.stdout,
        stdout_tail=result.stdout.strip().splitlines()[-8:] if result.stdout.strip() else [],
        stderr_tail=result.stderr.strip().splitlines()[-8:] if result.stderr.strip() else [],
    )


def run_catch_falling_petal_hard_split_blocks_smoke(temp_root: Path) -> CommandResult:
    run_dir = temp_root / "catch_falling_petal_hard_split_block"
    parts_dir = run_dir / "parts"
    parts_dir.mkdir(parents=True)
    for part in ["head", "torso", "left_arm", "right_arm", "tail"]:
        image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((30, 30, 90, 90), fill=(120, 180, 160, 255))
        image.save(parts_dir / f"{part}.png")
    write_json(run_dir / "route_selection_report.json", {
        "schema_version": "sofunny-route-selection-report.v1",
        "status": "fail",
        "action": "catch_falling_petal",
        "run_type": "production",
        "recommended_route": None,
        "proposed_route": "source_animation_component_plan_with_local_hand_redraw",
        "blockers": ["unknown action route: catch_falling_petal"],
    })
    write_json(run_dir / "manual_route_override.json", {
        "schema_version": "sofunny-manual-route-override.v1",
        "status": "manual_override_required",
        "selected_route": "source_animation_component_plan_with_local_hand_redraw",
    })
    write_json(run_dir / "part_map.json", {
        "schema_version": "sofunny-part-map.v1",
        "review_status": "draft_manual_review_required",
        "route": "source_animation_component_plan_with_local_hand_redraw",
        "canvas": {"width": 128, "height": 128},
        "parts": [
            {"name": part, "file": f"parts/{part}.png", "render": True}
            for part in ["head", "torso", "left_arm", "right_arm", "tail"]
        ],
        "render_order": ["tail", "torso", "left_arm", "right_arm", "head"],
    })
    write_json(run_dir / "identity_parts_contract.json", {
        "schema_version": "sofunny-identity-parts.v1",
        "fixed_identity_parts": [{"part": "head"}, {"part": "torso"}],
    })
    write_json(run_dir / "movable_parts_contract.json", {
        "schema_version": "sofunny-movable-parts.v1",
        "movable_parts": [{"part": "right_arm"}, {"part": "left_arm"}, {"part": "tail"}],
    })
    write_json(run_dir / "action_component_plan.json", {
        "schema_version": "sofunny-action-component-plan.v1",
        "action_name": "catch_falling_petal",
        "route": "source_animation_component_plan_with_local_hand_redraw",
        "phases": [
            {
                "name": "K06_half_closed_contact",
                "frame": 0,
                "body_y": 0,
                "head_y": 0,
                "head_rotation": 0,
                "arm_rotation": 30,
                "leg_phase": "grounded",
                "tail_rotation": 2,
                "tail_lag": 1,
                "squash_stretch": [1, 1],
                "optional_expression_variant": None,
                "transforms": {"right_arm": {"translate": [-20, -30], "rotate": -30, "scale": [1, 1]}},
                "required_visual_change": "petal partly occluded by hand",
            }
        ],
    })
    write_json(run_dir / "part_consistency_report.json", {
        "schema_version": "sofunny-part-consistency.v1",
        "status": "manual_required",
        "findings": ["hand/petal local redraw missing"],
    })
    command = [sys.executable, str(ROOT / "scripts" / "generate_component_keyposes.py"), "--run-dir", str(run_dir)]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    return CommandResult(
        name="catch_falling_petal_hard_split_blocks_generation",
        command=command,
        returncode=result.returncode,
        passed=result.returncode == 1 and "diagnostic-only" in result.stderr + result.stdout,
        stdout_tail=result.stdout.strip().splitlines()[-8:] if result.stdout.strip() else [],
        stderr_tail=result.stderr.strip().splitlines()[-8:] if result.stderr.strip() else [],
    )


def create_component_generation_fixture(
    run_dir: Path,
    *,
    route: str,
    route_status: str = "pass",
    action: str = "test_action",
    provenance: str = "production_clean_components",
    review_status: str = "approved",
    manual_override: bool = False,
    omit_component_integrity: bool = False,
) -> None:
    parts_dir = run_dir / "parts"
    parts_dir.mkdir(parents=True)
    for part in ["head", "torso", "left_arm", "right_arm", "tail"]:
        image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((30, 30, 90, 90), fill=(120, 180, 160, 255))
        image.save(parts_dir / f"{part}.png")
    write_json(run_dir / "route_selection_report.json", {
        "schema_version": "sofunny-route-selection-report.v1",
        "status": route_status,
        "action": action,
        "run_type": "production_candidate",
        "recommended_route": route,
        "proposed_route": route,
        "blockers": [] if route_status == "pass" else ["fixture route failure"],
    })
    if manual_override:
        write_json(run_dir / "manual_route_override.json", {
            "schema_version": "sofunny-manual-route-override.v1",
            "status": "pass",
            "selected_route": route,
        })
    write_json(run_dir / "part_map.json", {
        "schema_version": "sofunny-part-map.v1",
        "review_status": review_status,
        "segmentation_provenance": provenance,
        "route": route,
        "canvas": {"width": 128, "height": 128},
        "parts": [
            {"name": part, "file": f"parts/{part}.png", "render": True}
            for part in ["head", "torso", "left_arm", "right_arm", "tail"]
        ],
        "render_order": ["tail", "torso", "left_arm", "right_arm", "head"],
    })
    write_json(run_dir / "identity_parts_contract.json", {
        "schema_version": "sofunny-identity-parts.v1",
        "fixed_identity_parts": [{"part": "head"}, {"part": "torso"}],
    })
    write_json(run_dir / "movable_parts_contract.json", {
        "schema_version": "sofunny-movable-parts.v1",
        "movable_parts": [{"part": "right_arm"}, {"part": "left_arm"}, {"part": "tail"}],
    })
    if not omit_component_integrity:
        write_json(run_dir / "component_integrity_report.json", {
            "schema_version": "sofunny-component-integrity.v1",
            "status": "pass",
            "findings": [],
        })
    write_json(run_dir / "part_consistency_report.json", {
        "schema_version": "sofunny-part-consistency.v1",
        "status": "pass",
        "findings": [],
    })
    write_json(run_dir / "action_component_plan.json", {
        "schema_version": "sofunny-action-component-plan.v1",
        "action_name": action,
        "route": route,
        "phases": [
            {
                "name": "phase_0",
                "frame": 0,
                "body_y": 0,
                "head_y": 0,
                "head_rotation": 0,
                "arm_rotation": 30,
                "leg_phase": "grounded",
                "tail_rotation": 2,
                "tail_lag": 1,
                "squash_stretch": [1, 1],
                "optional_expression_variant": None,
                "transforms": {"right_arm": {"translate": [-20, -30], "rotate": -30, "scale": [1, 1]}},
                "required_visual_change": "fixture component motion",
            }
        ],
    })


def run_component_generation_gate_smoke(temp_root: Path) -> CommandResult:
    scenarios = [
        (
            "component_generation_clean_pass",
            {"route": "clean_layer_component_route"},
            0,
            "",
        ),
        (
            "component_generation_blocks_forged_manual_override",
            {
                "route": "source_animation_component_plan_with_local_hand_redraw",
                "route_status": "fail",
                "manual_override": True,
            },
            1,
            "manual_route_override.json cannot feed deterministic component keypose generation",
        ),
        (
            "component_generation_blocks_dirty_provenance_even_with_pass_report",
            {
                "route": "clean_layer_component_route",
                "provenance": "single_image_hard_split",
                "review_status": "diagnostic_only",
            },
            1,
            "single-image/auto/box/flat/unknown component provenance is diagnostic-only",
        ),
        (
            "component_generation_blocks_missing_component_integrity",
            {"route": "clean_layer_component_route", "omit_component_integrity": True},
            1,
            "component_integrity_report.json is required",
        ),
    ]
    stdout: list[str] = []
    stderr: list[str] = []
    passed = True
    returncode = 0
    for name, fixture, expected_code, expected_text in scenarios:
        run_dir = temp_root / name
        create_component_generation_fixture(run_dir, **fixture)
        command = [sys.executable, str(ROOT / "scripts" / "generate_component_keyposes.py"), "--run-dir", str(run_dir)]
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        output = result.stdout + result.stderr
        scenario_passed = result.returncode == expected_code and (not expected_text or expected_text in output)
        stdout.append(f"{name}_returncode={result.returncode}")
        if expected_text:
            stdout.append(f"{name}_matched_expected_text={expected_text in output}")
        if not scenario_passed:
            passed = False
            returncode = result.returncode
        stderr.extend(result.stderr.strip().splitlines()[-2:] if result.stderr.strip() else [])
    return CommandResult(
        name="component_generation_gate_smoke",
        command=["component_generation_gate_smoke"],
        returncode=returncode,
        passed=passed,
        stdout_tail=stdout[-12:],
        stderr_tail=stderr[-8:],
    )


def run_freeze_enforcement_smoke(temp_root: Path) -> CommandResult:
    scenarios = [
        ("freeze_pass", {}, 0),
        ("freeze_blocks_missing_route_selection", {"omit_route_selection": True}, 1),
        ("freeze_blocks_retry_pivot", {"retry_pivot_required": True}, 1),
        ("freeze_blocks_missing_lively_motion", {"omit_lively_motion": True}, 1),
        ("freeze_blocks_tooncrafter_missing_audit", {"adapter": "tooncrafter", "omit_adapter_audit": True}, 1),
    ]
    stdout: list[str] = []
    stderr: list[str] = []
    returncode = 0
    for name, fixture, expected in scenarios:
        run_dir = temp_root / name
        write_base_fixture(run_dir, **fixture)
        valid_frame = Image.new("RGBA", (1, 1), (255, 0, 0, 255))
        valid_frame.save(run_dir / "sequence_frames" / "000.png")
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "freeze_keyposes.py"),
                "--run-dir",
                str(run_dir),
                "--canvas",
                "1x1",
                "--stage",
                "production",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        stdout.extend(result.stdout.strip().splitlines() if result.stdout.strip() else [])
        stderr.extend(result.stderr.strip().splitlines() if result.stderr.strip() else [])
        if result.returncode != expected:
            returncode = result.returncode
            break
    return CommandResult(
        name="freeze_enforcement_smoke",
        command=["freeze_enforcement_smoke"],
        returncode=returncode,
        passed=returncode == 0,
        stdout_tail=stdout[-8:],
        stderr_tail=stderr[-8:],
    )


def create_coin_action_contract_fixture(temp_root: Path, name: str, valid: bool) -> Path:
    run_dir = temp_root / name
    run_dir.mkdir(parents=True)
    if valid:
        parts = ["head", "torso", "left_arm", "right_arm", "left_leg", "right_leg", "tail", "coin_prop"]
        route = "prop_action_component_route"
        route_action = "coin_flip_deal_nod_v3"
        lively_status = "pass"
    else:
        parts = ["full_character", "coin_prop"]
        route = "local_part_transform_or_masked_edit"
        route_action = "small_expression"
        lively_status = "fail"
    write_json(run_dir / "source_route_selection_report.json", {
        "schema_version": "sofunny-route-selection-report.v1",
        "status": "pass" if valid else "fail",
        "action": route_action,
        "run_type": "production",
        "recommended_route": route,
        "blockers": [] if valid else ["fixture mismatch"],
        "warnings": [],
    })
    write_json(run_dir / "candidate_manifest.json", {
        "character_name": "audit_char",
        "action": "coin_flip_deal_nod_v3",
        "route": route,
        "admission_eligible": valid,
    })
    write_json(run_dir / "sofunny-run-manifest.json", {
        "schema_version": "sofunny-character-gif.v1",
        "character_name": "audit_char",
        "action_name": "coin_flip_deal_nod_v3",
        "generation": {"route": route, "admission_eligible": valid},
    })
    write_json(run_dir / "part_map.json", {
        "schema_version": "sofunny-part-map.v1",
        "segmentation_source": "manual_clean_layer" if valid else "flat_png_box_split",
        "anchors": {"right_hand": [220, 220], "tail_base": [205, 235]} if valid else {},
        "parts": [{"name": part, "file": f"parts/{part}.png", "render": True} for part in parts],
        "render_order": parts,
    })
    phase_names = [
        "ready",
        "anticipation",
        "toss_release",
        "coin_rise",
        "coin_peak",
        "deal_nod_down",
        "catch_receive",
        "present",
        "settle",
        "loop_return",
    ]
    phases = []
    for index, phase_name in enumerate(phase_names):
        transforms = {
            part: {
                "translate": [0, 0],
                "rotate": 0,
                "scale": [1, 1],
            }
            for part in parts
        }
        phases.append({
            "name": phase_name,
            "frame": index,
            "body_y": 0 if valid else None,
            "head_y": index % 3 if valid else None,
            "head_rotation": 1 if valid else None,
            "arm_rotation": 8 if valid else None,
            "leg_phase": "support" if valid else None,
            "tail_rotation": -4 if valid else None,
            "tail_lag": -0.9 if valid else None,
            "squash_stretch": [1.0, 1.0] if valid else None,
            "optional_expression_variant": None,
            "transforms": transforms,
            "required_visual_change": "coin toss release catch present with head follow and tail settle",
        })
    if not valid:
        for phase in phases:
            for key in ["body_y", "head_y", "head_rotation", "arm_rotation", "leg_phase", "tail_rotation", "tail_lag", "squash_stretch"]:
                phase.pop(key, None)
    write_json(run_dir / "action_component_plan.json", {
        "schema_version": "sofunny-action-component-plan.v1",
        "action_name": "coin_flip_deal_nod_v3",
        "frames": len(phases),
        "phases": phases,
        "loop": {"first_last_match": True, "max_loop_delta_px": 2},
    })
    write_json(run_dir / "part_consistency_report.json", {"status": "pass" if valid else "fail", "warnings": []})
    write_json(run_dir / "component_integrity_report.json", {"status": "pass" if valid else "fail", "warnings": []})
    write_json(run_dir / "lively_motion_report.json", {"status": lively_status, "warnings": []})
    write_json(run_dir / "prop_action_contact_report.json", {"status": "pass" if valid else "fail", "warnings": []})
    return run_dir


def run_coin_action_contract_smoke(temp_root: Path) -> CommandResult:
    scenarios = [
        ("coin_full_character_only_fail", False, 1),
        ("coin_component_prop_pass", True, 0),
    ]
    stdout: list[str] = []
    stderr: list[str] = []
    returncode = 0
    for name, valid, expected in scenarios:
        run_dir = create_coin_action_contract_fixture(temp_root, name, valid)
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "validate_action_contract.py"),
                "--run-dir",
                str(run_dir),
                "--action",
                "coin_flip_deal_nod_v3",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        stdout.extend(result.stdout.strip().splitlines() if result.stdout.strip() else [])
        stderr.extend(result.stderr.strip().splitlines() if result.stderr.strip() else [])
        if result.returncode != expected:
            returncode = result.returncode
            break
    return CommandResult(
        name="coin_flip_deal_nod_action_contract_smoke",
        command=["coin_flip_deal_nod_action_contract_smoke"],
        returncode=returncode,
        passed=returncode == 0,
        stdout_tail=stdout[-8:],
        stderr_tail=stderr[-8:],
    )


def phase_values(index: int, total: int, scenario: str) -> dict[str, Any]:
    if scenario == "near_duplicate_end_frames_fail" and index >= total - 3:
        index = total - 1
    if index == total - 1:
        values = {
            "body_y": 0.0,
            "head_y": -1.0,
            "head_rotation": -1.0,
            "arm_rotation": -8.0,
            "leg_y": -3.0,
            "leg_x": -2.0,
            "tail_rotation": -5.0,
            "tail_lag": -0.9,
            "squash_stretch": [1.0, 1.0],
        }
        if scenario == "tail_locked_fail":
            values["tail_rotation"] = 0.0
        return values
    cycle = (index / max(1, total - 1)) * math.tau
    body_y = round(2.0 * math.sin(cycle), 3)
    head_y = round(2.8 * math.sin(cycle - 0.55), 3)
    head_rotation = round(2.2 * math.sin(cycle - 0.55), 3)
    arm_rotation = round(8.0 * math.sin(cycle + 0.35), 3)
    leg_y = round(3.2 * math.sin(cycle), 3)
    leg_x = round(2.6 * math.cos(cycle), 3)
    tail_rotation = round(7.0 * math.sin(cycle - 0.9), 3)
    if scenario == "whole_body_bob_only_fail":
        head_y = body_y
        head_rotation = 0.0
        arm_rotation = 0.0
        leg_y = body_y
        leg_x = 0.0
        tail_rotation = 0.0
    if scenario == "tail_locked_fail":
        tail_rotation = 0.0
    return {
        "body_y": body_y,
        "head_y": head_y,
        "head_rotation": head_rotation,
        "arm_rotation": arm_rotation,
        "leg_y": leg_y,
        "leg_x": leg_x,
        "tail_rotation": tail_rotation,
        "tail_lag": -0.9,
        "squash_stretch": [round(1.0 - body_y * 0.005, 4), round(1.0 + body_y * 0.007, 4)],
    }


def draw_lively_frame(values: dict[str, Any], path: Path) -> None:
    image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    body_y = float(values["body_y"])
    head_y = float(values["head_y"])
    arm_rotation = float(values["arm_rotation"])
    leg_y = float(values["leg_y"])
    leg_x = float(values["leg_x"])
    tail_rotation = float(values["tail_rotation"])
    draw.ellipse((82, 63 + body_y + tail_rotation * 0.12, 113, 92 + body_y - tail_rotation * 0.12), fill=(95, 70, 45, 255), outline=(30, 30, 30, 255), width=2)
    draw.rounded_rectangle((50, 58 + body_y, 78, 96 + body_y), radius=6, fill=(65, 70, 82, 255), outline=(30, 30, 30, 255), width=2)
    draw.ellipse((42, 28 + head_y, 84, 62 + head_y), fill=(236, 180, 105, 255), outline=(30, 30, 30, 255), width=2)
    draw.line((54, 70 + body_y, 39 - arm_rotation * 0.35, 83 + body_y + arm_rotation * 0.2), fill=(35, 35, 35, 255), width=5)
    draw.line((74, 70 + body_y, 90 + arm_rotation * 0.35, 83 + body_y - arm_rotation * 0.2), fill=(35, 35, 35, 255), width=5)
    draw.line((57, 94 + body_y, 52 - leg_x, 112 + body_y + leg_y), fill=(35, 35, 35, 255), width=5)
    draw.line((71, 94 + body_y, 77 + leg_x, 112 + body_y - leg_y), fill=(35, 35, 35, 255), width=5)
    draw.ellipse((53, 42 + head_y, 59, 48 + head_y), fill=(20, 20, 20, 255))
    draw.ellipse((68, 42 + head_y, 74, 48 + head_y), fill=(20, 20, 20, 255))
    image.save(path)


def create_lively_motion_fixture(temp_root: Path, name: str, scenario: str) -> Path:
    run_dir = temp_root / name
    frame_dir = run_dir / "component_keyposes"
    frame_dir.mkdir(parents=True)
    write_json(run_dir / "part_consistency_report.json", {"status": "pass", "warnings": []})
    write_json(run_dir / "movable_parts_contract.json", {
        "schema_version": "sofunny-movable-parts.v1",
        "movable_parts": [
            {"part": "torso", "max_translation_px": 8, "max_rotation_deg": 3, "must_remain_attached": True},
            {"part": "head", "max_translation_px": 8, "max_rotation_deg": 5, "must_remain_attached": True},
            {"part": "left_arm", "max_translation_px": 8, "max_rotation_deg": 18, "must_remain_attached": True},
            {"part": "right_arm", "max_translation_px": 8, "max_rotation_deg": 18, "must_remain_attached": True},
            {"part": "left_leg", "max_translation_px": 8, "max_rotation_deg": 10, "must_remain_attached": True},
            {"part": "right_leg", "max_translation_px": 8, "max_rotation_deg": 10, "must_remain_attached": True},
            {"part": "tail", "max_translation_px": 8, "max_rotation_deg": 14, "must_remain_attached": True}
        ]
    })
    phases = []
    manifest_frames = []
    frame_total = 8
    for index in range(frame_total):
        values = phase_values(index, frame_total, scenario)
        frame_path = frame_dir / f"{index:03d}.png"
        draw_lively_frame(values, frame_path)
        transforms = {
            "torso": {"translate": [0, values["body_y"]], "rotate": 0, "scale": values["squash_stretch"]},
            "head": {"translate": [0, values["head_y"]], "rotate": values["head_rotation"], "scale": [1, 1]},
            "left_arm": {"translate": [0, values["body_y"]], "rotate": values["arm_rotation"], "scale": [1, 1]},
            "right_arm": {"translate": [0, values["body_y"]], "rotate": -values["arm_rotation"], "scale": [1, 1]},
            "left_leg": {"translate": [values["leg_x"], values["leg_y"]], "rotate": 0, "scale": [1, 1]},
            "right_leg": {"translate": [-values["leg_x"], -values["leg_y"]], "rotate": 0, "scale": [1, 1]},
            "tail": {"translate": [0, values["body_y"]], "rotate": values["tail_rotation"], "scale": [1, 1]},
        }
        phases.append({
            "name": f"phase_{index:02d}",
            "frame": index,
            "body_y": values["body_y"],
            "head_y": values["head_y"],
            "head_rotation": values["head_rotation"],
            "arm_rotation": values["arm_rotation"],
            "leg_phase": "contact" if values["leg_y"] < -1 else "lift" if values["leg_y"] > 1 else "passing",
            "tail_rotation": values["tail_rotation"],
            "tail_lag": values["tail_lag"],
            "squash_stretch": values["squash_stretch"],
            "optional_expression_variant": None,
            "transforms": transforms,
            "required_visual_change": "fixture phase motion",
        })
        manifest_frames.append({
            "frame": index,
            "phase": f"phase_{index:02d}",
            "required_visual_change": "fixture phase motion",
            "file": f"component_keyposes/{index:03d}.png",
            "parts": transforms,
        })
    write_json(run_dir / "action_component_plan.json", {
        "schema_version": "sofunny-action-component-plan.v1",
        "action_name": "small_jog_front",
        "frames": frame_total,
        "phases": phases,
        "loop": {"first_last_match": True, "max_loop_delta_px": 2},
    })
    write_json(run_dir / "component_keypose_manifest.json", {
        "schema_version": "sofunny-component-keyposes.v1",
        "route": "source_animation_pseudo_rig_mvp",
        "full_frame_redraw": False,
        "output_dir": "component_keyposes",
        "frame_count": frame_total,
        "frames": manifest_frames,
    })
    return run_dir


def create_secondary_motion_source_fixture(temp_root: Path, name: str) -> Path:
    run_dir = temp_root / name
    parts_dir = run_dir / "parts"
    parts_dir.mkdir(parents=True)
    part_shapes = {
        "torso": ("rectangle", (50, 58, 78, 96), (65, 70, 82, 255)),
        "head": ("ellipse", (42, 28, 84, 62), (236, 180, 105, 255)),
        "left_arm": ("line", (54, 70, 40, 86), (35, 35, 35, 255)),
        "right_arm": ("line", (74, 70, 90, 86), (35, 35, 35, 255)),
        "left_leg": ("line", (57, 94, 52, 112), (35, 35, 35, 255)),
        "right_leg": ("line", (71, 94, 77, 112), (35, 35, 35, 255)),
        "tail": ("ellipse", (82, 63, 113, 92), (95, 70, 45, 255)),
    }
    part_entries = []
    for part, (kind, coords, color) in part_shapes.items():
        image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        if kind == "line":
            draw.line(coords, fill=color, width=5)
        elif kind == "rectangle":
            draw.rounded_rectangle(coords, radius=6, fill=color, outline=(30, 30, 30, 255), width=2)
        else:
            draw.ellipse(coords, fill=color, outline=(30, 30, 30, 255), width=2)
        rel = f"parts/{part}.png"
        image.save(run_dir / rel)
        part_entries.append({"name": part, "file": rel, "render": True})
    write_json(run_dir / "part_map.json", {
        "schema_version": "sofunny-part-map.v1",
        "segmentation_provenance": "production_clean_components",
        "canvas": {"width": 128, "height": 128},
        "parts": part_entries,
        "render_order": ["tail", "left_leg", "right_leg", "torso", "left_arm", "right_arm", "head"],
    })
    write_json(run_dir / "component_integrity_report.json", {"schema_version": "sofunny-component-integrity.v1", "status": "pass", "findings": []})
    write_json(run_dir / "identity_parts_contract.json", {"schema_version": "sofunny-identity-parts.v1", "fixed_identity_parts": []})
    write_json(run_dir / "movable_parts_contract.json", {
        "schema_version": "sofunny-movable-parts.v1",
        "movable_parts": [
            {"part": part, "max_translation_px": 8, "max_rotation_deg": 18 if "arm" in part else 14, "must_remain_attached": True}
            for part in part_shapes
        ],
    })
    phases = []
    for index in range(8):
        cycle = (index / 7) * math.tau
        leg_y = round(math.sin(cycle) * 3.0, 3)
        leg_x = round(math.cos(cycle) * 2.0, 3)
        phases.append({
            "name": f"phase_{index:02d}",
            "frame": index,
            "acting_intent": "small jog phase with readable lower-body contact",
            "primary_driver": "legs",
            "motion_reason": "primary lower-body step carries the action; secondary parts follow with lag",
            "spacing_curve": "ease_in_out_sine",
            "overlap_group": "head/tail/arms lag torso",
            "transforms": {
                "left_leg": {"translate": [leg_x, leg_y], "rotate": 0, "scale": [1, 1]},
                "right_leg": {"translate": [-leg_x, -leg_y], "rotate": 0, "scale": [1, 1]},
            },
            "required_visual_change": "primary leg contact changes before secondary motion",
        })
    write_json(run_dir / "action_component_plan.json", {
        "schema_version": "sofunny-action-component-plan.v1",
        "action_name": "small_jog_front",
        "frames": 8,
        "canvas": {"width": 128, "height": 128},
        "background": "#00ff00",
        "phases": phases,
        "loop": {"first_last_match": True, "max_loop_delta_px": 20},
    })
    return run_dir


def run_lively_motion_case(case: dict[str, Any], temp_root: Path) -> CaseResult:
    fixture = case.get("fixture", {})
    expected = case.get("expect", {})
    scenario = fixture.get("scenario", case["name"].replace("lively_motion_", ""))
    run_dir = temp_root / case["name"]
    evidence: list[str] = []
    if scenario == "secondary_motion_pass":
        run_dir = create_secondary_motion_source_fixture(temp_root, case["name"])
        commands = [
            [sys.executable, str(ROOT / "scripts" / "add_secondary_motion_pass.py"), "--run-dir", str(run_dir)],
            [sys.executable, str(ROOT / "scripts" / "generate_component_keyposes.py"), "--run-dir", str(run_dir)],
            [sys.executable, str(ROOT / "scripts" / "audit_part_consistency.py"), "--run-dir", str(run_dir)],
            [sys.executable, str(ROOT / "scripts" / "audit_lively_motion.py"), "--run-dir", str(run_dir), "--frame-dir", str(run_dir / "component_keyposes"), "--max-loop-diff", "0.2"],
        ]
        returncode = 0
        for command in commands:
            result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
            evidence.append(f"{Path(command[1]).name}_returncode={result.returncode}")
            if result.stdout.strip():
                evidence.append(f"{Path(command[1]).name}_stdout_last={result.stdout.strip().splitlines()[-1]}")
            if result.stderr.strip():
                evidence.append(f"{Path(command[1]).name}_stderr_last={result.stderr.strip().splitlines()[-1]}")
            if result.returncode != 0:
                returncode = result.returncode
                break
    else:
        run_dir = create_lively_motion_fixture(temp_root, case["name"], scenario)
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "audit_lively_motion.py"), "--run-dir", str(run_dir)],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        returncode = result.returncode
        evidence.append(f"audit_lively_motion_returncode={result.returncode}")
        if result.stdout.strip():
            evidence.append("audit_lively_motion_stdout_last=" + result.stdout.strip().splitlines()[-1])
        if result.stderr.strip():
            evidence.append("audit_lively_motion_stderr_last=" + result.stderr.strip().splitlines()[-1])
    report = json.loads((run_dir / "lively_motion_report.json").read_text(encoding="utf-8")) if (run_dir / "lively_motion_report.json").exists() else {}
    actual = {
        "audit_lively_motion_returncode": returncode,
        "lively_motion_status": report.get("status", "missing"),
    }
    passed = (
        returncode == expected.get("audit_lively_motion_returncode")
        and actual["lively_motion_status"] == expected.get("lively_motion_status")
    )
    return CaseResult(
        name=case["name"],
        description=case.get("description", ""),
        passed=passed,
        run_dir=str(run_dir),
        expected=expected,
        actual=actual,
        evidence=evidence,
    )


def load_case(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "sofunny-regression-case.v1":
        raise ValueError(f"{path} has unsupported schema_version")
    return data


def run_optional_validator(name: str, command: list[str], expected: int | str) -> tuple[str, int | str, bool, list[str]]:
    if expected == "skip":
        return "skip", "skip", True, [f"{name}=skipped"]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    evidence = [f"{name}_returncode={result.returncode}"]
    if result.stdout.strip():
        evidence.append(f"{name}_stdout_last={result.stdout.strip().splitlines()[-1]}")
    if result.stderr.strip():
        evidence.append(f"{name}_stderr_last={result.stderr.strip().splitlines()[-1]}")
    return "run", result.returncode, result.returncode == expected, evidence


def run_case(case_path: Path, temp_root: Path) -> CaseResult:
    case = load_case(case_path)
    if case.get("fixture", {}).get("type") == "lively_motion":
        return run_lively_motion_case(case, temp_root)
    fixture = case.get("fixture", {})
    expected = case.get("expect", {})
    run_dir = temp_root / case["name"]
    write_base_fixture(
        run_dir,
        identity_status=fixture.get("identity_status", "pass"),
        smoke=bool(fixture.get("smoke", False)),
        omit_visual_review=bool(fixture.get("omit_visual_review", False)),
        omit_route_selection=bool(fixture.get("omit_route_selection", False)),
        retry_pivot_required=bool(fixture.get("retry_pivot_required", False)),
        omit_part_map=bool(fixture.get("omit_part_map", False)),
        part_consistency_status=fixture.get("part_consistency_status", "pass"),
        omit_lively_motion=bool(fixture.get("omit_lively_motion", False)),
        component_integrity_status=fixture.get("component_integrity_status", "pass"),
        adapter=fixture.get("adapter", ""),
        omit_adapter_audit=bool(fixture.get("omit_adapter_audit", False)),
    )

    finalize = run_finalize(run_dir)
    approved = manifest_production_approved(run_dir)
    evidence = [
        f"finalize_returncode={finalize.returncode}",
        f"production_approved={approved}",
    ]
    if finalize.stdout.strip():
        evidence.append("finalize_stdout_last=" + finalize.stdout.strip().splitlines()[-1])
    if finalize.stderr.strip():
        evidence.append("finalize_stderr_last=" + finalize.stderr.strip().splitlines()[-1])

    admission_mode, admission_rc, admission_ok, admission_evidence = run_optional_validator(
        "validate_admission",
        [sys.executable, str(ROOT / "scripts" / "validate_sofunny_run.py"), "--run-dir", str(run_dir), "--stage", "admission"],
        expected.get("validate_admission_returncode", "skip"),
    )
    manifest_mode, manifest_rc, manifest_ok, manifest_evidence = run_optional_validator(
        "validate_manifest",
        [sys.executable, str(ROOT / "scripts" / "validate_sofunny_manifest.py"), "--run-dir", str(run_dir)],
        expected.get("validate_manifest_returncode", "skip"),
    )
    evidence.extend(admission_evidence)
    evidence.extend(manifest_evidence)

    actual = {
        "finalize_returncode": finalize.returncode,
        "production_approved": approved,
        "validate_admission_mode": admission_mode,
        "validate_admission_returncode": admission_rc,
        "validate_manifest_mode": manifest_mode,
        "validate_manifest_returncode": manifest_rc,
    }
    passed = (
        finalize.returncode == expected.get("finalize_returncode")
        and approved is expected.get("production_approved")
        and admission_ok
        and manifest_ok
    )
    return CaseResult(
        name=case["name"],
        description=case.get("description", ""),
        passed=passed,
        run_dir=str(run_dir),
        expected=expected,
        actual=actual,
        evidence=evidence,
    )


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# SoFunny Regression Report",
        "",
        f"Generated: {payload['generated_at']}",
        f"Status: `{payload['status']}`",
        "",
        "## Command Checks",
        "",
    ]
    for check in payload["checks"]:
        verdict = "PASS" if check["passed"] else "FAIL"
        lines.append(f"- {verdict}: `{check['name']}` returncode={check['returncode']}")
    lines.extend(["", "## Cases", ""])
    for case in payload["cases"]:
        verdict = "PASS" if case["passed"] else "FAIL"
        lines.extend([
            f"### {verdict}: {case['name']}",
            "",
            case.get("description", ""),
            "",
            "Evidence:",
            "",
        ])
        for item in case["evidence"]:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(ROOT))
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args()

    temp_dir = tempfile.TemporaryDirectory(prefix="sofunny_regression_suite_")
    temp_root = Path(temp_dir.name)

    checks = [
        run_command("quick_validate_skill", [sys.executable, str(ROOT / "scripts" / "quick_validate_skill.py")]),
        run_command("validate_profile_sofunny", [sys.executable, str(ROOT / "scripts" / "validate_profile.py"), "--profile", "sofunny"]),
        run_command("validate_profile_default", [sys.executable, str(ROOT / "scripts" / "validate_profile.py"), "--profile", "default-character-gif"]),
        run_command("audit_admission_enforcement", [sys.executable, str(ROOT / "scripts" / "audit_admission_enforcement.py"), "--output-dir", str(args.output_dir)]),
        run_command("route_select_small_jog", [sys.executable, str(ROOT / "scripts" / "select_source_animation_route.py"), "--action", "small_jog_front", "--run-type", "production"]),
        run_command("route_select_blocks_production_full_frame_redraw", [sys.executable, str(ROOT / "scripts" / "select_source_animation_route.py"), "--action", "small_jog_front", "--run-type", "production", "--proposed-route", "full_frame_redraw"], expected_returncode=1),
        run_command("route_select_sherry_tail_wave_greeting", [sys.executable, str(ROOT / "scripts" / "select_source_animation_route.py"), "--action", "sherry_tail_wave_greeting", "--run-type", "production_candidate"]),
        run_command("route_select_catch_falling_petal", [sys.executable, str(ROOT / "scripts" / "select_source_animation_route.py"), "--action", "catch_falling_petal", "--run-type", "production_candidate"]),
        run_command("route_select_catch_falling_petal_blocks_candidate_pseudo_rig", [sys.executable, str(ROOT / "scripts" / "select_source_animation_route.py"), "--action", "catch_falling_petal", "--run-type", "production_candidate", "--proposed-route", "component_pseudo_rig_action_component_plan"], expected_returncode=1),
        run_command("route_select_catch_falling_petal_blocks_pseudo_rig", [sys.executable, str(ROOT / "scripts" / "select_source_animation_route.py"), "--action", "catch_falling_petal", "--run-type", "production", "--proposed-route", "source_animation_component_plan_with_local_hand_redraw"], expected_returncode=1),
        run_command("route_select_coin_flip_prop_action", [sys.executable, str(ROOT / "scripts" / "select_source_animation_route.py"), "--action", "coin_flip_deal_nod_v3", "--run-type", "production"]),
        run_command("route_select_coin_flip_blocks_local_transform", [sys.executable, str(ROOT / "scripts" / "select_source_animation_route.py"), "--action", "coin_flip_deal_nod_v3", "--run-type", "production", "--proposed-route", "local_part_transform_or_masked_edit"], expected_returncode=1),
        run_command("adapter_select_tooncrafter_requires_approved_keyposes", [sys.executable, str(ROOT / "scripts" / "select_route_adapter.py"), "--route", "interpolation_route", "--adapter", "tooncrafter", "--reimport-through-gates"], expected_returncode=1),
        run_command("adapter_select_tooncrafter_with_approved_keyposes", [sys.executable, str(ROOT / "scripts" / "select_route_adapter.py"), "--route", "interpolation_route", "--adapter", "tooncrafter", "--approved-keyposes", "--reimport-through-gates"]),
        run_command("adapter_select_animate_requires_deid_reimport", [sys.executable, str(ROOT / "scripts" / "select_route_adapter.py"), "--route", "external_animation_provider_candidate", "--adapter", "animate_x_wan"], expected_returncode=1),
        run_command("adapter_select_ipadapter_external_upload_blocked", [sys.executable, str(ROOT / "scripts" / "select_route_adapter.py"), "--route", "local_part_transform_or_masked_edit", "--adapter", "ipadapter_comfyui", "--reimport-through-gates", "--hosted-external"], expected_returncode=1),
        run_command("adapter_select_spine_blocks_first_round_mvp", [sys.executable, str(ROOT / "scripts" / "select_route_adapter.py"), "--route", "lora_ipadapter_or_component_rig_candidate", "--adapter", "spine_live2d_dragonbones", "--reimport-through-gates"], expected_returncode=1),
        run_command("retry_tax_single_attempt_allows_continue", [sys.executable, str(ROOT / "scripts" / "retry_tax_report.py"), "--attempt", "full_frame_redraw:identity_drift"]),
        run_command("retry_tax_repeated_identity_drift_requires_pivot", [sys.executable, str(ROOT / "scripts" / "retry_tax_report.py"), "--attempt", "full_frame_redraw:identity_drift", "--attempt", "full_frame_redraw:identity_drift"], expected_returncode=1),
        run_command("retry_tax_same_route_two_failures_requires_pivot", [sys.executable, str(ROOT / "scripts" / "retry_tax_report.py"), "--attempt", "full_frame_redraw:identity_drift", "--attempt", "full_frame_redraw:tail_artifact"], expected_returncode=1),
        run_command("retry_tax_same_failure_two_routes_requires_pivot", [sys.executable, str(ROOT / "scripts" / "retry_tax_report.py"), "--attempt", "full_frame_redraw:identity_drift", "--attempt", "provider_candidate:identity_drift"], expected_returncode=1),
        run_command("animatex_blocks_small_action", [sys.executable, str(ROOT / "scripts" / "create_animatex_packet.py"), "--run-dir", str(temp_root / "animatex_small_action"), "--canonical-reference", str(temp_root / "missing.png"), "--motion-video", str(temp_root / "missing.mp4"), "--action", "small_jog_front", "--deidentified-motion"], expected_returncode=1),
        run_tooncrafter_smoke(temp_root),
        run_ipadapter_smoke(temp_root),
        run_animatex_smoke(temp_root),
        run_hard_split_component_plan_block_smoke(temp_root),
        run_catch_falling_petal_hard_split_blocks_smoke(temp_root),
        run_component_generation_gate_smoke(temp_root),
        run_freeze_enforcement_smoke(temp_root),
        run_coin_action_contract_smoke(temp_root),
    ]

    cases = [run_case(path, temp_root) for path in sorted(CASES_DIR.glob("*/case.json"))]
    status = "pass" if all(check.passed for check in checks) and all(case.passed for case in cases) else "fail"
    payload: dict[str, Any] = {
        "schema_version": "sofunny-regression-report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "skill_root": str(ROOT),
        "cases_dir": str(CASES_DIR),
        "temp_root": str(temp_root) if args.keep_temp else None,
        "checks": [asdict(check) for check in checks],
        "cases": [asdict(case) for case in cases],
    }

    output_dir = Path(args.output_dir).expanduser().resolve()
    json_path = output_dir / "regression_report.json"
    md_path = output_dir / "regression_report.md"
    write_json(json_path, payload)
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps({
        "status": status,
        "checks": sum(1 for check in checks if check.passed),
        "cases": sum(1 for case in cases if case.passed),
        "case_total": len(cases),
        "json": str(json_path),
        "md": str(md_path),
    }, ensure_ascii=False, indent=2))
    if args.keep_temp:
        return 0 if status == "pass" else 1
    temp_dir.cleanup()
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
