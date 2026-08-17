#!/usr/bin/env python3
"""Exercise the packaged template without touching Minecraft or Docker."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
TEMPLATE = PLUGIN / "assets" / "starter-project"


def run(project: Path, *args: str) -> None:
    completed = subprocess.run(
        [sys.executable, "tools/aionstruct.py", *args], cwd=project,
        check=False, capture_output=True, text=True,
    )
    if completed.returncode:
        raise RuntimeError(f"command failed: {' '.join(args)}\n{completed.stdout}\n{completed.stderr}")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aionstruct-plugin-test-") as temporary:
        project = Path(temporary) / "project"
        shutil.copytree(TEMPLATE, project)
        blueprint = "aionstruct/examples/wayfarers_hearth_house.aionstruct.json"
        contract = "aionstruct/examples/wayfarers_hearth_house.quality.json"
        run(project, "doctor")
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=project,
            check=False, capture_output=True, text=True,
        )
        if completed.returncode:
            raise RuntimeError(f"starter tests failed\n{completed.stdout}\n{completed.stderr}")
        run(project, "validate", blueprint)
        run(project, "build", blueprint, "--contract", contract)
        structure = project / "dist" / "wayfarers_hearth_house.mcstructure"
        first = digest(structure)
        run(project, "compile", blueprint)
        if digest(structure) != first:
            raise RuntimeError("deterministic compile check failed")
        if not (project / "reports" / "previews" / "wayfarers_hearth_house" / "isometric_engineering_board.png").exists():
            raise RuntimeError("isometric preview missing")
    print("PASS plugin starter validate/build/recompile determinism")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
