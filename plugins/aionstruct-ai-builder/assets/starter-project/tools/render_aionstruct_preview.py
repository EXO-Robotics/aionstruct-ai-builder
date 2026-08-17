#!/usr/bin/env python3
"""Render deterministic, dependency-free previews from expanded AIONSTRUCT IR.

The previewer is deliberately downstream of the authoritative expander.  It
accepts either a validated ``*.aionstruct.json`` blueprint (which it expands in
memory) or an existing ``*.ir.json`` file.  It never writes compiler products;
its only outputs are review evidence: exact metrics and SVG views.

Cell terminology follows the IR contract:

* occupied: an authored cell whose block is not ``minecraft:air``;
* air: an explicitly authored ``minecraft:air`` cell;
* void: a coordinate absent from expanded IR.  Untouched coordinates and
  coordinates cleared with the reserved ``void`` token are intentionally
  indistinguishable after expansion.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from aionstruct_expand import expand
from aionstruct_validate import load_blueprint_json, validate_blueprint


ROOT = Path(__file__).resolve().parents[1]
AIR_BLOCK = "minecraft:air"
AIR_COLOR = "#d7eef7"
VOID_BLOCK = "aionstruct:void"
METRICS_SCHEMA = "aionstruct.preview.metrics.v1"
MANIFEST_SCHEMA = "aionstruct.preview.manifest.v1"
PREVIEWER_VERSION = 2


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _compact_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _require_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    return value


def validate_expanded_ir(ir: Any) -> dict[str, Any]:
    """Fail closed on malformed or semantically inconsistent expanded IR."""
    if not isinstance(ir, dict):
        raise ValueError("expanded IR root must be an object")
    if ir.get("schema") != "aionstruct.ir.v1":
        raise ValueError(f"unsupported expanded IR schema {ir.get('schema')!r}")

    size = ir.get("size")
    if not isinstance(size, list) or len(size) != 3:
        raise ValueError("expanded IR size must be a three-integer list")
    dimensions = [_require_int(value, f"size[{index}]") for index, value in enumerate(size)]
    if any(value <= 0 for value in dimensions):
        raise ValueError("expanded IR dimensions must be positive")

    origin = ir.get("origin", [0, 0, 0])
    if not isinstance(origin, list) or len(origin) != 3:
        raise ValueError("expanded IR origin must be a three-integer list")
    for index, value in enumerate(origin):
        _require_int(value, f"origin[{index}]")

    cells = ir.get("cells")
    if not isinstance(cells, list):
        raise ValueError("expanded IR cells must be a list")
    seen: set[tuple[int, int, int]] = set()
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            raise ValueError(f"cells[{index}] must be an object")
        try:
            x = _require_int(cell["x"], f"cells[{index}].x")
            y = _require_int(cell["y"], f"cells[{index}].y")
            z = _require_int(cell["z"], f"cells[{index}].z")
            block = cell["block"]
        except KeyError as exc:
            raise ValueError(f"cells[{index}] is missing {exc.args[0]!r}") from exc
        if not isinstance(block, str) or ":" not in block:
            raise ValueError(f"cells[{index}].block must be a namespaced identifier")
        if block == VOID_BLOCK:
            raise ValueError("reserved void cells must be absent from expanded IR")
        if not (0 <= x < dimensions[0] and 0 <= y < dimensions[1] and 0 <= z < dimensions[2]):
            raise ValueError(f"cells[{index}] coordinate {(x, y, z)} is outside size {dimensions}")
        position = (x, y, z)
        if position in seen:
            raise ValueError(f"duplicate expanded IR cell at {position}")
        seen.add(position)

        states = cell.get("states")
        if states is not None:
            if not isinstance(states, dict):
                raise ValueError(f"cells[{index}].states must be an object")
            for key, value in states.items():
                if not isinstance(key, str) or not isinstance(value, (str, int, bool)) or isinstance(value, float):
                    raise ValueError(f"cells[{index}].states must contain typed scalar values")
        if "version" in cell:
            _require_int(cell["version"], f"cells[{index}].version")

    if "block_count" in ir and _require_int(ir["block_count"], "block_count") != len(cells):
        raise ValueError(f"block_count={ir['block_count']} does not match cells={len(cells)}")
    return ir


def load_expanded_ir(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load a blueprint/IR and return validated expanded IR plus source evidence."""
    source = load_blueprint_json(path)
    schema = source.get("schema") if isinstance(source, dict) else None
    source_bytes = path.read_bytes()
    if schema == "aionstruct.blueprint.v1":
        errors = validate_blueprint(source, path)
        if errors:
            joined = "\n".join(f"- {error}" for error in errors)
            raise ValueError(f"invalid AIONSTRUCT blueprint {path}:\n{joined}")
        ir = expand(source)
        source_kind = "aionstruct_blueprint"
    elif schema == "aionstruct.ir.v1":
        ir = source
        source_kind = "expanded_ir"
    else:
        raise ValueError(f"unsupported input schema {schema!r}")
    validate_expanded_ir(ir)
    try:
        portable_path = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        # Do not make otherwise identical evidence checkout- or temp-root-specific.
        portable_path = path.name
    evidence = {
        "kind": source_kind,
        "path": portable_path,
        "sha256": _sha256(source_bytes),
        "expanded_ir_sha256": _sha256(_json_bytes(ir)),
    }
    return ir, evidence


