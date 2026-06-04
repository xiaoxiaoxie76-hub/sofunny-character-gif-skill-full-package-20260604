#!/usr/bin/env python3
"""Validate a SoFunny character GIF profile."""

from __future__ import annotations

import argparse
import json

from sofunny_anim.profiles import validate_profile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    args = parser.parse_args()
    profile, failures = validate_profile(args.profile)
    payload = {
        "status": "pass" if not failures else "fail",
        "profile_name": profile.get("profile_name"),
        "profile_path": profile.get("_profile_path"),
        "failures": failures,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
