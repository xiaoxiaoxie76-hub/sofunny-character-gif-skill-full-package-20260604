#!/usr/bin/env python3
"""Create a packet for local repair of failed source-animation parts."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-dir", default="local_part_repair_packet")
    parser.add_argument("--report", default="part_consistency_report.json")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    output_dir = run_dir / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / args.report
    report = read_json(report_path) if report_path.exists() else {"status": "missing", "findings": ["missing part consistency report"]}
    part_map = read_json(run_dir / "part_map.json") if (run_dir / "part_map.json").exists() else {"parts": []}

    for source_name in [
        "part_map.json",
        "identity_parts_contract.json",
        "movable_parts_contract.json",
        "action_component_plan.json",
        "part_consistency_report.json",
        "component_keypose_contact_sheet.png",
    ]:
        source = run_dir / source_name
        if source.exists():
            shutil.copy2(source, output_dir / source_name)

    parts_out = output_dir / "parts"
    parts_out.mkdir(exist_ok=True)
    for entry in part_map.get("parts", []):
        source = run_dir / entry.get("file", "")
        if source.exists():
            shutil.copy2(source, parts_out / source.name)

    payload = {
        "schema_version": "sofunny-local-part-repair-packet.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_run": str(run_dir),
        "status": "repair_required",
        "source_report_status": report.get("status"),
        "findings": report.get("findings", []),
        "instructions": [
            "Repair only the failed local part or phase.",
            "Do not full-frame redraw the character.",
            "Preserve fixed identity parts unless the identity contract is updated first.",
            "After repair, rerun validate_part_map.py, generate_component_keyposes.py, and audit_part_consistency.py.",
        ],
    }
    write_json(output_dir / "repair_packet_manifest.json", payload)
    (output_dir / "README.md").write_text(
        "# Local Part Repair Packet\n\n"
        "Repair the failed source-animation parts only. Do not redraw the full character frame.\n\n"
        "After editing, copy repaired parts back to the run and rerun the source-animation checks.\n",
        encoding="utf-8",
    )
    print(str(output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

