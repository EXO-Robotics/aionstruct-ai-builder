#!/usr/bin/env python3
"""Portable AIONSTRUCT command line for offline Bedrock structure development."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from aionstruct_expand import expand  # noqa: E402
from aionstruct_quality import load_contract, quality_report  # noqa: E402
from aionstruct_validate import load_blueprint_json, validate_blueprint  # noqa: E402
from lib.mcstructure_le import BLOCK_VERSION, encode_mcstructure  # noqa: E402
from lib.mcstructure_reader import decode_mcstructure_file  # noqa: E402
from render_aionstruct_preview import load_expanded_ir, write_preview  # noqa: E402


TOOL_VERSION = "1.0.0"


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def load_validated(path: Path) -> dict[str, Any]:
    blueprint = load_blueprint_json(path)
    errors = validate_blueprint(blueprint, path)
    if errors:
        raise ValueError("invalid blueprint:\n" + "\n".join(f"- {error}" for error in errors))
    return blueprint


def compare_decoded(ir: dict[str, Any], decoded: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if decoded["size"] != ir["size"]:
        return [f"size mismatch: decoded={decoded['size']} ir={ir['size']}"]
    expected = {(cell["x"], cell["y"], cell["z"]): cell for cell in ir["cells"]}
    for item in decoded["cells"]:
        point = (item["x"], item["y"], item["z"])
        actual = item["primary"]
        source = expected.get(point)
        if source is None:
            if actual["classification"] != "void":
                errors.append(f"expected void at {point}, got {actual['classification']}")
            continue
        expected_class = "air" if source["block"] == "minecraft:air" else "block"
        if actual["classification"] != expected_class:
            errors.append(f"classification mismatch at {point}")
            continue
        permutation = actual.get("permutation", {})
        if permutation.get("name") != source["block"]:
            errors.append(f"block mismatch at {point}: {permutation.get('name')} != {source['block']}")
        if permutation.get("states", {}) != source.get("states", {}):
            errors.append(f"state mismatch at {point}")
    if any(index != -1 for index in decoded["block_indices"][1]):
        errors.append("secondary block-index layer must remain entirely void")
    return errors


def compile_blueprint(blueprint_path: Path, output: Path, receipt_path: Path) -> dict[str, Any]:
    blueprint = load_validated(blueprint_path)
    ir = expand(blueprint)
    encoded, palette, indices = encode_mcstructure(tuple(ir["size"]), ir["cells"])
    atomic_write(output, encoded)
    decoded = decode_mcstructure_file(output)
    errors = compare_decoded(ir, decoded)
    if errors:
        output.unlink(missing_ok=True)
        raise ValueError("independent decode failed:\n" + "\n".join(f"- {error}" for error in errors[:20]))
    counts = Counter(
        "air" if cell["block"] == "minecraft:air" else "block" for cell in ir["cells"]
    )
    volume = ir["size"][0] * ir["size"][1] * ir["size"][2]
    receipt = {
        "schema": "aionstruct.compile_receipt.v1",
        "status": "PASS_STATIC_ENCODE_AND_INDEPENDENT_DECODE",
        "tool_version": TOOL_VERSION,
        "block_runtime_version": BLOCK_VERSION,
        "structure_id": blueprint["id"],
        "inputs": {
            "blueprint": str(blueprint_path.relative_to(ROOT)),
            "blueprint_sha256": sha256(blueprint_path.read_bytes()),
            "expanded_ir_sha256": sha256(canonical_bytes(ir)),
        },
        "artifact": {
            "path": str(output.relative_to(ROOT)),
            "bytes": len(encoded),
            "sha256": sha256(encoded),
            "size": ir["size"],
            "palette_entries": len(palette),
            "block_cells": counts["block"],
            "explicit_air_cells": counts["air"],
            "void_cells": volume - len(ir["cells"]),
            "primary_index_count": len(indices),
        },
        "verification": {
            "reader": "tools/lib/mcstructure_reader.py",
            "full_volume_compared": True,
            "mismatches": 0,
        },
        "proof_boundary": [
            "offline_schema_ir_encode_decode_only",
            "not_bds_structure_load_or_persistence_proof",
            "not_client_visual_gameplay_worldgen_or_console_proof",
        ],
    }
    atomic_write(receipt_path, canonical_bytes(receipt))
    return receipt


def render_all(blueprint_path: Path, contract_path: Path | None, output_dir: Path) -> None:
    ir, source = load_expanded_ir(blueprint_path)
    write_preview(ir, output_dir / "core", source)
    try:
        from render_aionstruct_isometric import image_bytes as iso_bytes, render_board
    except ImportError as exc:
        raise ValueError("Pillow is required for PNG previews; run python3 -m pip install -r requirements.txt") from exc
    atomic_write(output_dir / "isometric_engineering_board.png", iso_bytes(render_board(ir)))
    if contract_path:
        from render_aionstruct_lightmap import image_bytes as light_bytes, render_lightmap
        contract = load_contract(contract_path)
        atomic_write(output_dir / "static_light_heatmap.png", light_bytes(render_lightmap(ir, contract)))


def default_paths(blueprint_path: Path) -> tuple[Path, Path, Path, Path]:
    short_name = load_validated(blueprint_path).get("short_name") or blueprint_path.stem.split(".")[0]
    return (
        ROOT / "build" / f"{short_name}.ir.json",
        ROOT / "dist" / f"{short_name}.mcstructure",
        ROOT / "reports" / short_name / "compile_receipt.json",
        ROOT / "reports" / "previews" / short_name,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Design, inspect, preview, and compile AIONSTRUCT structures offline")
    parser.add_argument("--version", action="version", version=f"%(prog)s {TOOL_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check the local runtime")
    validate = sub.add_parser("validate", help="strictly validate one blueprint")
    validate.add_argument("blueprint", type=Path)
    expand_cmd = sub.add_parser("expand", help="write deterministic final IR")
    expand_cmd.add_argument("blueprint", type=Path)
    expand_cmd.add_argument("--output", type=Path)
    compile_cmd = sub.add_parser("compile", help="compile and independently reopen .mcstructure bytes")
    compile_cmd.add_argument("blueprint", type=Path)
    compile_cmd.add_argument("--output", type=Path)
    compile_cmd.add_argument("--receipt", type=Path)
    preview = sub.add_parser("preview", help="render SVG, isometric, and optional light previews")
    preview.add_argument("blueprint", type=Path)
    preview.add_argument("--contract", type=Path)
    preview.add_argument("--output-dir", type=Path)
    quality = sub.add_parser("quality", help="run the static quality contract")
    quality.add_argument("blueprint", type=Path)
    quality.add_argument("--contract", required=True, type=Path)
    quality.add_argument("--output", type=Path)
    build = sub.add_parser("build", help="run validate, IR, compile, previews, and quality")
    build.add_argument("blueprint", type=Path)
    build.add_argument("--contract", required=True, type=Path)
    args = parser.parse_args()

    try:
        if args.command == "doctor":
            try:
                import PIL
                pillow = PIL.__version__
            except ImportError:
                pillow = None
            print(json.dumps({"python": platform.python_version(), "pillow": pillow, "tool_version": TOOL_VERSION}, sort_keys=True))
            return 0 if sys.version_info >= (3, 10) else 1

        blueprint_path = args.blueprint.resolve()
        ir_path, structure_path, receipt_path, preview_dir = default_paths(blueprint_path)
        if args.command == "validate":
            blueprint = load_validated(blueprint_path)
            print(f"PASS {blueprint['id']} size={blueprint['size']} ops={len(blueprint['ops'])}")
        elif args.command == "expand":
            output = (args.output or ir_path).resolve()
            atomic_write(output, canonical_bytes(expand(load_validated(blueprint_path))))
            print(f"PASS expanded {output}")
        elif args.command == "compile":
            receipt = compile_blueprint(
                blueprint_path,
                (args.output or structure_path).resolve(),
                (args.receipt or receipt_path).resolve(),
            )
            print(f"{receipt['status']} sha256={receipt['artifact']['sha256']}")
        elif args.command == "preview":
            render_all(
                blueprint_path,
                args.contract.resolve() if args.contract else None,
                (args.output_dir or preview_dir).resolve(),
            )
            print(f"PASS previews {args.output_dir or preview_dir}")
        elif args.command == "quality":
            contract = args.contract.resolve()
            report = quality_report(ROOT, blueprint_path, contract)
            output = (args.output or (ROOT / "reports" / blueprint_path.stem / "quality_report.json")).resolve()
            atomic_write(output, canonical_bytes(report))
            print(f"{report['status']} gates={sum(report['gates'].values())}/{len(report['gates'])}")
            return 0 if all(report["gates"].values()) else 1
        elif args.command == "build":
            contract = args.contract.resolve()
            atomic_write(ir_path, canonical_bytes(expand(load_validated(blueprint_path))))
            receipt = compile_blueprint(blueprint_path, structure_path, receipt_path)
            render_all(blueprint_path, contract, preview_dir)
            report = quality_report(ROOT, blueprint_path, contract)
            report_path = ROOT / "reports" / blueprint_path.stem / "quality_report.json"
            atomic_write(report_path, canonical_bytes(report))
            print(json.dumps({
                "compile": receipt["status"], "quality": report["status"],
                "mcstructure": str(structure_path), "previews": str(preview_dir),
            }, sort_keys=True))
            return 0 if all(report["gates"].values()) else 1
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
