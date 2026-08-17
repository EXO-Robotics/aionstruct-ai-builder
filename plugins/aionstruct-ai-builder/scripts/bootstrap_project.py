#!/usr/bin/env python3
"""Copy the self-contained AIONSTRUCT starter project to a new directory."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
TEMPLATE = PLUGIN / "assets" / "starter-project"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a standalone AIONSTRUCT project")
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    destination = args.destination.resolve()
    if destination.exists():
        if not destination.is_dir() or any(destination.iterdir()):
            parser.error(f"destination must not exist or must be empty: {destination}")
    else:
        destination.mkdir(parents=True)
    shutil.copytree(TEMPLATE, destination, dirs_exist_ok=True)
    print(f"created AIONSTRUCT project: {destination}")
    print("next: python3 tools/aionstruct.py doctor")
    print("sample: python3 tools/aionstruct.py build aionstruct/examples/wayfarers_hearth_house.aionstruct.json --contract aionstruct/examples/wayfarers_hearth_house.quality.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
