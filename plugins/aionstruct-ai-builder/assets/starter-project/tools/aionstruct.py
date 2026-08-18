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
from aionstruct_plan import load_plan, lower_plan, validate_plan  # noqa: E402
from aionstruct_quality import load_contract, quality_report  # noqa: E402
from aionstruct_validate import load_blueprint_json, validate_blueprint  # noqa: E402
from lib.mcstructure_le import BLOCK_VERSION, encode_mcstructure  # noqa: E402
from lib.mcstructure_reader import decode_mcstructure_file  # noqa: E402
from render_aionstruct_preview import load_expanded_ir, write_preview  # noqa: E402


TOOL_VERSION = "1.2.0"


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


def inspect_materials(blueprint_path: Path) -> dict[str, Any]:
    ir = expand(load_validated(blueprint_path))
    counts = Counter(cell["block"] for cell in ir["cells"])
    return {
        "schema": "aionstruct.materials.v1",
        "structure_id": ir["id"],
        "size": ir["size"],
        "distinct_blocks": len(counts),
        "explicit_cells": len(ir["cells"]),
        "block_counts": dict(sorted(counts.items())),
        "source_sha256": sha256(blueprint_path.read_bytes()),
    }


def inspect_layers(blueprint_path: Path) -> dict[str, Any]:
    ir = expand(load_validated(blueprint_path))
    volume_per_layer = ir["size"][0] * ir["size"][2]
    layers = []
    for y in range(ir["size"][1]):
        counts = Counter(cell["block"] for cell in ir["cells"] if cell["y"] == y)
        explicit = sum(counts.values())
        layers.append(
            {
                "y": y,
                "explicit_cells": explicit,
                "explicit_air_cells": counts.get("minecraft:air", 0),
                "void_cells": volume_per_layer - explicit,
                "block_counts": dict(sorted(counts.items())),
            }
        )
    return {
        "schema": "aionstruct.layers.v1",
        "structure_id": ir["id"],
        "size": ir["size"],
        "layers": layers,
        "source_sha256": sha256(blueprint_path.read_bytes()),
    }


def structural_fingerprint(blueprint_path: Path) -> dict[str, Any]:
    ir = expand(load_validated(blueprint_path))
    canonical = {
        "size": ir["size"],
        "origin": ir["origin"],
        "cells": ir["cells"],
        "anchors": sorted(ir["anchors"], key=lambda item: canonical_bytes(item)),
        "connectors": sorted(ir["connectors"], key=lambda item: canonical_bytes(item)),
    }
    return {
        "schema": "aionstruct.fingerprint.v1",
        "structure_id": ir["id"],
        "algorithm": "sha256-canonical-final-structure",
        "sha256": sha256(canonical_bytes(canonical)),
        "size": ir["size"],
        "explicit_cells": len(ir["cells"]),
    }


def _normalized_topology(cells: list[dict[str, Any]]) -> list[list[Any]]:
    """Return the lexicographically smallest horizontal dihedral occupancy."""
    classified = [
        (cell["x"], cell["y"], cell["z"], "air" if cell["block"] == "minecraft:air" else "solid")
        for cell in cells
    ]
    transforms = (
        lambda x, z: (x, z), lambda x, z: (-z, x),
        lambda x, z: (-x, -z), lambda x, z: (z, -x),
        lambda x, z: (-x, z), lambda x, z: (x, -z),
        lambda x, z: (z, x), lambda x, z: (-z, -x),
    )
    candidates: list[list[list[Any]]] = []
    for transform in transforms:
        transformed = []
        for x, y, z, kind in classified:
            transformed_x, transformed_z = transform(x, z)
            transformed.append((transformed_x, y, transformed_z, kind))
        if not transformed:
            candidates.append([])
            continue
        minimum_x = min(row[0] for row in transformed)
        minimum_y = min(row[1] for row in transformed)
        minimum_z = min(row[2] for row in transformed)
        candidates.append(sorted(
            [[x - minimum_x, y - minimum_y, z - minimum_z, kind] for x, y, z, kind in transformed]
        ))
    return min(candidates, key=canonical_bytes)


def topology_fingerprint(blueprint_path: Path) -> dict[str, Any]:
    """Fingerprint geometry while ignoring block palette, translation, and X/Z dihedral orientation."""
    ir = expand(load_validated(blueprint_path))
    topology = _normalized_topology(ir["cells"])
    bounds = [0, 0, 0]
    if topology:
        bounds = [
            max(row[0] for row in topology) + 1,
            max(row[1] for row in topology) + 1,
            max(row[2] for row in topology) + 1,
        ]
    counts = Counter(row[3] for row in topology)
    return {
        "schema": "aionstruct.topology_fingerprint.v1",
        "structure_id": ir["id"],
        "algorithm": "sha256-normalized-xz-dihedral-air-solid-topology",
        "sha256": sha256(canonical_bytes(topology)),
        "normalized_bounds": bounds,
        "solid_cells": counts["solid"],
        "explicit_air_cells": counts["air"],
        "void_semantics": "coordinates absent from the normalized explicit-cell set remain void",
    }


