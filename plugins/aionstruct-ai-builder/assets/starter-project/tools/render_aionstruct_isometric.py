#!/usr/bin/env python3
"""Render deterministic isometric engineering boards from expanded AIONSTRUCT IR."""
from __future__ import annotations

import argparse
import colorsys
import hashlib
import io
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable

import PIL
from PIL import Image, ImageColor, ImageDraw, ImageFont

from render_aionstruct_preview import AIR_BLOCK, block_color, load_expanded_ir


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "aionstruct.isometric_manifest.v1"
RENDERER_VERSION = 1
BACKGROUND = "#e9e5dc"
INK = "#20272c"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def rgb(value: str) -> tuple[int, int, int]:
    if value.startswith("hsl("):
        h, s, light = value[4:-1].replace("%", "").split(",")
        red, green, blue = colorsys.hls_to_rgb(float(h) / 360.0, float(light) / 100.0, float(s) / 100.0)
        return round(red * 255), round(green * 255), round(blue * 255)
    return ImageColor.getrgb(value)


def shade(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, round(channel * factor))) for channel in color)


def rotate_point(x: int, z: int, size_x: int, size_z: int, turns: int) -> tuple[int, int, int, int]:
    turns %= 4
    if turns == 0:
        return x, z, size_x, size_z
    if turns == 1:
        return size_z - 1 - z, x, size_z, size_x
    if turns == 2:
        return size_x - 1 - x, size_z - 1 - z, size_x, size_z
    return z, size_x - 1 - x, size_z, size_x


def panel_cells(ir: dict[str, Any], *, turns: int, max_y: int | None) -> tuple[dict[tuple[int, int, int], dict[str, Any]], tuple[int, int, int]]:
    size_x, size_y, size_z = ir["size"]
    cells: dict[tuple[int, int, int], dict[str, Any]] = {}
    rotated_size_x, rotated_size_z = size_x, size_z
    for cell in ir["cells"]:
        if cell["block"] == AIR_BLOCK or (max_y is not None and int(cell["y"]) > max_y):
            continue
        x, z, rotated_size_x, rotated_size_z = rotate_point(int(cell["x"]), int(cell["z"]), size_x, size_z, turns)
        cells[(x, int(cell["y"]), z)] = cell
    return cells, (rotated_size_x, size_y, rotated_size_z)


def render_panel(
    ir: dict[str, Any], *, title: str, turns: int, max_y: int | None,
    tile_width: int = 10, tile_height: int = 5, block_height: int = 7,
) -> Image.Image:
    cells, (size_x, _, size_z) = panel_cells(ir, turns=turns, max_y=max_y)

    def project(x: float, y: float, z: float) -> tuple[float, float]:
        return (x - z) * tile_width / 2.0, (x + z) * tile_height / 2.0 - y * block_height

    vertices = [project(x, y, z) for x in (0, size_x) for z in (0, size_z) for y in (0, max((p[1] for p in cells), default=0) + 2)]
    min_x = math.floor(min(point[0] for point in vertices))
    max_x = math.ceil(max(point[0] for point in vertices))
    min_y = math.floor(min(point[1] for point in vertices))
    max_y_screen = math.ceil(max(point[1] for point in vertices))
    margin_x, margin_top, margin_bottom = 28, 54, 34
    width = max_x - min_x + margin_x * 2
    height = max_y_screen - min_y + margin_top + margin_bottom
    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    offset_x = margin_x - min_x
    offset_y = margin_top - min_y

    def points(values: Iterable[tuple[float, float]]) -> list[tuple[int, int]]:
        return [(round(x + offset_x), round(y + offset_y)) for x, y in values]

    # Interior cubes cannot contribute a visible face from this camera.  Drop
    # them before polygon construction; this keeps landmark-scale boards fast.
    visible_cells = [
        (position, cell)
        for position, cell in cells.items()
        if (
            (position[0] + 1, position[1], position[2]) not in cells
            or (position[0], position[1], position[2] + 1) not in cells
            or (position[0], position[1] + 1, position[2]) not in cells
        )
    ]
    color_cache: dict[str, tuple[int, int, int]] = {}
    # Far-to-near painter order in rotated coordinates; lower cubes draw first.
    for (x, y, z), cell in sorted(visible_cells, key=lambda item: (item[0][0] + item[0][2], item[0][1], item[0][0])):
        block = cell["block"]
        if block not in color_cache:
            color_cache[block] = rgb(block_color(block))
        base = color_cache[block]
        top = points((project(x, y + 1, z), project(x + 1, y + 1, z), project(x + 1, y + 1, z + 1), project(x, y + 1, z + 1)))
        right = points((project(x + 1, y, z), project(x + 1, y + 1, z), project(x + 1, y + 1, z + 1), project(x + 1, y, z + 1)))
        left = points((project(x, y, z + 1), project(x + 1, y, z + 1), project(x + 1, y + 1, z + 1), project(x, y + 1, z + 1)))
        if (x + 1, y, z) not in cells:
            draw.polygon(right, fill=shade(base, 0.72))
        if (x, y, z + 1) not in cells:
            draw.polygon(left, fill=shade(base, 0.57))
        if (x, y + 1, z) not in cells:
            draw.polygon(top, fill=shade(base, 1.08), outline=shade(base, 0.48))

    font = ImageFont.load_default(size=15)
    small = ImageFont.load_default(size=11)
    draw.text((16, 14), title, fill=INK, font=font)
    subtitle = f"rotation={turns * 90}° · {'exterior' if max_y is None else f'cut at local Y≤{max_y}'} · occupied={len(cells):,} · surface={len(visible_cells):,}"
    draw.text((16, 34), subtitle, fill="#4a5359", font=small)
    return image


