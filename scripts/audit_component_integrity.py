#!/usr/bin/env python3
"""Audit whether source-animation parts are clean enough for production use."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageStat


DEFAULT_ALLOWED_OVERLAPS = {
    ("head", "torso"): 1800,
    ("arm", "torso"): 1800,
    ("leg", "torso"): 1400,
    ("tail", "torso"): 1400,
    ("leg", "leg"): 900,
}


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def part_group(name: str) -> str:
    lowered = name.lower()
    if "coin" in lowered:
        return "coin_prop"
    if "head" in lowered or "face" in lowered or "glasses" in lowered:
        return "head"
    if "torso" in lowered or "body" in lowered or "trunk" in lowered:
        return "torso"
    if "arm" in lowered or "hand" in lowered:
        return "arm"
    if "leg" in lowered or "foot" in lowered:
        return "leg"
    if "tail" in lowered:
        return "tail"
    return "other"


def alpha_area(image: Image.Image, threshold: int = 1) -> int:
    return sum(1 for value in image.convert("RGBA").getchannel("A").getdata() if value >= threshold)


def load_part_images(run_dir: Path, part_map: dict[str, Any]) -> list[tuple[str, str, Image.Image]]:
    images = []
    for entry in part_map.get("parts", []):
        if not entry.get("render", True):
            continue
        name = str(entry.get("name", ""))
        if part_group(name) == "coin_prop":
            continue
        file_value = entry.get("file")
        if not file_value:
            continue
        path = run_dir / file_value
        if path.exists():
            images.append((name, part_group(name), Image.open(path).convert("RGBA")))
    return images


def composite_parts(parts: list[tuple[str, str, Image.Image]], render_order: list[str]) -> Image.Image | None:
    if not parts:
        return None
    by_name = {name: image for name, _, image in parts}
    size = parts[0][2].size
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    order = render_order or [name for name, _, _ in parts]
    for name in order:
        image = by_name.get(name)
        if image is not None:
            out.alpha_composite(image)
    return out


def overlap_metrics(parts: list[tuple[str, str, Image.Image]]) -> dict[str, Any]:
    if not parts:
        return {"union_area": 0, "overlap_area": 0, "overlap_ratio": 0.0, "max_depth": 0, "pair_overlaps": []}
    size = parts[0][2].size
    counts = [0] * (size[0] * size[1])
    masks = []
    for name, group, image in parts:
        alpha = list(image.getchannel("A").getdata())
        masks.append((name, group, alpha))
        for index, value in enumerate(alpha):
            if value > 0:
                counts[index] += 1
    union_area = sum(1 for count in counts if count > 0)
    overlap_area = sum(1 for count in counts if count >= 2)
    max_depth = max(counts) if counts else 0
    pairs = []
    for index, (name_a, group_a, alpha_a) in enumerate(masks):
        for name_b, group_b, alpha_b in masks[index + 1:]:
            overlap = sum(1 for a, b in zip(alpha_a, alpha_b) if a > 0 and b > 0)
            if overlap:
                groups = tuple(sorted((group_a, group_b)))
                pairs.append({
                    "a": name_a,
                    "b": name_b,
                    "group_pair": list(groups),
                    "overlap_px": overlap,
                    "allowed_px": DEFAULT_ALLOWED_OVERLAPS.get(groups, 350),
                })
    pairs.sort(key=lambda item: item["overlap_px"], reverse=True)
    return {
        "union_area": union_area,
        "overlap_area": overlap_area,
        "overlap_ratio": round(overlap_area / max(1, union_area), 4),
        "max_depth": max_depth,
        "pair_overlaps": pairs,
    }


def reconstruction_metrics(run_dir: Path, part_map: dict[str, Any], parts: list[tuple[str, str, Image.Image]]) -> dict[str, Any]:
    canonical_path = run_dir / str(part_map.get("canonical", {}).get("normalized", "source/canonical-normalized.png"))
    if not canonical_path.exists():
        return {"status": "missing_canonical", "canonical": str(canonical_path)}
    canonical = Image.open(canonical_path).convert("RGBA")
    composite = composite_parts(parts, part_map.get("render_order", []))
    if composite is None:
        return {"status": "missing_parts", "canonical": str(canonical_path)}
    diff = ImageChops.difference(canonical, composite)
    alpha_c = list(canonical.getchannel("A").getdata())
    alpha_f = list(composite.getchannel("A").getdata())
    missing = sum(1 for c, f in zip(alpha_c, alpha_f) if c > 64 and f <= 64)
    extra = sum(1 for c, f in zip(alpha_c, alpha_f) if c <= 64 and f > 64)
    alpha_changed = sum(1 for c, f in zip(alpha_c, alpha_f) if abs(c - f) > 32)
    stat = ImageStat.Stat(diff)
    diff_path = run_dir / "component_integrity_diff.png"
    debug = Image.new("RGBA", canonical.size, (255, 255, 255, 255))
    debug.alpha_composite(canonical)
    overlay = Image.new("RGBA", canonical.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = canonical.size
    for index, (c, f) in enumerate(zip(alpha_c, alpha_f)):
        if c > 64 and f <= 64:
            x, y = index % width, index // width
            draw.point((x, y), fill=(255, 0, 0, 180))
        elif c <= 64 and f > 64:
            x, y = index % width, index // width
            draw.point((x, y), fill=(0, 0, 255, 160))
    debug.alpha_composite(overlay)
    debug.save(diff_path)
    return {
        "status": "computed",
        "canonical": str(canonical_path),
        "missing_alpha_px": missing,
        "extra_alpha_px": extra,
        "alpha_changed_px": alpha_changed,
        "diff_bbox": list(diff.getbbox() or (0, 0, 0, 0)),
        "mean_rgba_diff_sum": round(sum(stat.mean), 4),
        "diff_debug": str(diff_path),
    }


def provenance(part_map: dict[str, Any]) -> dict[str, Any]:
    source = part_map.get("segmentation_source") or part_map.get("part_source") or part_map.get("provenance", {}).get("segmentation_source")
    if source:
        source = str(source)
    else:
        source = "unknown"
    return {
        "segmentation_source": source,
        "flat_png_box_split": source in {"flat_png_box_split", "unknown"},
        "has_declared_pivots": bool(part_map.get("pivots") or part_map.get("anchors")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--report", default="component_integrity_report.json")
    parser.add_argument("--max-overlap-ratio", type=float, default=0.18)
    parser.add_argument("--max-overlap-depth", type=int, default=3)
    parser.add_argument("--max-missing-alpha-px", type=int, default=180)
    parser.add_argument("--max-extra-alpha-px", type=int, default=700)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    part_map = read_json(run_dir / "part_map.json", {})
    findings: list[str] = []
    warnings: list[str] = []
    if not part_map:
        findings.append("missing part_map.json")
        parts: list[tuple[str, str, Image.Image]] = []
    else:
        parts = load_part_images(run_dir, part_map)
    groups = defaultdict(int)
    for _, group, _ in parts:
        groups[group] += 1
    required_groups = {"head", "torso", "arm", "leg", "tail"}
    missing_groups = sorted(group for group in required_groups if groups[group] == 0)
    if missing_groups:
        findings.append("missing required visual part groups: " + ", ".join(missing_groups))

    prov = provenance(part_map)
    if prov["flat_png_box_split"]:
        findings.append("component parts lack clean segmentation provenance; flat/unknown PNG box split is diagnostic-only")
    if not prov["has_declared_pivots"]:
        findings.append("part_map must declare anchors/pivots for production component animation")

    overlap = overlap_metrics(parts)
    if overlap["overlap_ratio"] > args.max_overlap_ratio:
        findings.append(f"part overlap ratio {overlap['overlap_ratio']} exceeds {args.max_overlap_ratio}")
    if overlap["max_depth"] > args.max_overlap_depth:
        findings.append(f"part overlap depth {overlap['max_depth']} exceeds {args.max_overlap_depth}")
    bad_pairs = [item for item in overlap["pair_overlaps"] if item["overlap_px"] > item["allowed_px"]]
    if bad_pairs:
        findings.append("undeclared/large part overlaps exceed allowed thresholds")

    reconstruction = reconstruction_metrics(run_dir, part_map, parts)
    if reconstruction.get("status") != "computed":
        warnings.append(f"neutral reconstruction not computed: {reconstruction.get('status')}")
    else:
        if int(reconstruction["missing_alpha_px"]) > args.max_missing_alpha_px:
            findings.append(f"neutral reconstruction missing alpha {reconstruction['missing_alpha_px']}px exceeds {args.max_missing_alpha_px}")
        if int(reconstruction["extra_alpha_px"]) > args.max_extra_alpha_px:
            findings.append(f"neutral reconstruction extra alpha {reconstruction['extra_alpha_px']}px exceeds {args.max_extra_alpha_px}")

    report = {
        "schema_version": "sofunny-component-integrity-report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not findings else "fail",
        "run_dir": str(run_dir),
        "provenance": prov,
        "part_group_counts": dict(groups),
        "overlap": overlap,
        "neutral_reconstruction": reconstruction,
        "findings": findings,
        "warnings": warnings,
        "blocks_keypose_freeze": bool(findings),
    }
    write_json(run_dir / args.report, report)
    if findings:
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("PASS: component integrity audit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

