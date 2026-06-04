#!/usr/bin/env python3
"""Print a resolved SoFunny character GIF profile or one dotted value."""

from __future__ import annotations

import argparse
import json

from sofunny_anim.profiles import get_path, load_profile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sofunny")
    parser.add_argument("--get", help="Dotted path to print, e.g. thresholds.body_tail.max_bbox_width_range_px")
    args = parser.parse_args()
    profile = load_profile(args.profile)
    value = get_path(profile, args.get) if args.get else profile
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
