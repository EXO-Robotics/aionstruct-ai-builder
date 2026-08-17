#!/usr/bin/env python3
"""Audit AIONSTRUCT design quality without changing compiler authority."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from aionstruct_expand import expand  # noqa: E402
from aionstruct_validate import load_blueprint_json, validate_blueprint  # noqa: E402
from lib.aionstruct_spatial import (  # noqa: E402
    cell_map,
    connected_component,
    is_supporting,
    manhattan,
    walkable_floor_cells,
)


SCHEMA = "aionstruct.quality_report.v1"
CONTRACT_SCHEMA = "aionstruct.quality_contract.v1"


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_contract(path: Path) -> dict[str, Any]:
    value = load_blueprint_json(path)
    required = {
        "schema", "structure_id", "generation", "preserve", "architectural_targets",
        "lighting", "materials", "traversal", "previews", "client_review",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("quality contract must contain the exact v1 top-level fields")
    if value["schema"] != CONTRACT_SCHEMA:
        raise ValueError(f"unsupported quality contract schema {value.get('schema')!r}")
    if not isinstance(value["generation"], int) or value["generation"] < 2:
        raise ValueError("quality contract generation must be an integer >= 2")
    lighting = value["lighting"]
    nested_fields = {
        "architectural_targets": {
            "mass_hierarchy", "minimum_facade_depth_layers", "maximum_repeated_bay_run",
            "minimum_distinct_room_identities", "required_preview_views", "room_quality",
        },
        "lighting": {
            "default_zone", "minimum_floor_block_light", "required_walkable_coverage",
            "emission_by_block", "strategy",
        },
        "materials": {
            "primary_structure_blocks", "ratio_excluded_blocks", "maximum_primary_ratio",
            "minimum_distinct_blocks", "strategy",
        },
        "traversal": {"start_anchor", "headroom", "max_step", "required_anchors", "strategy"},
        "previews": {"directory", "required_artifacts", "require_source_bound_manifest"},
        "client_review": {"required", "conditions", "record"},
    }
    for field, expected in nested_fields.items():
        if not isinstance(value[field], dict) or set(value[field]) != expected:
            raise ValueError(f"quality contract {field} must contain the exact v1 fields")
    if not 0 <= lighting["minimum_floor_block_light"] <= 15:
        raise ValueError("minimum_floor_block_light must be in 0..15")
    if not 0.0 <= lighting["required_walkable_coverage"] <= 1.0:
        raise ValueError("required_walkable_coverage must be in 0..1")
    if value["previews"]["require_source_bound_manifest"] is not True:
        raise ValueError("quality contracts must require source-bound previews")
    if len(value["traversal"]["required_anchors"]) != len(set(value["traversal"]["required_anchors"])):
        raise ValueError("required traversal anchors must be unique")
    return value


def _percentile(values: list[int], fraction: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def light_sources(ir: dict[str, Any], contract: dict[str, Any]) -> list[tuple[tuple[int, int, int], int, dict[str, Any]]]:
    cells = cell_map(ir)
    emissions = {str(block): int(level) for block, level in contract["lighting"]["emission_by_block"].items()}
    return [
        (position, emissions[cell["block"]], cell)
        for position, cell in sorted(cells.items())
        if cell.get("block") in emissions
    ]


def estimate_light_field(
    ir: dict[str, Any], contract: dict[str, Any], walkable: set[tuple[int, int, int]],
) -> dict[tuple[int, int, int], int]:
    """Return the shared optimistic light estimate for every walkable cell."""
    sources = light_sources(ir, contract)
    return {
        point: max(
            (max(0, emission - manhattan(point, position)) for position, emission, _ in sources),
            default=0,
        )
        for point in sorted(walkable)
    }


def analyze_lighting(ir: dict[str, Any], contract: dict[str, Any], walkable: set[tuple[int, int, int]]) -> dict[str, Any]:
    cells = cell_map(ir)
    sources = light_sources(ir, contract)
    field = estimate_light_field(ir, contract, walkable)
    minimum = int(contract["lighting"]["minimum_floor_block_light"])
    estimates = list(field.values())
    underlit: list[tuple[int, int, int]] = []
    nearest_distances: list[int] = []
    for point in sorted(walkable):
        estimate = field[point]
        if estimate < minimum:
            underlit.append(point)
        if sources:
            nearest_distances.append(min(manhattan(point, position) for position, _, _ in sources))

    support = []
    for position, emission, cell in sources:
        states = cell.get("states", {})
        hanging = bool(states.get("hanging", False))
        x, y, z = position
        support_position = (x, y + 1, z) if hanging else (x, y - 1, z)
        supported = is_supporting(cells.get(support_position))
        support.append({
            "position": list(position),
            "block": cell["block"],
            "emission": emission,
            "hanging": hanging,
            "support_position": list(support_position),
            "supported": supported,
        })

    covered = len(walkable) - len(underlit)
    coverage = covered / len(walkable) if walkable else 0.0
    return {
        "method": "optimistic_unobstructed_manhattan_ceiling",
        "sources": support,
        "source_count": len(sources),
        "walkable_cells": len(walkable),
        "minimum_floor_block_light": minimum,
        "covered_cells": covered,
        "underlit_cells": len(underlit),
        "coverage_fraction": round(coverage, 6),
        "estimated_light_min": min(estimates, default=0),
        "estimated_light_p50": _percentile(estimates, 0.50),
        "estimated_light_p95": _percentile(estimates, 0.95),
        "nearest_source_distance_p50": _percentile(nearest_distances, 0.50),
        "nearest_source_distance_p95": _percentile(nearest_distances, 0.95),
        "max_nearest_source_distance": max(nearest_distances, default=None),
        "underlit_samples": [list(point) for point in underlit[:32]],
        "all_sources_supported": all(item["supported"] for item in support),
    }


def analyze_materials(ir: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    ignored = set(contract["materials"]["ratio_excluded_blocks"])
    primary = set(contract["materials"]["primary_structure_blocks"])
    counts = Counter(
        cell["block"] for cell in ir["cells"]
        if cell["block"] not in ignored
    )
    denominator = sum(counts.values())
    primary_count = sum(counts[block] for block in primary)
    ratio = primary_count / denominator if denominator else 0.0
    return {
        "counted_cells": denominator,
        "primary_cells": primary_count,
        "primary_ratio": round(ratio, 6),
        "maximum_primary_ratio": contract["materials"]["maximum_primary_ratio"],
        "distinct_counted_blocks": len(counts),
        "minimum_distinct_blocks": contract["materials"]["minimum_distinct_blocks"],
        "block_counts": dict(sorted(counts.items())),
    }


def analyze_traversal(ir: dict[str, Any], contract: dict[str, Any], walkable: set[tuple[int, int, int]]) -> dict[str, Any]:
    anchors = {item["name"]: tuple(item["local"]) for item in ir.get("anchors", [])}
    required = list(contract["traversal"]["required_anchors"])
    start_name = contract["traversal"]["start_anchor"]
    start = anchors.get(start_name)
    reached = connected_component(walkable, start, max_step=int(contract["traversal"]["max_step"])) if start else set()
    results = {
        name: {
            "present": name in anchors,
            "position": list(anchors[name]) if name in anchors else None,
            "walkable": anchors.get(name) in walkable,
            "reachable": anchors.get(name) in reached,
        }
        for name in required
    }
    return {
        "headroom": contract["traversal"]["headroom"],
        "walkable_cells": len(walkable),
        "reachable_cells": len(reached),
        "required_anchors": results,
        "all_required_anchors_reachable": all(item["reachable"] for item in results.values()),
    }


def analyze_previews(root: Path, blueprint_path: Path, contract: dict[str, Any]) -> dict[str, Any]:
    preview_dir = root / contract["previews"]["directory"]
    manifest_path = preview_dir / "preview_manifest.json"
    source_hash = sha256(blueprint_path.read_bytes())
    if not manifest_path.exists():
        return {"directory": str(preview_dir.relative_to(root)), "manifest_present": False, "source_bound": False, "artifacts": {}}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = {}
    declared = {item["path"]: item for item in manifest.get("artifacts", [])}
    for name in contract["previews"]["required_artifacts"]:
        path = preview_dir / name
        entry = declared.get(name)
        artifacts[name] = {
            "present": path.exists(),
            "hash_matches": bool(path.exists() and entry and sha256(path.read_bytes()) == entry.get("sha256")),
        }
    manifest_input = manifest.get("input") or {}
    return {
        "directory": str(preview_dir.relative_to(root)),
        "manifest_present": True,
        "source_sha256": source_hash,
        "manifest_source_sha256": manifest_input.get("sha256"),
        "source_bound": manifest_input.get("sha256") == source_hash,
        "artifacts": artifacts,
    }


def quality_report(root: Path, blueprint_path: Path, contract_path: Path) -> dict[str, Any]:
    contract = load_contract(contract_path)
    blueprint = load_blueprint_json(blueprint_path)
    errors = validate_blueprint(blueprint, blueprint_path)
    if errors:
        raise ValueError("invalid blueprint: " + " | ".join(errors))
    if blueprint.get("id") != contract["structure_id"]:
        raise ValueError("contract structure_id does not match blueprint")
    ir = expand(blueprint)
    walkable = walkable_floor_cells(ir, headroom=int(contract["traversal"]["headroom"]))
    lighting = analyze_lighting(ir, contract, walkable)
    materials = analyze_materials(ir, contract)
    traversal = analyze_traversal(ir, contract, walkable)
    previews = analyze_previews(root, blueprint_path, contract)

    gates = {
        "traversal": traversal["all_required_anchors_reachable"],
        "light_source_support": lighting["all_sources_supported"],
        "optimistic_light_coverage": lighting["coverage_fraction"] >= contract["lighting"]["required_walkable_coverage"],
        "material_dominance": materials["primary_ratio"] <= contract["materials"]["maximum_primary_ratio"],
        "material_variety": materials["distinct_counted_blocks"] >= contract["materials"]["minimum_distinct_blocks"],
        "preview_source_binding": previews["source_bound"] and all(item["hash_matches"] for item in previews["artifacts"].values()),
    }
    recommendations = []
    if not gates["optimistic_light_coverage"]:
        recommendations.append("author zone-based, support-verified lighting before voxel compilation")
    if not gates["material_dominance"]:
        recommendations.append("break primary masonry mass with structural trim, roof, floor, and depth-layer materials")
    if not gates["preview_source_binding"]:
        recommendations.append("regenerate source-bound engineering previews and enforce preview --check")
    return {
        "schema": SCHEMA,
        "status": "PASS_BLUEPRINT_QUALITY_STATIC" if all(gates.values()) else "NEEDS_G2_BLUEPRINT_REDESIGN",
        "structure_id": blueprint["id"],
        "generation": contract["generation"],
        "inputs": {
            "blueprint": str(blueprint_path.relative_to(root)),
            "blueprint_sha256": sha256(blueprint_path.read_bytes()),
            "contract": str(contract_path.relative_to(root)),
            "contract_sha256": sha256(contract_path.read_bytes()),
        },
        "preserve": contract["preserve"],
        "architectural_targets": contract["architectural_targets"],
        "gates": gates,
        "lighting": lighting,
        "materials": materials,
        "traversal": traversal,
        "previews": previews,
        "recommendations": recommendations,
        "client_review": contract["client_review"],
        "proof_boundary": [
            "static_expanded_ir_analysis",
            "optimistic_unobstructed_light_estimate_only",
            "not_bds_light_sampling_or_mob_spawn_or_client_visual_proof",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("blueprint", type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        report = quality_report(ROOT, args.blueprint.resolve(), args.contract.resolve())
        data = canonical_bytes(report)
        if args.check:
            if not args.output.exists() or args.output.read_bytes() != data:
                print(f"STALE {args.output}", file=sys.stderr)
                return 1
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(data)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"{report['status']} gates={sum(report['gates'].values())}/{len(report['gates'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