def portable_source_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return f"external/{path.name}"


def portfolio_audit(blueprint_paths: list[Path], contract_path: Path | None = None) -> dict[str, Any]:
    """Detect architectural clones and optionally enforce per-structure purpose contracts."""
    rows = []
    errors: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for path in blueprint_paths:
        exact = structural_fingerprint(path)
        topology = topology_fingerprint(path)
        structure_id = exact["structure_id"]
        if structure_id in seen_ids:
            errors.append({"code": "duplicate_structure_id", "structure_id": structure_id})
        seen_ids.add(structure_id)
        rows.append({
            "structure_id": structure_id,
            "path": portable_source_path(path),
            "exact_sha256": exact["sha256"],
            "topology_sha256": topology["sha256"],
            "normalized_bounds": topology["normalized_bounds"],
            "solid_cells": topology["solid_cells"],
            "explicit_air_cells": topology["explicit_air_cells"],
        })
    groups: dict[str, list[str]] = {}
    for row in rows:
        groups.setdefault(row["topology_sha256"], []).append(row["structure_id"])
    duplicate_groups = [
        {"topology_sha256": digest, "structure_ids": sorted(ids)}
        for digest, ids in sorted(groups.items()) if len(ids) > 1
    ]
    for group in duplicate_groups:
        errors.append({"code": "duplicate_topology", **group})

    contract_sha256 = None
    if contract_path is not None:
        contract_bytes = contract_path.read_bytes()
        contract_sha256 = sha256(contract_bytes)
        contract = json.loads(contract_bytes)
        if not isinstance(contract, dict) or contract.get("schema") != "aionstruct.portfolio_contract.v1":
            errors.append({"code": "invalid_contract_schema", "path": portable_source_path(contract_path)})
        entries = contract.get("structures", []) if isinstance(contract, dict) else []
        by_id: dict[str, dict[str, Any]] = {}
        for index, entry in enumerate(entries if isinstance(entries, list) else []):
            structure_id = entry.get("structure_id") if isinstance(entry, dict) else None
            if not isinstance(structure_id, str) or structure_id in by_id:
                errors.append({"code": "invalid_or_duplicate_contract_id", "index": index})
                continue
            by_id[structure_id] = entry
        for structure_id in sorted(seen_ids - set(by_id)):
            errors.append({"code": "missing_purpose_contract", "structure_id": structure_id})
        for structure_id in sorted(set(by_id) - seen_ids):
            errors.append({"code": "contract_structure_not_audited", "structure_id": structure_id})
        allowed_axes = {"silhouette", "approach", "traversal", "function", "environmental_story"}
        for structure_id in sorted(seen_ids & set(by_id)):
            entry = by_id[structure_id]
            purpose = entry.get("purpose", {})
            if not isinstance(purpose, dict):
                errors.append({"code": "invalid_purpose_object", "structure_id": structure_id})
                purpose = {}
            for field in ("walk_toward", "enter", "changes_after_departure"):
                if not isinstance(purpose.get(field), str) or not purpose[field].strip():
                    errors.append({"code": "missing_purpose_answer", "structure_id": structure_id, "field": field})
            axes = entry.get("distinctness_axes", [])
            if (
                not isinstance(axes, list)
                or len(set(axes)) < 2
                or len(set(axes)) != len(axes)
                or any(axis not in allowed_axes for axis in axes)
            ):
                errors.append({"code": "invalid_distinctness_axes", "structure_id": structure_id})

    return {
        "schema": "aionstruct.portfolio_audit.v1",
        "status": "PASS" if not errors else "FAIL",
        "algorithm": "palette-independent-translation-and-xz-dihedral-invariant",
        "counts": {
            "structures": len(rows),
            "distinct_topologies": len(groups),
            "duplicate_topology_groups": len(duplicate_groups),
        },
        "structures": sorted(rows, key=lambda row: row["structure_id"]),
        "duplicate_topology_groups": duplicate_groups,
        "contract": None if contract_path is None else {"path": portable_source_path(contract_path), "sha256": contract_sha256},
        "errors": errors,
        "proof_boundary": [
            "static_final_ir_topology_and_authored_purpose_contract_only",
            "not_visual_quality_gameplay_memorability_worldgen_or_runtime_proof",
        ],
    }


