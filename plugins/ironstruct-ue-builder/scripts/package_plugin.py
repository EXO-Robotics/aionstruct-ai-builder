#!/usr/bin/env python3
"""Create a deterministic IronStruct plugin archive and hash receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
FIXED_TIME = (2020, 1, 1, 0, 0, 0)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def included_files() -> list[Path]:
    result = []
    for path in PLUGIN.rglob("*"):
        relative = path.relative_to(PLUGIN)
        if not path.is_file() or "__pycache__" in relative.parts:
            continue
        if path.name == ".DS_Store" or path.suffix == ".pyc":
            continue
        result.append(path)
    return sorted(result, key=lambda item: item.relative_to(PLUGIN).as_posix())


def main() -> int:
    manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description="Package exact IronStruct plugin bytes")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = (args.output or (PLUGIN.parent / "dist" / f"{manifest['name']}-{manifest['version']}.zip")).resolve()
    if PLUGIN == output or PLUGIN in output.parents:
        parser.error("output must be outside the plugin directory")
    output.parent.mkdir(parents=True, exist_ok=True)

    files = included_files()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = Path(manifest["name"]) / path.relative_to(PLUGIN)
            info = zipfile.ZipInfo(relative.as_posix(), FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)

    data = output.read_bytes()
    receipt = {
        "schema": "ironstruct.plugin_package_receipt.v1",
        "plugin": {"name": manifest["name"], "version": manifest["version"]},
        "archive": {"path": output.name, "bytes": len(data), "sha256": sha256(data)},
        "files": [
            {
                "path": path.relative_to(PLUGIN).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path.read_bytes()),
            }
            for path in files
        ],
    }
    receipt_path = output.with_suffix(".receipt.json")
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"packaged {output} bytes={len(data)} sha256={receipt['archive']['sha256']}")
    print(f"receipt {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