def render_board(ir: dict[str, Any]) -> Image.Image:
    panels = [
        render_panel(ir, title="Exterior · southwest engineering view", turns=0, max_y=None),
        render_panel(ir, title="Exterior · northeast engineering view", turns=2, max_y=None),
        render_panel(ir, title="Ground program cutaway", turns=0, max_y=12),
        render_panel(ir, title="Upper program cutaway", turns=2, max_y=24),
    ]
    panel_width = max(image.width for image in panels)
    panel_height = max(image.height for image in panels)
    gutter = 20
    header = 78
    board = Image.new("RGB", (panel_width * 2 + gutter * 3, panel_height * 2 + gutter * 3 + header), "#d6d0c5")
    draw = ImageDraw.Draw(board)
    title_font = ImageFont.load_default(size=24)
    subtitle_font = ImageFont.load_default(size=13)
    draw.text((gutter, 14), f"{ir.get('id')} · 3D ENGINEERING BOARD", fill=INK, font=title_font)
    draw.text((gutter, 48), "Exact expanded IR · exterior massing plus two non-shipping inspection cutaways", fill="#4a5359", font=subtitle_font)
    for index, panel in enumerate(panels):
        x = gutter + (index % 2) * (panel_width + gutter)
        y = header + gutter + (index // 2) * (panel_height + gutter)
        board.paste(panel, (x, y))
    return board


def image_bytes(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        ir, source = load_expanded_ir(args.input.resolve())
        data = image_bytes(render_board(ir))
        manifest_path = args.manifest or args.output.with_suffix(".manifest.json")
        manifest = {
            "schema": SCHEMA,
            "renderer": {
                "name": Path(__file__).name,
                "version": RENDERER_VERSION,
                "sha256": sha256(Path(__file__).read_bytes()),
                "pillow_version": PIL.__version__,
            },
            "structure_id": ir.get("id"),
            "size": ir["size"],
            "input": source,
            "artifact": {"path": args.output.name, "bytes": len(data), "sha256": sha256(data)},
            "views": [
                {"rotation": 0, "mode": "exterior"},
                {"rotation": 180, "mode": "exterior"},
                {"rotation": 0, "mode": "cutaway", "maximum_local_y": 12},
                {"rotation": 180, "mode": "cutaway", "maximum_local_y": 24},
            ],
            "proof_boundary": ["expanded_ir_engineering_visualization", "not_client_render_or_runtime_light_proof"],
        }
        manifest_data = json_bytes(manifest)
        if args.check:
            if not args.output.exists() or args.output.read_bytes() != data or not manifest_path.exists() or manifest_path.read_bytes() != manifest_data:
                print("STALE isometric engineering board", file=sys.stderr)
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
