#!/usr/bin/env python3
"""Fail-closed validation for AIONSTRUCT blueprint v1.

The JSON Schema is the author-facing shape contract.  This module enforces the
same finite vocabulary plus checks which depend on the blueprint dimensions or
cross-reference other fields.  It intentionally has no third-party runtime
dependency so validation is always available to the offline compiler.
"""
from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Any


SCHEMA_ID = "aionstruct.blueprint.v1"
WORLD_GRAMMAR = "AIONSTRUCT_WORLD_GRAMMAR_V1"
PRODUCTION_STANDARD = "AIONSTRUCT_STRUCTURE_STANDARD_V1"
MAX_DIMENSION = 64
MAX_PALETTE = 256

IDENTIFIER_RE = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")
ALIAS_RE = re.compile(r"^[a-z][a-z0-9_]*$")
NAME_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")
STATE_KEY_RE = re.compile(r"^(?:[a-z0-9_.-]+:)?[a-z][a-z0-9_.-]*$")

OP_FIELDS: dict[str, frozenset[str]] = {
    "cuboid": frozenset({"op", "from", "to", "block", "states", "version", "comment"}),
    "floor": frozenset({"op", "from", "to", "block", "states", "version", "comment"}),
    "wall": frozenset({"op", "from", "to", "block", "states", "version", "comment"}),
    "shell": frozenset(
        {"op", "from", "to", "block", "states", "version", "walls", "floor", "ceiling", "comment"}
    ),
    "pillar": frozenset({"op", "at", "height", "block", "states", "version", "comment"}),
    "set": frozenset({"op", "at", "block", "states", "version", "comment"}),
    "doorway": frozenset(
        {"op", "face", "wall_z", "center_x", "wall_x", "center_z", "y", "width", "height", "fill", "comment"}
    ),
    "window": frozenset(
        {"op", "face", "wall_z", "center_x", "wall_x", "center_z", "y", "width", "height", "fill", "comment"}
    ),
    "roof_gable": frozenset(
        {"op", "from", "to", "axis", "block", "fill_gable", "states", "version", "comment"}
    ),
    "stair": frozenset(
        {"op", "at", "steps", "facing", "block", "states", "version", "comment"}
    ),
    "arch": frozenset(
        {
            "op", "face", "wall_z", "center_x", "wall_x", "center_z", "y", "width", "height",
            "fill", "lintel", "comment",
        }
    ),
    "scatter": frozenset(
        {"op", "from", "to", "block", "count", "seed", "states", "version", "comment"}
    ),
    "replace": frozenset(
        {"op", "from", "to", "from_block", "to_block", "states", "version", "comment"}
    ),
    "anchor": frozenset({"op", "name", "at", "type", "facing", "comment"}),
    "connector": frozenset(
        {"op", "name", "id", "face", "origin", "width", "height", "type", "comment"}
    ),
}

REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    "cuboid": frozenset({"op", "from", "to", "block"}),
    "floor": frozenset({"op", "from", "to", "block"}),
    "wall": frozenset({"op", "from", "to", "block"}),
    "shell": frozenset({"op", "from", "to", "block"}),
    "pillar": frozenset({"op", "at", "height", "block"}),
    "set": frozenset({"op", "at", "block"}),
    "doorway": frozenset({"op", "face", "y", "width", "height", "fill"}),
    "window": frozenset({"op", "face", "y", "width", "height", "fill"}),
    "roof_gable": frozenset({"op", "from", "to", "axis", "block", "fill_gable"}),
    "stair": frozenset({"op", "at", "steps", "facing", "block"}),
    "arch": frozenset({"op", "face", "y", "width", "height", "fill", "lintel"}),
    "scatter": frozenset({"op", "from", "to", "block", "count", "seed"}),
    "replace": frozenset({"op", "from", "to", "from_block", "to_block"}),
    "anchor": frozenset({"op", "name", "at", "type"}),
    "connector": frozenset({"op", "face", "origin", "width", "height", "type"}),
}

TOP_LEVEL_FIELDS = frozenset(
    {
        "schema", "id", "short_name", "size", "origin", "palette", "ops", "anchors", "connectors",
        "meta", "world_grammar", "production_standard", "rotation_policy", "mirror_policy",
    }
)

