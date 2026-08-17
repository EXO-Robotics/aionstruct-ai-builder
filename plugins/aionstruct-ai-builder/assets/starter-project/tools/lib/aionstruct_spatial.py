#!/usr/bin/env python3
"""Reusable spatial analysis for expanded AIONSTRUCT IR.

This module is deliberately downstream of the deterministic v1 expander.  It
does not change blueprint or IR bytes; it provides shared design-quality
analysis for contracts, previews, and tests.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Iterable, Mapping


Point = tuple[int, int, int]
AIR = "minecraft:air"
NON_SUPPORTING_BLOCKS = {
    AIR,
    "minecraft:water",
    "minecraft:flowing_water",
    "minecraft:lava",
    "minecraft:flowing_lava",
    "minecraft:lantern",
    "minecraft:iron_bars",
    "minecraft:glass_pane",
}


def cell_map(ir: Mapping[str, Any]) -> dict[Point, dict[str, Any]]:
    return {
        (int(cell["x"]), int(cell["y"]), int(cell["z"])): dict(cell)
        for cell in ir.get("cells", [])
    }


def is_supporting(cell: Mapping[str, Any] | None) -> bool:
    return bool(cell) and cell.get("block") not in NON_SUPPORTING_BLOCKS


def walkable_floor_cells(ir: Mapping[str, Any], headroom: int = 3) -> set[Point]:
    """Return supported explicit-air feet cells with exact authored clearance."""
    if headroom < 2:
        raise ValueError("headroom must be at least two blocks")
    cells = cell_map(ir)
    result: set[Point] = set()
    for (x, y, z), cell in cells.items():
        if cell.get("block") != AIR:
            continue
        if not is_supporting(cells.get((x, y - 1, z))):
            continue
        if all(cells.get((x, y + offset, z), {}).get("block") == AIR for offset in range(headroom)):
            result.add((x, y, z))
    return result


def connected_component(nodes: set[Point], start: Point, max_step: int = 1) -> set[Point]:
    if start not in nodes:
        return set()
    reached = {start}
    queue = deque([start])
    while queue:
        x, y, z = queue.popleft()
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for dy in range(-max_step, max_step + 1):
                nxt = (x + dx, y + dy, z + dz)
                if nxt in nodes and nxt not in reached:
                    reached.add(nxt)
                    queue.append(nxt)
    return reached


def connected_components(nodes: Iterable[Point], max_step: int = 1) -> list[set[Point]]:
    remaining = set(nodes)
    result: list[set[Point]] = []
    while remaining:
        start = min(remaining)
        group = connected_component(remaining, start, max_step=max_step)
        remaining.difference_update(group)
        result.append(group)
    return sorted(result, key=lambda group: (-len(group), min(group)))


def point_in_bounds(point: Point, bounds: list[list[int]]) -> bool:
    low, high = bounds
    return all(int(low[axis]) <= point[axis] <= int(high[axis]) for axis in range(3))


def cells_in_bounds(nodes: Iterable[Point], bounds: list[list[int]]) -> set[Point]:
    return {point for point in nodes if point_in_bounds(point, bounds)}


def manhattan(a: Point, b: Point) -> int:
    return sum(abs(a[index] - b[index]) for index in range(3))