def _permutation(cell: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"block": cell["block"]}
    if cell.get("states"):
        result["states"] = {key: cell["states"][key] for key in sorted(cell["states"])}
    if "version" in cell:
        result["version"] = cell["version"]
    return result


def _bbox(cells: Iterable[Mapping[str, Any]]) -> dict[str, list[int]] | None:
    points = [(int(cell["x"]), int(cell["y"]), int(cell["z"])) for cell in cells]
    if not points:
        return None
    minimum = [min(point[axis] for point in points) for axis in range(3)]
    maximum = [max(point[axis] for point in points) for axis in range(3)]
    return {
        "min": minimum,
        "max": maximum,
        "size": [maximum[axis] - minimum[axis] + 1 for axis in range(3)],
    }


def compute_metrics(ir: dict[str, Any], source: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compute exact, stable metrics from the expanded IR cell set."""
    validate_expanded_ir(ir)
    sx, sy, sz = ir["size"]
    cells = list(ir["cells"])
    occupied_cells = [cell for cell in cells if cell["block"] != AIR_BLOCK]
    air_cells = [cell for cell in cells if cell["block"] == AIR_BLOCK]
    volume = sx * sy * sz

    permutation_counts: Counter[str] = Counter()
    permutations: dict[str, dict[str, Any]] = {}
    block_counts: Counter[str] = Counter()
    for cell in cells:
        permutation = _permutation(cell)
        key = _compact_json(permutation)
        permutation_counts[key] += 1
        permutations[key] = permutation
        block_counts[cell["block"]] += 1

    palette = []
    for key in sorted(permutation_counts):
        entry = dict(permutations[key])
        entry["count"] = permutation_counts[key]
        entry["classification"] = "air" if entry["block"] == AIR_BLOCK else "occupied"
        palette.append(entry)

    occupied_by_y: Counter[int] = Counter(int(cell["y"]) for cell in occupied_cells)
    air_by_y: Counter[int] = Counter(int(cell["y"]) for cell in air_cells)
    per_layer = []
    layer_capacity = sx * sz
    for y in range(sy):
        occupied = occupied_by_y[y]
        air = air_by_y[y]
        per_layer.append(
            {
                "y": y,
                "y_relative_to_origin": y - ir.get("origin", [0, 0, 0])[1],
                "occupied": occupied,
                "air": air,
                "void": layer_capacity - occupied - air,
                "authored": occupied + air,
                "capacity": layer_capacity,
            }
        )

    occupied_bbox = _bbox(occupied_cells)
    authored_bbox = _bbox(cells)
    origin = list(ir.get("origin", [0, 0, 0]))

    def relative_bbox(value: dict[str, list[int]] | None) -> dict[str, list[int]] | None:
        if value is None:
            return None
        return {
            "min": [value["min"][i] - origin[i] for i in range(3)],
            "max": [value["max"][i] - origin[i] for i in range(3)],
            "size": list(value["size"]),
        }

    result: dict[str, Any] = {
        "schema": METRICS_SCHEMA,
        "structure": {
            "id": ir.get("id"),
            "short_name": ir.get("short_name"),
            "size": list(ir["size"]),
            "origin": origin,
            "source_sha256": ir.get("source_sha256"),
        },
        "classification_contract": {
            "occupied": "expanded IR cells whose block is not minecraft:air",
            "air": "expanded IR cells explicitly authored as minecraft:air",
            "void": "coordinates absent from expanded IR; untouched and explicitly cleared coordinates are indistinguishable",
        },
        "counts": {
            "capacity": volume,
            "occupied": len(occupied_cells),
            "air": len(air_cells),
            "void": volume - len(cells),
            "authored": len(cells),
            "palette_permutations": len(palette),
            "block_identifiers": len(block_counts),
        },
        "bbox": occupied_bbox,
        "bounding_boxes": {
            "occupied_local": occupied_bbox,
            "authored_local": authored_bbox,
            "occupied_relative_to_origin": relative_bbox(occupied_bbox),
            "authored_relative_to_origin": relative_bbox(authored_bbox),
        },
        "palette": palette,
        "block_counts": [
            {"block": block, "count": block_counts[block]} for block in sorted(block_counts)
        ],
        "per_layer": per_layer,
        "anchors": sorted(ir.get("anchors") or [], key=lambda item: (item.get("name", ""), _compact_json(item))),
        "connectors": sorted(ir.get("connectors") or [], key=lambda item: (item.get("id", ""), _compact_json(item))),
    }
    if source is not None:
        result["input"] = source
    return result


_COLOR_RULES: tuple[tuple[str, str], ...] = (
    ("water", "#2f73b8"),
    ("lava", "#de5b28"),
    ("mossy_stone_brick", "#66735f"),
    ("cracked_stone_brick", "#777a76"),
    ("moss", "#607a4c"),
    ("stone_brick", "#8b8e89"),
    ("cobblestone", "#737a78"),
    ("deepslate", "#414748"),
    ("blackstone", "#353638"),
    ("stone", "#868b8b"),
    ("brick", "#98594d"),
    ("iron_bars", "#3f4850"),
    ("iron", "#aeb8bd"),
    ("chain", "#444c52"),
    ("glass", "#9ecbd1"),
    ("spruce", "#62462f"),
    ("dark_oak", "#493425"),
    ("oak", "#9b7644"),
    ("wood", "#755337"),
    ("planks", "#8b6740"),
    ("wool", "#b7a98d"),
    ("hay", "#b29a45"),
    ("grass", "#638254"),
    ("dirt", "#79563d"),
    ("sand", "#c8ba83"),
    ("gravel", "#7a7771"),
    ("torch", "#e4a942"),
    ("lantern", "#dda744"),
)


def block_color(block: str) -> str:
    if block == AIR_BLOCK:
        return AIR_COLOR
    lowered = block.lower()
    for needle, color in _COLOR_RULES:
        if needle in lowered:
            return color
    digest = hashlib.sha256(block.encode("utf-8")).digest()
    hue = int.from_bytes(digest[:2], "big") % 360
    saturation = 28 + digest[2] % 24
    lightness = 39 + digest[3] % 21
    return f"hsl({hue},{saturation}%,{lightness}%)"


def _svg_open(width: int, height: int, title: str, description: str) -> list[str]:
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f"<title>{_escape(title)}</title>",
        f"<desc>{_escape(description)}</desc>",
        '<rect width="100%" height="100%" fill="#f3f0e8"/>',
        '<g font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" fill="#182028">',
    ]


def _svg_close(lines: list[str]) -> str:
    lines.extend(["</g>", "</svg>"])
    return "\n".join(lines) + "\n"


def _runs(points: Mapping[tuple[int, int], str]) -> list[tuple[int, int, int, str]]:
    """Return deterministic horizontal ``(start, end, row, fill)`` runs."""
    rows: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for (column, row), fill in points.items():
        rows[row].append((column, fill))
    result: list[tuple[int, int, int, str]] = []
    for row in sorted(rows):
        values = sorted(rows[row])
        start, previous, fill = values[0][0], values[0][0], values[0][1]
        for column, next_fill in values[1:]:
            if column == previous + 1 and next_fill == fill:
                previous = column
                continue
            result.append((start, previous, row, fill))
            start = previous = column
            fill = next_fill
        result.append((start, previous, row, fill))
    return result


def _draw_runs(
    lines: list[str],
    points: Mapping[tuple[int, int], str],
    left: int,
    top: int,
    scale: int,
) -> None:
    for start, end, row, fill in _runs(points):
        width = (end - start + 1) * scale
        lines.append(
            f'<rect x="{left + start * scale}" y="{top + row * scale}" '
            f'width="{width}" height="{scale}" fill="{_escape(fill)}"/>'
        )


def _grid(lines: list[str], left: int, top: int, columns: int, rows: int, scale: int) -> None:
    width, height = columns * scale, rows * scale
    lines.append(
        f'<rect x="{left}" y="{top}" width="{width}" height="{height}" fill="none" stroke="#343a40" stroke-width="1"/>'
    )
    stride = 8 if max(columns, rows) <= 80 else 16
    for column in range(stride, columns, stride):
        x = left + column * scale
        lines.append(f'<path d="M{x} {top}V{top + height}" stroke="#1f2937" stroke-opacity="0.13"/>')
    for row in range(stride, rows, stride):
        y = top + row * scale
        lines.append(f'<path d="M{left} {y}H{left + width}" stroke="#1f2937" stroke-opacity="0.13"/>')


def render_top_down_svg(ir: dict[str, Any], metrics: dict[str, Any]) -> str:
    sx, _sy, sz = ir["size"]
    scale = max(3, min(9, 900 // max(sx, sz)))
    left, top = 64, 88
    map_width, map_height = sx * scale, sz * scale
    palette = metrics["block_counts"]
    legend_width = 390
    legend_x = left + map_width + 28
    structure_id = str(ir.get("id"))
    summary_text = (
        f'TOP DOWN · size {sx}×{ir["size"][1]}×{sz} · occupied {metrics["counts"]["occupied"]:,} · '
        f'air {metrics["counts"]["air"]:,} · void {metrics["counts"]["void"]:,}'
    )
    width = max(
        legend_x + legend_width + 28,
        left + len(structure_id) * 14 + 28,
        left + len(summary_text) * 8 + 28,
    )
    height = max(top + map_height + 58, top + 70 + len(palette) * 19)
    lines = _svg_open(
        width,
        height,
        f"{ir.get('short_name', 'structure')} top-down preview",
        "Highest occupied cell at each X/Z coordinate; explicit air is omitted from the roof projection.",
    )
    lines.append(f'<text x="{left}" y="35" font-size="22" font-weight="700">{_escape(structure_id)}</text>')
    lines.append(f'<text x="{left}" y="61" font-size="13">{_escape(summary_text)}</text>')

    highest: dict[tuple[int, int], Mapping[str, Any]] = {}
    for cell in sorted(ir["cells"], key=lambda item: (item["y"], item["z"], item["x"])):
        if cell["block"] != AIR_BLOCK:
            highest[(cell["x"], cell["z"])] = cell
    points = {(x, z): block_color(cell["block"]) for (x, z), cell in highest.items()}
    _draw_runs(lines, points, left, top, scale)
    _grid(lines, left, top, sx, sz, scale)

    origin = ir.get("origin", [0, 0, 0])
    ox, oz = origin[0], origin[2]
    if 0 <= ox < sx and 0 <= oz < sz:
        cx, cy = left + (ox + 0.5) * scale, top + (oz + 0.5) * scale
        lines.append(f'<circle cx="{cx}" cy="{cy}" r="{max(3, scale * 0.48)}" fill="none" stroke="#e11d48" stroke-width="2"/>')

    for anchor in metrics["anchors"]:
        local = anchor.get("local")
        if not isinstance(local, list) or len(local) != 3:
            continue
        x, _y, z = local
        cx, cy = left + (x + 0.5) * scale, top + (z + 0.5) * scale
        lines.append(f'<circle cx="{cx}" cy="{cy}" r="{max(2, scale * 0.32)}" fill="#ffe66d" stroke="#111827"/>')
        lines.append(f'<text x="{cx + 5}" y="{cy - 5}" font-size="10">{_escape(anchor.get("name", "anchor"))}</text>')

    lines.append(f'<text x="{left}" y="{top - 10}" font-size="12" font-weight="700">NORTH</text>')
    lines.append(f'<text x="{left + map_width / 2}" y="{top + map_height + 30}" text-anchor="middle" font-size="11">X → · Z ↓ · red ring = origin</text>')

    lines.append(f'<text x="{legend_x}" y="{top}" font-size="16" font-weight="700">Expanded palette by block</text>')
    lines.append(f'<text x="{legend_x}" y="{top + 23}" font-size="11">Counts include all authored occupied/air cells.</text>')
    for index, entry in enumerate(palette):
        y = top + 51 + index * 19
        color = AIR_COLOR if entry["block"] == AIR_BLOCK else block_color(entry["block"])
        lines.append(f'<rect x="{legend_x}" y="{y - 11}" width="13" height="13" fill="{_escape(color)}" stroke="#475569" stroke-width="0.5"/>')
        lines.append(
            f'<text x="{legend_x + 20}" y="{y}" font-size="11">{_escape(entry["block"])}  × {entry["count"]:,}</text>'
        )
    return _svg_close(lines)


def render_floor_sheet_svg(ir: dict[str, Any], metrics: dict[str, Any]) -> str:
    sx, sy, sz = ir["size"]
    active_layers = [layer["y"] for layer in metrics["per_layer"] if layer["authored"]]
    if not active_layers:
        active_layers = [0]
    scale = max(2, min(5, 420 // max(sx, sz)))
    panel_width, panel_height = sx * scale, sz * scale
    gap_x, gap_y = 34, 56
    columns = max(1, min(4, 1480 // (panel_width + gap_x)))
    rows = math.ceil(len(active_layers) / columns)
    left, top = 52, 92
    width = left * 2 + columns * panel_width + (columns - 1) * gap_x
    height = top + rows * panel_height + (rows - 1) * gap_y + 52
    lines = _svg_open(
        width,
        height,
        f"{ir.get('short_name', 'structure')} floor sheet",
        "One X/Z plan for every authored Y layer. Pale-blue cells are explicit air; blank cells are void.",
    )
    lines.append(f'<text x="{left}" y="34" font-size="22" font-weight="700">{_escape(ir.get("id"))} · FLOOR SHEET</text>')
    lines.append(
        f'<text x="{left}" y="60" font-size="12">{len(active_layers)} authored layers of {sy} total · '
        'solid = occupied · pale blue = explicit air · blank = void</text>'
    )
    cells_by_y: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for cell in ir["cells"]:
        cells_by_y[cell["y"]].append(cell)
    layer_metrics = {layer["y"]: layer for layer in metrics["per_layer"]}

    for index, y in enumerate(active_layers):
        column, row = index % columns, index // columns
        panel_left = left + column * (panel_width + gap_x)
        panel_top = top + row * (panel_height + gap_y)
        summary = layer_metrics[y]
        lines.append(
            f'<text x="{panel_left}" y="{panel_top - 13}" font-size="11" font-weight="700">Y {y} '
            f'(O {summary["occupied"]:,} · A {summary["air"]:,} · V {summary["void"]:,})</text>'
        )
        points: dict[tuple[int, int], str] = {}
        for cell in cells_by_y.get(y, []):
            fill = AIR_COLOR if cell["block"] == AIR_BLOCK else block_color(cell["block"])
            points[(cell["x"], cell["z"])] = fill
        _draw_runs(lines, points, panel_left, panel_top, scale)
        _grid(lines, panel_left, panel_top, sx, sz, scale)
    return _svg_close(lines)


def _projection(ir: dict[str, Any], direction: str) -> tuple[int, int, dict[tuple[int, int], str]]:
    sx, sy, sz = ir["size"]
    occupied = [cell for cell in ir["cells"] if cell["block"] != AIR_BLOCK]
    if direction in ("north", "south"):
        depth_order = (lambda item: item["z"]) if direction == "north" else (lambda item: -item["z"])
        horizontal = lambda item: item["x"]
        width = sx
    else:
        depth_order = (lambda item: item["x"]) if direction == "west" else (lambda item: -item["x"])
        horizontal = lambda item: item["z"] if direction == "west" else sz - 1 - item["z"]
        width = sz
    visible: dict[tuple[int, int], dict[str, Any]] = {}
    for cell in sorted(occupied, key=lambda item: (depth_order(item), item["y"], horizontal(item))):
        key = (horizontal(cell), sy - 1 - cell["y"])
        if key not in visible:
            visible[key] = cell
    return width, sy, {key: block_color(cell["block"]) for key, cell in visible.items()}


def render_silhouettes_svg(ir: dict[str, Any], metrics: dict[str, Any]) -> str:
    del metrics
    projections = [(direction, *_projection(ir, direction)) for direction in ("north", "south", "west", "east")]
    max_width = max(item[1] for item in projections)
    sy = ir["size"][1]
    scale = max(3, min(8, 780 // max(max_width, sy)))
    gap_x, gap_y = 62, 64
    panel_width, panel_height = max_width * scale, sy * scale
    left, top = 56, 92
    width = left * 2 + panel_width * 2 + gap_x
    height = top + panel_height * 2 + gap_y + 52
    lines = _svg_open(
        width,
        height,
        f"{ir.get('short_name', 'structure')} silhouettes",
        "Nearest occupied cell projection from north, south, west, and east; explicit air is omitted.",
    )
    lines.append(f'<text x="{left}" y="34" font-size="22" font-weight="700">{_escape(ir.get("id"))} · SILHOUETTES</text>')
    lines.append('<text x="56" y="60" font-size="12">Nearest occupied surface from each cardinal direction · Y increases upward</text>')
    for index, (direction, projection_width, projection_height, points) in enumerate(projections):
        column, row = index % 2, index // 2
        panel_left = left + column * (panel_width + gap_x)
        panel_top = top + row * (panel_height + gap_y)
        lines.append(f'<text x="{panel_left}" y="{panel_top - 13}" font-size="12" font-weight="700">VIEW FROM {direction.upper()}</text>')
        _draw_runs(lines, points, panel_left, panel_top, scale)
        _grid(lines, panel_left, panel_top, projection_width, projection_height, scale)
    return _svg_close(lines)


def write_preview(ir: dict[str, Any], output_dir: Path, source: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write one deterministic preview evidence set and return its manifest."""
    validate_expanded_ir(ir)
    metrics = compute_metrics(ir, source)
    artifacts: dict[str, bytes] = {
        "metrics.json": _json_bytes(metrics),
        "top_down.svg": render_top_down_svg(ir, metrics).encode("utf-8"),
        "floors.svg": render_floor_sheet_svg(ir, metrics).encode("utf-8"),
        "silhouettes.svg": render_silhouettes_svg(ir, metrics).encode("utf-8"),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in sorted(artifacts):
        (output_dir / name).write_bytes(artifacts[name])

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "generator": {
            "name": "render_aionstruct_preview.py",
            "version": PREVIEWER_VERSION,
            "sha256": _sha256(Path(__file__).read_bytes()),
        },
        "structure_id": ir.get("id"),
        "short_name": ir.get("short_name"),
        "input": source,
        "artifacts": [
            {"path": name, "sha256": _sha256(artifacts[name]), "bytes": len(artifacts[name])}
            for name in sorted(artifacts)
        ],
    }
    (output_dir / "preview_manifest.json").write_bytes(_json_bytes(manifest))
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render deterministic SVG previews and exact metrics from AIONSTRUCT blueprint/IR"
    )
    parser.add_argument("input", type=Path, help="validated .aionstruct.json blueprint or expanded .ir.json")
    parser.add_argument("--output-dir", required=True, type=Path, help="preview evidence directory")
    parser.add_argument("--check", action="store_true", help="fail if the output directory is stale; do not rewrite it")
    args = parser.parse_args(argv)
    try:
        ir, source = load_expanded_ir(args.input.resolve())
        output_dir = args.output_dir.resolve()
        if args.check:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp = Path(temp_dir)
                manifest = write_preview(ir, temp, source)
                expected = {path.name: path.read_bytes() for path in temp.iterdir()}
            actual_names = {path.name for path in output_dir.iterdir()} if output_dir.exists() else set()
            if actual_names != set(expected) or any((output_dir / name).read_bytes() != data for name, data in expected.items()):
                print(f"STALE {output_dir}", file=sys.stderr)
                return 1
        else:
            manifest = write_preview(ir, output_dir, source)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"{'checked' if args.check else 'previewed'} {manifest['structure_id']} -> {args.output_dir} "
        f"artifacts={len(manifest['artifacts'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