META_FIELDS = frozenset(
    {
        "product_type", "biome", "dialect", "vertical_band", "discovery", "notes",
        "entities_forbidden", "block_entities_forbidden", "max_occupied_blocks", "max_palette",
        "scatter_denominator", "ground_level",
    }
)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _point(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 3 and all(_is_int(v) for v in value)


def _state_value(value: Any) -> bool:
    return (isinstance(value, str) and len(value) <= 256) or isinstance(value, bool) or _is_int(value)


class DuplicateKeyError(ValueError):
    """Raised before validation when JSON object keys are not unique."""


def load_blueprint_json(path: Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise DuplicateKeyError(f"duplicate JSON object key {key!r}")
            value[key] = item
        return value

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)


def _validate_states(states: Any, where: str, errs: list[str]) -> None:
    if not isinstance(states, dict):
        errs.append(f"{where} must be an object")
        return
    for key, value in states.items():
        if not isinstance(key, str) or not STATE_KEY_RE.fullmatch(key):
            errs.append(f"{where} has invalid state key {key!r}")
        if not _state_value(value):
            errs.append(f"{where}.{key} must be a string, integer, or boolean")


def _in_bounds(point: list[int], size: list[int]) -> bool:
    return all(0 <= point[i] < size[i] for i in range(3))


def _block_token(token: Any, palette: dict[str, Any], where: str, errs: list[str]) -> None:
    if not isinstance(token, str):
        errs.append(f"{where} must be a palette key, namespaced block identifier, or void")
        return
    if token == "void" or token in palette or IDENTIFIER_RE.fullmatch(token):
        return
    errs.append(f"{where} references unknown palette key or invalid block identifier {token!r}")


def _opening_points(op: dict[str, Any]) -> list[list[int]]:
    width = op["width"]
    height = op["height"]
    half = width // 2
    points: list[list[int]] = []
    top_extra = 1 if op["op"] == "arch" else 0
    if op["face"] in ("north", "south"):
        for dx in range(-half, width - half):
            points.extend([[op["center_x"] + dx, op["y"] + dy, op["wall_z"]] for dy in range(height + top_extra)])
    else:
        for dz in range(-half, width - half):
            points.extend([[op["wall_x"], op["y"] + dy, op["center_z"] + dz] for dy in range(height + top_extra)])
    return points


def _connector_points(face: str, origin: list[int], width: int, height: int) -> list[list[int]]:
    x, y, z = origin
    if face in ("north", "south"):
        return [[x + dx, y + dy, z] for dx in range(width) for dy in range(height)]
    return [[x, y + dy, z + dz] for dz in range(width) for dy in range(height)]


def validate_blueprint(bp: Any, path: Path | None = None) -> list[str]:
    """Return deterministic, user-actionable validation errors."""
    del path  # reserved for future source-located diagnostics
    errs: list[str] = []
    if not isinstance(bp, dict):
        return ["blueprint root must be an object"]

    unknown = sorted(set(bp) - TOP_LEVEL_FIELDS)
    if unknown:
        errs.append(f"unknown top-level fields: {', '.join(unknown)}")
    for key in ("schema", "id", "size", "palette", "ops", "world_grammar", "production_standard"):
        if key not in bp:
            errs.append(f"missing {key}")

    if bp.get("schema") != SCHEMA_ID:
        errs.append(f"schema must be {SCHEMA_ID}")
    if not isinstance(bp.get("id"), str) or not IDENTIFIER_RE.fullmatch(bp.get("id", "")):
        errs.append("id must be a lowercase namespaced identifier such as mypack:roadside_house")
    if "short_name" in bp and (
        not isinstance(bp["short_name"], str) or not ALIAS_RE.fullmatch(bp["short_name"])
    ):
        errs.append("short_name must match ^[a-z][a-z0-9_]*$")
    if bp.get("world_grammar") != WORLD_GRAMMAR:
        errs.append(f"world_grammar must be {WORLD_GRAMMAR}")
    if bp.get("production_standard") != PRODUCTION_STANDARD:
        errs.append(f"production_standard must be {PRODUCTION_STANDARD}")

    size = bp.get("size")
    if not (_point(size) and all(1 <= v <= MAX_DIMENSION for v in size)):
        errs.append(f"size must be [x,y,z] integers 1..{MAX_DIMENSION}")
        size = None
    origin = bp.get("origin")
    if origin is not None and not _point(origin):
        errs.append("origin must be [x,y,z] integers")
    elif size is not None and origin is not None and not _in_bounds(origin, size):
        errs.append(f"origin {origin} out of bounds for size {size}")

    palette = bp.get("palette")
    if not isinstance(palette, dict) or not palette:
        errs.append("palette must be a non-empty object")
        palette = {}
    else:
        if len(palette) > MAX_PALETTE:
            errs.append(f"palette has {len(palette)} entries; hard maximum is {MAX_PALETTE}")
        for alias, entry in palette.items():
            if not isinstance(alias, str) or not ALIAS_RE.fullmatch(alias):
                errs.append(f"palette key {alias!r} must match ^[a-z][a-z0-9_]*$")
            if alias == "void":
                errs.append("palette key 'void' is reserved for leave-unchanged cells")
            if isinstance(entry, str):
                if not IDENTIFIER_RE.fullmatch(entry):
                    errs.append(f"palette.{alias} must be a namespaced block identifier")
            elif isinstance(entry, dict):
                extra = sorted(set(entry) - {"block", "states", "version"})
                if extra:
                    errs.append(f"palette.{alias} has unknown fields: {', '.join(extra)}")
                if not isinstance(entry.get("block"), str) or not IDENTIFIER_RE.fullmatch(entry.get("block", "")):
                    errs.append(f"palette.{alias}.block must be a namespaced block identifier")
                if "states" in entry:
                    _validate_states(entry["states"], f"palette.{alias}.states", errs)
                if "version" in entry and (not _is_int(entry["version"]) or entry["version"] < 0):
                    errs.append(f"palette.{alias}.version must be a non-negative integer")
            else:
                errs.append(f"palette.{alias} must be a block identifier or permutation object")

    meta = bp.get("meta", {})
    if not isinstance(meta, dict):
        errs.append("meta must be an object")
        meta = {}
    else:
        extra = sorted(set(meta) - META_FIELDS)
        if extra:
            errs.append(f"meta has unknown fields: {', '.join(extra)}")
        for field in ("entities_forbidden", "block_entities_forbidden"):
            if field in meta and not isinstance(meta[field], bool):
                errs.append(f"meta.{field} must be boolean")
        for field in ("max_occupied_blocks", "max_palette", "scatter_denominator"):
            if field in meta and (not _is_int(meta[field]) or meta[field] < 1):
                errs.append(f"meta.{field} must be a positive integer")
        if "ground_level" in meta and not _is_int(meta["ground_level"]):
            errs.append("meta.ground_level must be an integer")
        for field in ("product_type", "biome", "dialect", "vertical_band", "discovery", "notes"):
            if field in meta and not isinstance(meta[field], str):
                errs.append(f"meta.{field} must be a string")
        if "product_type" in meta and meta["product_type"] not in {"poi", "complex_module", "landmark", "realm_segment"}:
            errs.append("meta.product_type is not a supported product type")
        for field in ("biome", "dialect", "vertical_band"):
            if isinstance(meta.get(field), str) and not NAME_RE.fullmatch(meta[field]):
                errs.append(f"meta.{field} must be a stable lowercase name")
        if isinstance(meta.get("discovery"), str) and len(meta["discovery"]) > 1024:
            errs.append("meta.discovery exceeds 1024 characters")
        if isinstance(meta.get("notes"), str) and len(meta["notes"]) > 4096:
            errs.append("meta.notes exceeds 4096 characters")
        max_palette = meta.get("max_palette")
        if _is_int(max_palette) and len(palette) > max_palette:
            errs.append(f"palette has {len(palette)} entries; meta.max_palette is {max_palette}")

    for field, allowed in (
        ("rotation_policy", {"none", "y_90"}),
        ("mirror_policy", {"mirror_none", "mirror_x", "mirror_z", "mirror_xz"}),
    ):
        if field in bp and bp[field] not in allowed:
            errs.append(f"{field} must be one of {sorted(allowed)}")

    ops = bp.get("ops")
    if not isinstance(ops, list) or not ops:
        errs.append("ops must be a non-empty array")
        ops = []

    op_anchor_names: set[str] = set()
    op_connectors: dict[str, dict[str, Any]] = {}
    for i, op in enumerate(ops):
        where = f"ops[{i}]"
        if not isinstance(op, dict):
            errs.append(f"{where} must be an object")
            continue
        kind = op.get("op")
        if kind not in OP_FIELDS:
            errs.append(f"{where} unknown op {kind!r}")
            continue
        extra = sorted(set(op) - OP_FIELDS[kind])
        if extra:
            errs.append(f"{where} ({kind}) has unknown fields: {', '.join(extra)}")
        missing = sorted(REQUIRED_FIELDS[kind] - set(op))
        if missing:
            errs.append(f"{where} ({kind}) missing fields: {', '.join(missing)}")
            continue

        if "comment" in op and (not isinstance(op["comment"], str) or len(op["comment"]) > 4096):
            errs.append(f"{where}.comment must be a string of at most 4096 characters")

        for point_field in ("from", "to", "at", "origin"):
            if point_field in op:
                if not _point(op[point_field]):
                    errs.append(f"{where}.{point_field} must be [x,y,z] integers")
                elif size is not None and not _in_bounds(op[point_field], size):
                    errs.append(f"{where}.{point_field} {op[point_field]} out of bounds for size {size}")
        for state_field in ("states",):
            if state_field in op:
                _validate_states(op[state_field], f"{where}.{state_field}", errs)
        if "version" in op and (not _is_int(op["version"]) or op["version"] < 0):
            errs.append(f"{where}.version must be a non-negative integer")

        for block_field in ("block", "fill", "fill_gable", "lintel", "from_block", "to_block"):
            if block_field in op:
                _block_token(op[block_field], palette, f"{where}.{block_field}", errs)
        if op.get("block") == "void" and ("states" in op or "version" in op):
            errs.append(f"{where} void cannot carry states or a block version")
        if op.get("to_block") == "void" and ("states" in op or "version" in op):
            errs.append(f"{where} void cannot carry states or a block version")

        if kind == "floor" and _point(op["from"]) and _point(op["to"]) and op["from"][1] != op["to"][1]:
            errs.append(f"{where} floor endpoints must share one y coordinate")
        if kind == "wall" and _point(op["from"]) and _point(op["to"]):
            if op["from"][0] != op["to"][0] and op["from"][2] != op["to"][2]:
                errs.append(f"{where} wall must have a constant x or z coordinate")
        if kind == "pillar":
            if not _is_int(op["height"]) or op["height"] < 1:
                errs.append(f"{where}.height must be a positive integer")
            elif size is not None and _point(op["at"]) and op["at"][1] + op["height"] > size[1]:
                errs.append(f"{where} pillar exceeds y bounds")
        if kind == "shell":
            for flag in ("walls", "floor", "ceiling"):
                if flag in op and not isinstance(op[flag], bool):
                    errs.append(f"{where}.{flag} must be boolean")
        if kind == "roof_gable" and op.get("axis") not in ("x", "z"):
            errs.append(f"{where}.axis must be x or z")
        if kind == "stair":
            if op.get("facing") not in ("north", "south", "east", "west"):
                errs.append(f"{where}.facing must be a cardinal direction")
            if not _is_int(op.get("steps")) or op["steps"] < 1:
                errs.append(f"{where}.steps must be a positive integer")
            elif size is not None and _point(op["at"]) and op.get("facing") in ("north", "south", "east", "west"):
                dx, dz = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}[op["facing"]]
                end = [op["at"][0] + dx * (op["steps"] - 1), op["at"][1] + op["steps"] - 1, op["at"][2] + dz * (op["steps"] - 1)]
                if not _in_bounds(end, size):
                    errs.append(f"{where} stair run ends out of bounds at {end}")
        if kind == "scatter":
            if not _is_int(op.get("count")) or op["count"] < 0:
                errs.append(f"{where}.count must be a non-negative integer")
            if not _is_int(op.get("seed")):
                errs.append(f"{where}.seed is required and must be an integer")
        if kind in ("doorway", "window", "arch"):
            if op.get("face") not in ("north", "south", "east", "west"):
                errs.append(f"{where}.face must be a cardinal direction")
            horizontal = op.get("face") in ("north", "south")
            required_face = {"wall_z", "center_x"} if horizontal else {"wall_x", "center_z"}
            forbidden_face = {"wall_x", "center_z"} if horizontal else {"wall_z", "center_x"}
            missing_face = sorted(required_face - set(op))
            if missing_face:
                errs.append(f"{where} missing face coordinates: {', '.join(missing_face)}")
            present_forbidden = sorted(forbidden_face & set(op))
            if present_forbidden:
                errs.append(f"{where} has coordinates for the wrong face: {', '.join(present_forbidden)}")
            for field in ("y", "width", "height"):
                if not _is_int(op.get(field)) or op[field] < (0 if field == "y" else 1):
                    errs.append(f"{where}.{field} must be {'a non-negative' if field == 'y' else 'a positive'} integer")
            if not missing_face and not present_forbidden and size is not None and all(_is_int(op.get(f)) for f in ("y", "width", "height")):
                if any(not _in_bounds(p, size) for p in _opening_points(op)):
                    errs.append(f"{where} opening geometry exceeds bounds")
        if kind == "anchor":
            name = op.get("name")
            if not isinstance(name, str) or not NAME_RE.fullmatch(name):
                errs.append(f"{where}.name must be a stable lowercase name")
            elif name in op_anchor_names:
                errs.append(f"duplicate anchor name {name!r}")
            else:
                op_anchor_names.add(name)
            if not isinstance(op.get("type"), str) or not NAME_RE.fullmatch(op["type"]):
                errs.append(f"{where}.type must be a stable lowercase name")
            if "facing" in op and op["facing"] not in ("none", "north", "south", "east", "west", "up", "down"):
                errs.append(f"{where}.facing is invalid")
        if kind == "connector":
            names = [op.get(field) for field in ("name", "id") if field in op]
            if len(names) != 1 or not isinstance(names[0], str) or not NAME_RE.fullmatch(names[0]):
                errs.append(f"{where} must define exactly one valid name or id")
            else:
                name = names[0]
                if name in op_connectors:
                    errs.append(f"duplicate connector name {name!r}")
                else:
                    op_connectors[name] = op
            if op.get("face") not in ("north", "south", "east", "west"):
                errs.append(f"{where}.face must be a cardinal direction")
            if not isinstance(op.get("type"), str) or not NAME_RE.fullmatch(op["type"]):
                errs.append(f"{where}.type must be a stable lowercase name")
            for field in ("width", "height"):
                if not _is_int(op.get(field)) or op[field] < 1:
                    errs.append(f"{where}.{field} must be a positive integer")
            if size is not None and _point(op.get("origin")) and op.get("face") in ("north", "south", "east", "west") and all(_is_int(op.get(f)) and op[f] >= 1 for f in ("width", "height")):
                if any(not _in_bounds(p, size) for p in _connector_points(op["face"], op["origin"], op["width"], op["height"])):
                    errs.append(f"{where} connector geometry exceeds bounds")

    anchors = bp.get("anchors", {})
    if not isinstance(anchors, dict):
        errs.append("anchors must be an object")
        anchors = {}
    for name, point in anchors.items():
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            errs.append(f"anchors key {name!r} must be a stable lowercase name")
        if not _point(point):
            errs.append(f"anchors.{name} must be [x,y,z] integers")
        elif size is not None and not _in_bounds(point, size):
            errs.append(f"anchors.{name} {point} out of bounds for size {size}")
        matching = [op for op in ops if isinstance(op, dict) and op.get("op") == "anchor" and op.get("name") == name]
        if matching and matching[0].get("at") != point:
            errs.append(f"anchor {name!r} conflicts between ops and anchors map")

    connectors = bp.get("connectors", [])
    if not isinstance(connectors, list):
        errs.append("connectors must be an array")
        connectors = []
    seen_top_connectors: set[str] = set()
    for i, connector in enumerate(connectors):
        where = f"connectors[{i}]"
        if not isinstance(connector, dict):
            errs.append(f"{where} must be an object")
            continue
        extra = sorted(set(connector) - {"id", "face", "origin_local", "width", "height", "type"})
        if extra:
            errs.append(f"{where} has unknown fields: {', '.join(extra)}")
        missing = sorted({"id", "face", "origin_local", "width", "height", "type"} - set(connector))
        if missing:
            errs.append(f"{where} missing fields: {', '.join(missing)}")
            continue
        name = connector["id"]
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            errs.append(f"{where}.id must be a stable lowercase name")
        elif name in seen_top_connectors:
            errs.append(f"duplicate connector name {name!r}")
        else:
            seen_top_connectors.add(name)
        if connector["face"] not in ("north", "south", "east", "west"):
            errs.append(f"{where}.face must be a cardinal direction")
        if not _point(connector["origin_local"]):
            errs.append(f"{where}.origin_local must be [x,y,z] integers")
        elif size is not None and not _in_bounds(connector["origin_local"], size):
            errs.append(f"{where}.origin_local out of bounds")
        for field in ("width", "height"):
            if not _is_int(connector[field]) or connector[field] < 1:
                errs.append(f"{where}.{field} must be a positive integer")
        if not isinstance(connector["type"], str) or not NAME_RE.fullmatch(connector["type"]):
            errs.append(f"{where}.type must be a stable lowercase name")
        if (
            size is not None and _point(connector["origin_local"])
            and connector["face"] in ("north", "south", "east", "west")
            and all(_is_int(connector[f]) and connector[f] >= 1 for f in ("width", "height"))
            and any(not _in_bounds(p, size) for p in _connector_points(connector["face"], connector["origin_local"], connector["width"], connector["height"]))
        ):
            errs.append(f"{where} connector geometry exceeds bounds")
        matching = op_connectors.get(name) if isinstance(name, str) else None
        if matching:
            normalized = {
                "id": matching.get("name", matching.get("id")),
                "face": matching["face"],
                "origin_local": matching["origin"],
                "width": matching["width"],
                "height": matching["height"],
                "type": matching["type"],
            }
            if normalized != connector:
                errs.append(f"connector {name!r} conflicts between ops and connectors array")

    return errs
