#!/usr/bin/env python3
"""Expand AIONSTRUCT DSL blueprints into placement IR + JS module for the dev pack.

Does not touch Minecraft. Output is pure data for @minecraft/server StructureManager.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any

from aionstruct_validate import load_blueprint_json, validate_blueprint

ROOT = Path(__file__).resolve().parents[1]
DSL_DIR = ROOT / "aionstruct" / "dsl"
IR_DIR = ROOT / "aionstruct" / "ir"
GEN_JS = ROOT / "dev-pack" / "AIONSTRUCT_Structure_Compiler_Dev_BP" / "scripts" / "generated" / "blueprints.js"


VOID_BLOCK = "aionstruct:void"


def canonical_states(states: dict[str, Any] | None) -> dict[str, Any]:
    """Return a deterministic state map without coercing typed values."""
    return {key: states[key] for key in sorted(states or {})}


def resolve_permutation(
    palette: dict[str, Any],
    token: str,
    states: dict[str, Any] | None = None,
    version: int | None = None,
) -> dict[str, Any]:
    """Resolve an alias/direct identifier into one canonical permutation."""
    if token == "void":
        return {"block": VOID_BLOCK}
    raw = palette.get(token, token if ":" in token else None)
    if raw is None:
        raise KeyError(f"unknown palette key or block id: {token}")
    if isinstance(raw, str):
        block = raw
        base_states: dict[str, Any] = {}
        base_version = None
    elif isinstance(raw, dict):
        block = raw["block"]
        base_states = dict(raw.get("states") or {})
        base_version = raw.get("version")
    else:
        raise TypeError(f"invalid palette entry for {token}: {type(raw).__name__}")

    merged_states = dict(base_states)
    merged_states.update(states or {})
    result: dict[str, Any] = {"block": block}
    if merged_states:
        result["states"] = canonical_states(merged_states)
    effective_version = version if version is not None else base_version
    if effective_version is not None:
        result["version"] = effective_version
    return result


def clamp_point(p: list[int], size: list[int]) -> tuple[int, int, int]:
    x, y, z = p
    if not (0 <= x < size[0] and 0 <= y < size[1] and 0 <= z < size[2]):
        raise ValueError(f"point out of bounds {p} size={size}")
    return x, y, z


def iter_box(a: list[int], b: list[int]):
    x0, x1 = sorted((a[0], b[0]))
    y0, y1 = sorted((a[1], b[1]))
    z0, z1 = sorted((a[2], b[2]))
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            for z in range(z0, z1 + 1):
                yield x, y, z


def set_block(
    grid: dict[tuple[int, int, int], dict[str, Any]],
    pos: tuple[int, int, int],
    permutation: dict[str, Any],
):
    if permutation["block"] == VOID_BLOCK:
        # An absent cell compiles to -1 and leaves the destination unchanged.
        grid.pop(pos, None)
        return
    grid[pos] = {
        "block": permutation["block"],
        **({"states": canonical_states(permutation["states"])} if permutation.get("states") else {}),
        **({"version": permutation["version"]} if "version" in permutation else {}),
    }


def expand(bp: dict[str, Any]) -> dict[str, Any]:
    size = list(bp["size"])
    palette = dict(bp["palette"])
    grid: dict[tuple[int, int, int], dict[str, Any]] = {}
    anchors: list[dict[str, Any]] = []
    connectors: list[dict[str, Any]] = []

    for op in bp.get("ops", []):
        kind = op["op"]

        if kind == "cuboid":
            block = resolve_permutation(palette, op["block"], op.get("states"), op.get("version"))
            for p in iter_box(op["from"], op["to"]):
                clamp_point(list(p), size)
                set_block(grid, p, block)

        elif kind == "floor":
            block = resolve_permutation(palette, op["block"], op.get("states"), op.get("version"))
            a, b = op["from"], op["to"]
            y = a[1]
            for x in range(min(a[0], b[0]), max(a[0], b[0]) + 1):
                for z in range(min(a[2], b[2]), max(a[2], b[2]) + 1):
                    p = (x, y, z)
                    clamp_point(list(p), size)
                    set_block(grid, p, block)

        elif kind == "wall":
            block = resolve_permutation(palette, op["block"], op.get("states"), op.get("version"))
            for p in iter_box(op["from"], op["to"]):
                clamp_point(list(p), size)
                set_block(grid, p, block)

        elif kind == "shell":
            block = resolve_permutation(palette, op["block"], op.get("states"), op.get("version"))
            a, b = op["from"], op["to"]
            x0, x1 = min(a[0], b[0]), max(a[0], b[0])
            y0, y1 = min(a[1], b[1]), max(a[1], b[1])
            z0, z1 = min(a[2], b[2]), max(a[2], b[2])
            walls = op.get("walls", True)
            do_floor = op.get("floor", True)
            do_ceil = op.get("ceiling", True)
            for x, y, z in iter_box(a, b):
                on_wall = x in (x0, x1) or z in (z0, z1)
                on_floor = y == y0
                on_ceil = y == y1
                if (walls and on_wall) or (do_floor and on_floor) or (do_ceil and on_ceil):
                    clamp_point([x, y, z], size)
                    set_block(grid, (x, y, z), block)

        elif kind == "pillar":
            block = resolve_permutation(palette, op["block"], op.get("states"), op.get("version"))
            x, y, z = clamp_point(op["at"], size)
            h = int(op["height"])
            for i in range(h):
                p = (x, y + i, z)
                clamp_point(list(p), size)
                set_block(grid, p, block)

        elif kind == "set":
            block = resolve_permutation(palette, op["block"], op.get("states"), op.get("version"))
            p = clamp_point(op["at"], size)
            set_block(grid, p, block)

        elif kind == "doorway":
            fill = resolve_permutation(palette, op["fill"])
            face = op["face"]
            width = int(op["width"])
            height = int(op["height"])
            y0 = int(op["y"])
            half = width // 2
            if face in ("north", "south"):
                z = int(op["wall_z"])
                cx = int(op["center_x"])
                for dx in range(-half, width - half):
                    for dy in range(height):
                        p = (cx + dx, y0 + dy, z)
                        clamp_point(list(p), size)
                        set_block(grid, p, fill)
            else:
                x = int(op["wall_x"])
                cz = int(op["center_z"])
                for dz in range(-half, width - half):
                    for dy in range(height):
                        p = (x, y0 + dy, cz + dz)
                        clamp_point(list(p), size)
                        set_block(grid, p, fill)

        elif kind == "window":
            fill = resolve_permutation(palette, op["fill"])
            # same geometry as doorway for MVP
            op2 = dict(op)
            op2["op"] = "doorway"
            # re-enter via doorway logic by recursive call would double-count;
            # inline minimal:
            face = op["face"]
            width = int(op["width"])
            height = int(op["height"])
            y0 = int(op["y"])
            half = width // 2
            if face in ("north", "south"):
                z = int(op["wall_z"])
                cx = int(op["center_x"])
                for dx in range(-half, width - half):
                    for dy in range(height):
                        p = (cx + dx, y0 + dy, z)
                        clamp_point(list(p), size)
                        set_block(grid, p, fill)
            else:
                x = int(op["wall_x"])
                cz = int(op["center_z"])
                for dz in range(-half, width - half):
                    for dy in range(height):
                        p = (x, y0 + dy, cz + dz)
                        clamp_point(list(p), size)
                        set_block(grid, p, fill)

        elif kind == "roof_gable":
            # Simple triangular gable: peak along center of axis-perpendicular
            block = resolve_permutation(palette, op["block"], op.get("states"), op.get("version"))
            fill_gable = resolve_permutation(palette, op["fill_gable"])
            a, b = op["from"], op["to"]
            x0, x1 = min(a[0], b[0]), max(a[0], b[0])
            y0, y1 = min(a[1], b[1]), max(a[1], b[1])
            z0, z1 = min(a[2], b[2]), max(a[2], b[2])
            axis = op.get("axis", "x")
            height = y1 - y0 + 1
            if axis == "x":
                # ridge parallel to X; peak at mid Z
                mid = (z0 + z1) / 2.0
                half_span = max((z1 - z0) / 2.0, 1.0)
                for x in range(x0, x1 + 1):
                    for z in range(z0, z1 + 1):
                        dist = abs(z - mid) / half_span
                        top = y1 - int(dist * (height - 1))
                        for y in range(y0, top + 1):
                            p = (x, y, z)
                            if 0 <= x < size[0] and 0 <= y < size[1] and 0 <= z < size[2]:
                                # shell: place on roof surface + gable ends
                                if y == top or x in (x0, x1):
                                    use = block if y == top else fill_gable
                                    set_block(grid, p, use)
            else:
                mid = (x0 + x1) / 2.0
                half_span = max((x1 - x0) / 2.0, 1.0)
                for z in range(z0, z1 + 1):
                    for x in range(x0, x1 + 1):
                        dist = abs(x - mid) / half_span
                        top = y1 - int(dist * (height - 1))
                        for y in range(y0, top + 1):
                            p = (x, y, z)
                            if 0 <= x < size[0] and 0 <= y < size[1] and 0 <= z < size[2]:
                                if y == top or z in (z0, z1):
                                    use = block if y == top else fill_gable
                                    set_block(grid, p, use)

        elif kind == "scatter":
            block = resolve_permutation(palette, op["block"], op.get("states"), op.get("version"))
            rng = random.Random(int(op["seed"]))
            pts = list(iter_box(op["from"], op["to"]))
            count = min(int(op["count"]), len(pts))
            for p in rng.sample(pts, count):
                clamp_point(list(p), size)
                set_block(grid, p, block)

        elif kind == "replace":
            src = resolve_permutation(palette, op["from_block"])
            dst = resolve_permutation(palette, op["to_block"], op.get("states"), op.get("version"))
            for p in iter_box(op["from"], op["to"]):
                if p in grid and grid[p]["block"] == src["block"] and (
                    "states" not in src or grid[p].get("states", {}) == src["states"]
                ) and ("version" not in src or grid[p].get("version") == src["version"]):
                    set_block(grid, p, dst)

        elif kind == "stair":
            stair_states = dict(op.get("states") or {})
            # stair run: at, steps, facing
            x, y, z = clamp_point(op["at"], size)
            steps = int(op["steps"])
            facing = op.get("facing", "north")
            direction_key = "minecraft:cardinal_direction"
            if direction_key in stair_states and stair_states[direction_key] != facing:
                raise ValueError(
                    f"stair state {direction_key}={stair_states[direction_key]!r} conflicts with facing={facing!r}"
                )
            stair_states[direction_key] = facing
            block = resolve_permutation(palette, op["block"], stair_states, op.get("version"))
            dx, dz = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}[facing]
            for i in range(steps):
                p = (x + dx * i, y + i, z + dz * i)
                clamp_point(list(p), size)
                set_block(grid, p, block)

        elif kind == "arch":
            # cut opening then optional top lintel
            fill = resolve_permutation(palette, op["fill"])
            lintel = resolve_permutation(palette, op["lintel"])
            face = op["face"]
            width = int(op["width"])
            height = int(op["height"])
            y0 = int(op["y"])
            half = width // 2
            if face in ("north", "south"):
                z = int(op["wall_z"])
                cx = int(op["center_x"])
                for dx in range(-half, width - half):
                    for dy in range(height):
                        p = (cx + dx, y0 + dy, z)
                        clamp_point(list(p), size)
                        set_block(grid, p, fill)
                    p = (cx + dx, y0 + height, z)
                    if 0 <= p[1] < size[1]:
                        set_block(grid, p, lintel)
            else:
                x = int(op["wall_x"])
                cz = int(op["center_z"])
                for dz in range(-half, width - half):
                    for dy in range(height):
                        p = (x, y0 + dy, cz + dz)
                        clamp_point(list(p), size)
                        set_block(grid, p, fill)
                    p = (x, y0 + height, cz + dz)
                    if 0 <= p[1] < size[1]:
                        set_block(grid, p, lintel)

        elif kind == "anchor":
            at = clamp_point(op["at"], size)
            anchors.append(
                {
                    "name": op.get("name", op.get("type", "anchor")),
                    "type": op.get("type", "discovery"),
                    "local": list(at),
                    "facing": op.get("facing", "none"),
                }
            )

        elif kind == "connector":
            connectors.append(
                {
                    "id": op.get("name", op.get("id", "conn")),
                    "face": op["face"],
                    "origin_local": op["origin"],
                    "width": op["width"],
                    "height": op["height"],
                    "type": op.get("type", "corridor_std"),
                }
            )

        elif kind == "module":
            raise NotImplementedError("module stamping: expand child IR in a later milestone")

        else:
            raise ValueError(f"unknown op: {kind}")

    # merge explicit anchors dict
    for name, coords in (bp.get("anchors") or {}).items():
        if not any(a["name"] == name for a in anchors):
            anchors.append(
                {
                    "name": name,
                    "type": name.split("_")[0] if "_" in name else name,
                    "local": list(coords),
                    "facing": "none",
                }
            )

    # Build compact placements list + merge adjacent equal permutations into runs
    # on X. Explicit air remains a cell; only the reserved void token is absent.
    cells = []
    for (x, y, z), data in sorted(grid.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0])):
        cell = {"x": x, "y": y, "z": z, "block": data["block"]}
        if "states" in data:
            cell["states"] = data["states"]
        if "version" in data:
            cell["version"] = data["version"]
        cells.append(cell)

    # Also emit cuboid RLE-ish groups for bulk fill optimization
    # Group by (y,z,block,states) continuous x ranges
    bulk: list[dict[str, Any]] = []
    by_row: dict[tuple, list[int]] = {}
    for c in cells:
        key = (
            c["y"],
            c["z"],
            c["block"],
            json.dumps(c.get("states") or {}, sort_keys=True, separators=(",", ":")),
            c.get("version"),
        )
        by_row.setdefault(key, []).append(c["x"])
    for (y, z, block, states_s, version), xs in by_row.items():
        xs = sorted(xs)
        start = xs[0]
        prev = xs[0]
        for x in xs[1:] + [None]:
            if x is not None and x == prev + 1:
                prev = x
                continue
            bulk.append(
                {
                    "from": [start, y, z],
                    "to": [prev, y, z],
                    "block": block,
                    **({"states": json.loads(states_s)} if states_s != "{}" else {}),
                    **({"version": version} if version is not None else {}),
                }
            )
            if x is not None:
                start = prev = x

    raw = json.dumps(bp, sort_keys=True, separators=(",", ":")).encode()
    ir = {
        "schema": "aionstruct.ir.v1",
        "id": bp["id"],
        "short_name": bp.get("short_name") or bp["id"].split("/")[-1],
        "size": size,
        "origin": bp.get("origin", [0, 0, 0]),
        "block_count": len(cells),
        "bulk_runs": len(bulk),
        "cells": cells,
        "bulk": bulk,
        "anchors": anchors,
        "connectors": connectors or bp.get("connectors") or [],
        "meta": bp.get("meta") or {},
        "world_grammar": bp.get("world_grammar"),
        "production_standard": bp.get("production_standard"),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
    }
    return ir


def write_js_bundle(irs: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Embed as JSON parse for speed of authoring; avoids hand-escaped JS
    payload = {ir["short_name"]: ir for ir in irs}
    body = (
        "// AUTO-GENERATED by tools/aionstruct_expand.py — do not edit\n"
        "export const BLUEPRINTS = "
        + json.dumps(payload, indent=2)
        + ";\n"
        "export const BLUEPRINT_NAMES = Object.keys(BLUEPRINTS);\n"
    )
    path.write_text(body, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="AIONSTRUCT JSON files (default: all in aionstruct/dsl)",
    )
    args = ap.parse_args()
    inputs = args.inputs or sorted(DSL_DIR.glob("*.aionstruct.json"))
    if not inputs:
        print("no inputs", file=sys.stderr)
        return 1

    irs = []
    IR_DIR.mkdir(parents=True, exist_ok=True)
    for path in inputs:
        bp = load_blueprint_json(path)
        errs = validate_blueprint(bp, path)
        if errs:
            for err in errs:
                print(f"ERROR {path.name}: {err}", file=sys.stderr)
            return 1
        ir = expand(bp)
        out = IR_DIR / f"{ir['short_name']}.ir.json"
        out.write_text(json.dumps(ir, indent=2) + "\n", encoding="utf-8")
        print(f"expanded {path.name} -> {out.name} blocks={ir['block_count']} bulk={ir['bulk_runs']}")
        irs.append(ir)

    write_js_bundle(irs, GEN_JS)
    print(f"wrote {GEN_JS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