def structural_diff(left_path: Path, right_path: Path) -> dict[str, Any]:
    left = expand(load_validated(left_path))
    right = expand(load_validated(right_path))
    left_cells = {(cell["x"], cell["y"], cell["z"]): cell for cell in left["cells"]}
    right_cells = {(cell["x"], cell["y"], cell["z"]): cell for cell in right["cells"]}
    changed = []
    for point in sorted(set(left_cells) | set(right_cells)):
        if left_cells.get(point) != right_cells.get(point):
            changed.append(
                {
                    "local": list(point),
                    "left": left_cells.get(point),
                    "right": right_cells.get(point),
                }
            )
    left_anchors = sorted(left["anchors"], key=lambda item: canonical_bytes(item))
    right_anchors = sorted(right["anchors"], key=lambda item: canonical_bytes(item))
    left_connectors = sorted(left["connectors"], key=lambda item: canonical_bytes(item))
    right_connectors = sorted(right["connectors"], key=lambda item: canonical_bytes(item))
    metadata_changes = {
        "size": left["size"] != right["size"],
        "origin": left["origin"] != right["origin"],
        "anchors": left_anchors != right_anchors,
        "connectors": left_connectors != right_connectors,
    }
    return {
        "schema": "aionstruct.structural_diff.v1",
        "identical": not changed and not any(metadata_changes.values()),
        "left": {"id": left["id"], "size": left["size"], "explicit_cells": len(left_cells)},
        "right": {"id": right["id"], "size": right["size"], "explicit_cells": len(right_cells)},
        "changed_cell_count": len(changed),
        "changed_cell_samples": changed[:64],
        "metadata_changes": metadata_changes,
        "sample_limit": 64,
    }


def emit_json(value: dict[str, Any], output: Path | None = None) -> None:
    data = canonical_bytes(value)
    if output is None:
        sys.stdout.buffer.write(data)
    else:
        atomic_write(output.resolve(), data)
        print(f"PASS wrote {output.resolve()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Design, inspect, preview, and compile AIONSTRUCT structures offline")
    parser.add_argument("--version", action="version", version=f"%(prog)s {TOOL_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check the local runtime")
    plan_cmd = sub.add_parser("plan", help="validate or lower semantic Plan v1 source")
    plan_actions = plan_cmd.add_subparsers(dest="plan_action", required=True)
    plan_validate = plan_actions.add_parser("validate", help="return structured Plan diagnostics")
    plan_validate.add_argument("plan", type=Path)
    plan_lower = plan_actions.add_parser("lower", help="emit ordinary Blueprint v1 plus a source map")
    plan_lower.add_argument("plan", type=Path)
    plan_lower.add_argument("--output", type=Path)
    plan_lower.add_argument("--source-map", type=Path)
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
    materials = sub.add_parser("materials", help="inspect deterministic final block counts")
    materials.add_argument("blueprint", type=Path)
    materials.add_argument("--output", type=Path)
    layers = sub.add_parser("layers", help="inspect deterministic per-Y final layers")
    layers.add_argument("blueprint", type=Path)
    layers.add_argument("--output", type=Path)
    fingerprint = sub.add_parser("fingerprint", help="hash canonical final structure content")
    fingerprint.add_argument("blueprint", type=Path)
    fingerprint.add_argument("--output", type=Path)
    topology = sub.add_parser("topology", help="hash palette-independent geometry across horizontal rotations/reflections")
    topology.add_argument("blueprint", type=Path)
    topology.add_argument("--output", type=Path)
    portfolio = sub.add_parser("portfolio", help="audit multiple blueprints for clone topology and purpose contracts")
    portfolio.add_argument("blueprints", nargs="+", type=Path)
    portfolio.add_argument("--contract", type=Path)
    portfolio.add_argument("--output", type=Path)
    diff = sub.add_parser("diff", help="compare two expanded structures without modifying them")
    diff.add_argument("left", type=Path)
    diff.add_argument("right", type=Path)
    diff.add_argument("--output", type=Path)
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

        if args.command == "plan":
            plan_path = args.plan.resolve()
            plan = load_plan(plan_path)
            diagnostics = validate_plan(plan)
            if args.plan_action == "validate":
                emit_json(
                    {
                        "schema": "aionstruct.plan_diagnostics.v1",
                        "status": "PASS" if not diagnostics else "FAIL",
                        "plan": str(plan_path),
                        "diagnostics": diagnostics,
                    }
                )
                return 0 if not diagnostics else 1
            blueprint, source_map = lower_plan(plan)
            short_name = plan.get("short_name") or plan["id"].split("/")[-1]
            output = (args.output or (ROOT / "build" / f"{short_name}.blueprint.json")).resolve()
            source_output = (args.source_map or output.with_suffix(".source-map.json")).resolve()
            atomic_write(output, canonical_bytes(blueprint))
            atomic_write(source_output, canonical_bytes(source_map))
            print(json.dumps({"status": "PASS", "blueprint": str(output), "source_map": str(source_output)}, sort_keys=True))
            return 0

        if args.command == "diff":
            emit_json(structural_diff(args.left.resolve(), args.right.resolve()), args.output)
            return 0

        if args.command == "portfolio":
            report = portfolio_audit(
                [path.resolve() for path in args.blueprints],
                args.contract.resolve() if args.contract else None,
            )
            emit_json(report, args.output)
            return 0 if report["status"] == "PASS" else 1

        if args.command in {"materials", "layers", "fingerprint", "topology"}:
            blueprint_path = args.blueprint.resolve()
            result = {
                "materials": inspect_materials,
                "layers": inspect_layers,
                "fingerprint": structural_fingerprint,
                "topology": topology_fingerprint,
            }[args.command](blueprint_path)
            emit_json(result, args.output)
            return 0

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
