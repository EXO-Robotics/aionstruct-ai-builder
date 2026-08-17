#!/usr/bin/env python3
"""Render selected-floor static light heatmaps from the shared quality model."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import PIL
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from aionstruct_expand import expand  # noqa: E402
from aionstruct_quality import canonical_bytes, estimate_light_field, light_sources, load_contract, sha256  # noqa: E402
from aionstruct_validate import load_blueprint_json, validate_blueprint  # noqa: E402
from lib.aionstruct_spatial import walkable_floor_cells  # noqa: E402


SCHEMA = "aionstruct.lightmap_manifest.v1"
RENDERER_VERSION = 2
MAX_FLOORS = 6


def selected_floors(walkable: set[tuple[int, int, int]], limit: int = MAX_FLOORS) -> tuple[int, ...]:
    """Choose actual occupied walkable bands, favoring substantive floors."""
    counts = Counter(y for _, y, _ in walkable)
    if not counts:
        return ()
    minimum_substantive = max(4, round(max(counts.values()) * 0.05))
    substantive = [y for y, count in counts.items() if count >= minimum_substantive]
    ranked = sorted(substantive, key=lambda y: (-counts[y], y))[:limit]
    return tuple(sorted(ranked))


def level_color(level: int) -> tuple[int, int, int]:
    # 0 is deep violet, threshold 8 is amber, and 15 is pale gold.
    stops = {
        0: (44, 32, 74),
        4: (79, 54, 112),
        7: (156, 82, 98),
        8: (214, 137, 70),
        11: (236, 184, 92),
        15: (255, 235, 158),
    }
    keys = sorted(stops)
    if level <= keys[0]:
        return stops[keys[0]]
    if level >= keys[-1]:
        return stops[keys[-1]]
    for low, high in zip(keys, keys[1:]):
        if low <= level <= high:
            fraction = (level - low) / (high - low)
            return tuple(round(stops[low][i] + (stops[high][i] - stops[low][i]) * fraction) for i in range(3))
    raise AssertionError(level)


def render_lightmap(ir: dict[str, Any], contract: dict[str, Any]) -> Image.Image:
    headroom = int(contract["traversal"]["headroom"])
    walkable = walkable_floor_cells(ir, headroom=headroom)
    field = estimate_light_field(ir, contract, walkable)
    sources = {position for position, _, _ in light_sources(ir, contract)}
    floors = selected_floors(walkable)
    sx, _, sz = ir["size"]
    scale = 6
    panel_width = sx * scale
    panel_height = sz * scale
    gutter = 30
    header = 100
    footer = 54
    board_width = max(panel_width * 3 + gutter * 4, 900)
    board = Image.new("RGB", (board_width, panel_height * 2 + gutter * 3 + header + footer), "#d7d1c6")
    draw = ImageDraw.Draw(board)
    title_font = ImageFont.load_default(size=21)
    label_font = ImageFont.load_default(size=15)
    small = ImageFont.load_default(size=11)
    draw.text((gutter, 14), f"{ir.get('id')} · OPTIMISTIC FLOOR-LIGHT HEATMAP", fill="#20272c", font=title_font)
    draw.text((gutter, 48), "Shared quality model · unobstructed Manhattan ceiling · orange/gold is >=8 · runtime sampling still required", fill="#4a5359", font=label_font)
    minimum = int(contract["lighting"]["minimum_floor_block_light"])
    for index, y in enumerate(floors):
        left = gutter + (index % 3) * (panel_width + gutter)
        top = header + gutter + (index // 3) * (panel_height + gutter)
        draw.rectangle((left, top, left + panel_width, top + panel_height), fill="#292f33")
        floor_points = [(x, z, field[(x, y, z)]) for x, py, z in walkable if py == y]
        for x, z, level in floor_points:
            x0, y0 = left + x * scale, top + z * scale
            draw.rectangle((x0, y0, x0 + scale - 1, y0 + scale - 1), fill=level_color(level))
        for x, sy, z in sources:
            if abs(sy - y) <= 3:
                cx, cy = left + x * scale + scale // 2, top + z * scale + scale // 2
                draw.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill="#ffffff", outline="#111111", width=1)
        counts = Counter(level for _, _, level in floor_points)
        covered = sum(count for level, count in counts.items() if level >= minimum)
        coverage = covered / len(floor_points) if floor_points else 0.0
        draw.text((left, top - 38), f"local Y={y} · walkable={len(floor_points):,}", fill="#20272c", font=label_font)
        draw.text((left, top - 20), f"cells >={minimum}: {coverage:.1%}", fill="#20272c", font=small)
        draw.rectangle((left, top, left + panel_width, top + panel_height), outline="#62686b", width=1)

    legend_y = board.height - footer + 10
    for level in range(16):
        x = gutter + level * 32
        draw.rectangle((x, legend_y, x + 30, legend_y + 16), fill=level_color(level))
        draw.text((x + 10, legend_y + 20), str(level), fill="#20272c", font=small)
    draw.text((gutter + 16 * 32 + 18, legend_y), "white ring = light source within ±3Y", fill="#20272c", font=small)
    return board


def image_bytes(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("blueprint", type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        blueprint = load_blueprint_json(args.blueprint.resolve())
        errors = validate_blueprint(blueprint, args.blueprint.resolve())
        if errors:
            raise ValueError("invalid blueprint: " + " | ".join(errors))
        contract = load_contract(args.contract.resolve())
        ir = expand(blueprint)
        walkable = walkable_floor_cells(ir, headroom=int(contract["traversal"]["headroom"]))
        floors = selected_floors(walkable)
        data = image_bytes(render_lightmap(ir, contract))
        manifest_path = args.output.with_suffix(".manifest.json")
        manifest = {
            "schema": SCHEMA,
            "renderer": {"name": Path(__file__).name, "version": RENDERER_VERSION, "sha256": sha256(Path(__file__).read_bytes()), "pillow_version": PIL.__version__},
            "structure_id": ir.get("id"),
            "input": {"blueprint_sha256": sha256(args.blueprint.read_bytes()), "contract_sha256": sha256(args.contract.read_bytes())},
            "artifact": {"path": args.output.name, "bytes": len(data), "sha256": sha256(data)},
            "selected_local_y": list(floors),
            "proof_boundary": ["optimistic_static_light_estimate", "not_runtime_or_client_light_proof"],
        }
        manifest_data = canonical_bytes(manifest)
        if args.check:
            if not args.output.exists() or args.output.read_bytes() != data or not manifest_path.exists() or manifest_path.read_bytes() != manifest_data:
                print("STALE lightmap", file=sys.stderr)
                return 1
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(data)
            manifest_path.write_bytes(manifest_data)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"{'checked' if args.check else 'rendered'} {args.output} bytes={len(data)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
