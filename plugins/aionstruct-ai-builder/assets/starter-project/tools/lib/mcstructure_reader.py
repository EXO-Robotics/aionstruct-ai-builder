"""Independent little-endian NBT reader for on-disk ``.mcstructure`` checks.

This module intentionally imports nothing from ``mcstructure_le``.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import Any


@dataclass(frozen=True)
class _Tagged:
    tag: int
    value: Any


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def take(self, length: int) -> bytes:
        if length < 0:
            raise ValueError("negative NBT length")
        value = self.data[self.offset:self.offset + length]
        if len(value) != length:
            raise ValueError("truncated little-endian NBT")
        self.offset += length
        return value

    def unpack(self, fmt: str) -> Any:
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, self.take(size))[0]

    def string(self) -> str:
        length = self.unpack("<H")
        return self.take(length).decode("utf-8")

    def count(self) -> int:
        value = self.unpack("<i")
        if value < 0:
            raise ValueError("negative NBT collection length")
        return value

    def payload(self, tag: int) -> _Tagged:
        if tag == 1:
            value = self.unpack("<b")
        elif tag == 2:
            value = self.unpack("<h")
        elif tag == 3:
            value = self.unpack("<i")
        elif tag == 4:
            value = self.unpack("<q")
        elif tag == 5:
            value = self.unpack("<f")
        elif tag == 6:
            value = self.unpack("<d")
        elif tag == 7:
            value = list(self.take(self.count()))
        elif tag == 8:
            value = self.string()
        elif tag == 9:
            subtype, count = self.unpack("<B"), self.count()
            value = [self.payload(subtype) for _ in range(count)]
        elif tag == 10:
            value = {}
            while True:
                subtype = self.unpack("<B")
                if subtype == 0:
                    break
                name = self.string()
                if name in value:
                    raise ValueError(f"duplicate NBT compound key {name!r}")
                value[name] = self.payload(subtype)
        elif tag == 11:
            value = [self.unpack("<i") for _ in range(self.count())]
        elif tag == 12:
            value = [self.unpack("<q") for _ in range(self.count())]
        else:
            raise ValueError(f"unsupported NBT tag {tag}")
        return _Tagged(tag, value)

    def root(self) -> _Tagged:
        if self.unpack("<B") != 10 or self.string() != "":
            raise ValueError("expected unnamed root compound")
        result = self.payload(10)
        if self.offset != len(self.data):
            raise ValueError("trailing bytes after NBT root")
        return result


def _plain(value: _Tagged) -> Any:
    if value.tag == 9:
        return [_plain(item) for item in value.value]
    if value.tag == 10:
        return {name: _plain(item) for name, item in value.value.items()}
    return value.value


def _compound(value: _Tagged, context: str) -> dict[str, _Tagged]:
    if value.tag != 10:
        raise ValueError(f"{context} must be a compound")
    return value.value


def _list(value: _Tagged, context: str) -> list[_Tagged]:
    if value.tag != 9:
        raise ValueError(f"{context} must be a list")
    return value.value


def _state_value(value: _Tagged, name: str) -> tuple[str, bool | int | str]:
    if value.tag == 1:
        if value.value not in (0, 1):
            raise ValueError(f"boolean block state {name!r} has byte value {value.value}")
        return "bool", bool(value.value)
    if value.tag == 3:
        return "int", value.value
    if value.tag == 8:
        return "string", value.value
    raise ValueError(f"block state {name!r} has unsupported NBT tag {value.tag}")


def _layer_cell(index: int, palette: list[dict[str, Any]]) -> dict[str, Any]:
    if index == -1:
        return {"classification": "void", "palette_index": -1}
    if not 0 <= index < len(palette):
        raise ValueError(f"block index {index} is outside palette")
    permutation = palette[index]
    classification = "air" if permutation["name"] == "minecraft:air" else "block"
    return {
        "classification": classification,
        "palette_index": index,
        "permutation": permutation,
    }


def decode_mcstructure_file(path: str | Path) -> dict[str, Any]:
    """Read and independently normalize an emitted file from disk."""
    source = Path(path)
    tagged_root = _Reader(source.read_bytes()).root()
    root = _compound(tagged_root, "root")

    required = {"format_version", "size", "structure_world_origin", "structure"}
    missing = required - root.keys()
    if missing:
        raise ValueError(f"mcstructure missing root fields: {sorted(missing)}")
    size = [_plain(item) for item in _list(root["size"], "size")]
    origin = [_plain(item) for item in _list(root["structure_world_origin"], "structure_world_origin")]
    if len(size) != 3 or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in size):
        raise ValueError(f"invalid structure size {size!r}")
    if len(origin) != 3 or any(isinstance(v, bool) or not isinstance(v, int) for v in origin):
        raise ValueError(f"invalid structure origin {origin!r}")

    structure = _compound(root["structure"], "structure")
    layers_tagged = _list(structure["block_indices"], "block_indices")
    if len(layers_tagged) != 2:
        raise ValueError("block_indices must have exactly two layers")
    layers = [[_plain(item) for item in _list(layer, "block_indices layer")] for layer in layers_tagged]

    palette_compound = _compound(structure["palette"], "palette")
    default = _compound(palette_compound["default"], "palette.default")
    palette: list[dict[str, Any]] = []
    for index, entry_tag in enumerate(_list(default["block_palette"], "block_palette")):
        entry = _compound(entry_tag, f"block_palette[{index}]")
        states_tagged = _compound(entry["states"], f"block_palette[{index}].states")
        states: dict[str, bool | int | str] = {}
        state_types: dict[str, str] = {}
        for name in sorted(states_tagged):
            kind, value = _state_value(states_tagged[name], name)
            states[name] = value
            state_types[name] = kind
        palette.append({
            "name": _plain(entry["name"]),
            "states": states,
            "state_types": state_types,
            "version": _plain(entry["version"]),
        })

    volume = size[0] * size[1] * size[2]
    if any(len(layer) != volume for layer in layers):
        raise ValueError(f"block index layer length does not match volume {volume}")
    cells = []
    _sx, sy, sz = size
    for flat in range(volume):
        x, rem = divmod(flat, sy * sz)
        y, z = divmod(rem, sz)
        cells.append({
            "flat_index": flat,
            "x": x,
            "y": y,
            "z": z,
            "primary": _layer_cell(layers[0][flat], palette),
            "secondary": _layer_cell(layers[1][flat], palette),
        })

    return {
        "path": str(source),
        "format_version": _plain(root["format_version"]),
        "size": size,
        "structure_world_origin": origin,
        "block_indices": layers,
        "palette": palette,
        "entities": _plain(structure["entities"]),
        "block_position_data": _plain(default["block_position_data"]),
        "cells": cells,
        "root": _plain(tagged_root),
    }
