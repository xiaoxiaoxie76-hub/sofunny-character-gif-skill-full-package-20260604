#!/usr/bin/env python3
"""Execute or diagnose a SoFunny provider packet."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from sofunny_anim.profiles import load_profile


SCRIPT_DIR = Path(__file__).resolve().parent


def read_json(path: Path, default: dict | None = None) -> dict:
    if not path.exists():
        return default or {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_env_file(path: Path | None) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path or not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def http_check(url: str, timeout: float) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return {
                "status": "ok",
                "url": url,
                "http_status": response.status,
                "content_type": response.headers.get("content-type", ""),
            }
    except Exception as exc:  # noqa: BLE001 - report diagnostic type to user
        return {
            "status": "fail",
            "url": url,
            "error_type": type(exc).__name__,
            "error": str(exc)[:240],
        }


def tcp_check(host: str, port: int, timeout: float) -> dict:
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        return {"status": "ok", "host": host, "port": port}
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "fail",
            "host": host,
            "port": port,
            "error_type": type(exc).__name__,
            "error": str(exc)[:160],
        }
    finally:
        sock.close()


def command_exists(command: str) -> bool:
    return subprocess.run(["/usr/bin/which", command], text=True, capture_output=True).returncode == 0


def write_blocked_markdown(run_dir: Path, payload: dict) -> None:
    manifest = payload.get("packet_manifest", {})
    expected = manifest.get("expected_output") or str(run_dir / "provider_packet" / "generated_sheet.png")
    lines = [
        "# Provider Execution Blocked",
        "",
        "The provider packet is ready, but no usable image provider is reachable in this environment.",
        "",
        "## Expected Output",
        "",
        "```text",
        expected,
        "```",
        "",
        "## Required Next Step",
        "",
        "Bring one provider online, then rerun:",
        "",
        "```bash",
        f"python3 {SCRIPT_DIR / 'execute_provider_packet.py'} --run-dir \"{run_dir}\"",
        "```",
        "",
        "Valid provider options:",
        "",
        "- ComfyUI at `http://127.0.0.1:8188`",
        "- SD WebUI at `http://127.0.0.1:7860`",
        "- external multi-image provider that writes the sheet to the expected output path",
        "",
        "After `generated_sheet.png` exists, this script will run SoFunny gates automatically.",
    ]
    (run_dir / "provider_execution_blocked.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_gates(run_dir: Path, generated_sheet: Path | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCRIPT_DIR / "run_provider_result_gates.py"), "--run-dir", str(run_dir)]
    if generated_sheet:
        cmd.extend(["--generated-sheet", str(generated_sheet)])
    return subprocess.run(cmd, text=True, capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--env-file", default="/Users/xiexiaoxiao/Desktop/SoFunnyWork/SoFunnyWorkFlow/.env")
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()
    profile = load_profile(args.profile)

    run_dir = Path(args.run_dir).expanduser().resolve()
    packet_dir = run_dir / "provider_packet"
    manifest = read_json(packet_dir / "provider_packet_manifest.json")
    expected_sheet = Path(manifest.get("expected_output") or packet_dir / "generated_sheet.png")
    env_values = load_env_file(Path(args.env_file).expanduser() if args.env_file else None)
    openai_key = os.getenv("OPENAI_API_KEY") or env_values.get("OPENAI_API_KEY", "")
    comfy_base = (os.getenv("COMFYUI_BASE_URL") or env_values.get("COMFYUI_BASE_URL") or "http://127.0.0.1:8188").rstrip("/")
    remote_host = os.getenv("COMFYUI_SERVER_HOST") or env_values.get("COMFYUI_SERVER_HOST", "")
    remote_ports = [22, 8188, 8190, 7860]
    codex_image_gen_tool = Path("/Users/xiexiaoxiao/.codex-image-gen/codex-image-gen.mjs")

    if expected_sheet.exists():
        gate = run_gates(run_dir, expected_sheet)
        status = "generated_sheet_found_gates_ran"
        payload = {
            "schema_version": "sofunny-provider-execution.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "generated_sheet": str(expected_sheet),
            "gate_returncode": gate.returncode,
            "gate_stdout": gate.stdout,
            "gate_stderr": gate.stderr,
            "packet_manifest": manifest,
        }
        write_json(run_dir / "provider_execution_report.json", payload)
        print(json.dumps({"status": status, "gate_returncode": gate.returncode}, ensure_ascii=False, indent=2))
        return 0 if gate.returncode == 0 else 1

    checks = {
        "openai_api_key_present": bool(openai_key),
        "codex_cli_present": command_exists("codex"),
        "codex_image_gen_tool_present": codex_image_gen_tool.exists(),
        "codex_image_gen_instruction_present": bool(manifest.get("codex_image_gen_instruction") and Path(manifest["codex_image_gen_instruction"]).exists()),
        "codex_image_gen_runner": manifest.get("codex_image_gen_runner"),
        "comfyui_system_stats": http_check(f"{comfy_base}/system_stats", args.timeout),
        "comfyui_object_info": http_check(f"{comfy_base}/object_info", args.timeout),
        "sd_webui_options": http_check("http://127.0.0.1:7860/sdapi/v1/options", args.timeout),
        "remote_tcp": [tcp_check(remote_host, port, args.timeout) for port in remote_ports] if remote_host else [],
    }
    comfy_available = (
        checks["comfyui_system_stats"]["status"] == "ok"
        and checks["comfyui_object_info"]["status"] == "ok"
    )
    codex_image_gen_available = bool(
        checks["codex_cli_present"]
        and checks["codex_image_gen_tool_present"]
        and checks["codex_image_gen_instruction_present"]
    )
    if comfy_available:
        status = "provider_reachable_manual_generation_required"
    elif codex_image_gen_available:
        status = "codex_image_gen_available_manual_generation_required"
    else:
        status = "blocked_provider_unavailable"
    next_step = (
        "ComfyUI is reachable. Use the packet prompt/references to generate generated_sheet.png, then rerun this script."
        if comfy_available
        else (
            f"Run the codex-image-gen runner: {manifest.get('codex_image_gen_runner')}"
            if codex_image_gen_available
            else "No reachable image provider. Start/tunnel ComfyUI or use an external multi-image provider to write generated_sheet.png."
        )
    )
    payload = {
        "schema_version": "sofunny-provider-execution.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "run_dir": str(run_dir),
        "packet_dir": str(packet_dir),
        "expected_output": str(expected_sheet),
        "packet_manifest": manifest,
        "checks": checks,
        "next_step": next_step,
    }
    write_json(run_dir / "provider_execution_report.json", payload)
    if status == "blocked_provider_unavailable":
        write_blocked_markdown(run_dir, payload)
    print(json.dumps({"status": status, "expected_output": str(expected_sheet), "next_step": next_step}, ensure_ascii=False, indent=2))
    return 2 if status == "blocked_provider_unavailable" else 0


if __name__ == "__main__":
    raise SystemExit(main())
