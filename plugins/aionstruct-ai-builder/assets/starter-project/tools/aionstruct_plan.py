#!/usr/bin/env python3
"""Semantic AIONSTRUCT Plan v1 validation and Blueprint v1 lowering.

Plan is an authoring layer only. It deterministically emits ordinary Blueprint
v1 operations and a hash-bound source map; it never writes Bedrock bytes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from aionstruct_validate import (
    ALIAS_RE,
    IDENTIFIER_RE,
    MAX_DIMENSION,
    NAME_RE,
    load_blueprint_json,
    validate_blueprint,
)


SCHEMA_ID = "aionstruct.plan.v1"
MAX_COMPONENTS = 256
MAX_GENERATED_OPS = 2048
COMPONENT_KINDS = frozenset(
    {"foundation", "room", "opening", "roof", "stair_run", "anchor", "connector"}
)
TOP_FIELDS = frozenset(
    {
        "schema", "id", "short_name", "size", "origin", "palette", "components", "meta",
        "world_grammar", "production_standard", "rotation_policy", "mirror_policy",
    }
)
COMMON_FIELDS = frozenset({"id", "kind", "depends_on", "comment"})
KIND_FIELDS = {
    "foundation": frozenset({"from", "to", "block"}),
    "room": frozenset(
        {"from", "to", "wall_block", "floor_block", "ceiling_block", "clear_block"}
    ),
    "opening": frozenset(
        {
            "host", "opening_kind", "face", "wall_z", "center_x", "wall_x", "center_z",
            "y", "width", "height", "fill", "lintel",
        }
    ),
    "roof": frozenset({"host", "from", "to", "axis", "block", "fill_gable"}),
    "stair_run": frozenset({"at", "steps", "facing", "block", "states"}),
    "anchor": frozenset({"name", "at", "type", "facing"}),
    "connector": frozenset({"name", "face", "origin", "width", "height", "type"}),
}
REQUIRED = {
    "foundation": frozenset({"from", "to", "block"}),
    "room": frozenset({"from", "to", "wall_block", "floor_block", "ceiling_block"}),
    "opening": frozenset(
        {"host", "opening_kind", "face", "y", "width", "height", "fill"}
    ),
    "roof": frozenset({"host", "from", "to", "axis", "block", "fill_gable"}),
    "stair_run": frozenset({"at", "steps", "facing", "block"}),
    "anchor": frozenset({"name", "at", "type"}),
    "connector": frozenset({"name", "face", "origin", "width", "height", "type"}),
}


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def diagnostic(
    code: str,
    message: str,
    path: str,
    component_id: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "code": code,
        "severity": "error",
        "message": message,
        "path": path,
    }
    if component_id is not None:
        item["component_id"] = component_id
    return item


def _point(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 3
        and all(isinstance(item, int) and not isinstance(item, bool) for item in value)
    )


def _in_bounds(point: list[int], size: list[int]) -> bool:
    return all(0 <= point[index] < size[index] for index in range(3))


def _token(value: Any, palette: dict[str, Any]) -> bool:
    return isinstance(value, str) and (
        value == "void" or value in palette or bool(IDENTIFIER_RE.fullmatch(value))
    )


def _topological_order(components: list[dict[str, Any]]) -> tuple[list[str], list[str] | None]:
    source_order = sorted(component["id"] for component in components)
    dependencies = {
        component["id"]: set(component.get("depends_on") or []) for component in components
    }
    result: list[str] = []
    remaining = set(source_order)
    while remaining:
        ready = [name for name in source_order if name in remaining and not (dependencies[name] & remaining)]
        if not ready:
            return result, [name for name in source_order if name in remaining]
        for name in ready:
            remaining.remove(name)
            result.append(name)
    return result, None


def validate_plan(plan: Any) -> list[dict[str, Any]]:
    """Return deterministic structured diagnostics for a Plan v1 document."""
    errors: list[dict[str, Any]] = []
    if not isinstance(plan, dict):
        return [diagnostic("PLAN_ROOT_TYPE", "plan root must be an object", "$")]

    unknown = sorted(set(plan) - TOP_FIELDS)
    if unknown:
        errors.append(diagnostic("PLAN_UNKNOWN_FIELD", f"unknown fields: {', '.join(unknown)}", "$"))
    for field in (
        "schema", "id", "size", "palette", "components", "world_grammar", "production_standard"
    ):
        if field not in plan:
            errors.append(diagnostic("PLAN_REQUIRED_FIELD", f"missing {field}", f"$.{field}"))
    if plan.get("schema") != SCHEMA_ID:
        errors.append(diagnostic("PLAN_SCHEMA", f"schema must be {SCHEMA_ID}", "$.schema"))
    if not isinstance(plan.get("id"), str) or not IDENTIFIER_RE.fullmatch(plan.get("id", "")):
        errors.append(diagnostic("PLAN_ID", "id must be a lowercase namespaced identifier", "$.id"))
    if "short_name" in plan and (
        not isinstance(plan["short_name"], str) or not ALIAS_RE.fullmatch(plan["short_name"])
    ):
        errors.append(diagnostic("PLAN_SHORT_NAME", "short_name must be a lowercase alias", "$.short_name"))
    if plan.get("rotation_policy", "none") != "none":
        errors.append(diagnostic("PLAN_TRANSFORM_UNSUPPORTED", "Plan v1 alpha does not apply rotation", "$.rotation_policy"))
    if plan.get("mirror_policy", "mirror_none") != "mirror_none":
        errors.append(diagnostic("PLAN_TRANSFORM_UNSUPPORTED", "Plan v1 alpha does not apply mirroring", "$.mirror_policy"))

    size = plan.get("size")
    if not (_point(size) and all(1 <= item <= MAX_DIMENSION for item in size)):
        errors.append(
            diagnostic("PLAN_SIZE", f"size must be [x,y,z] integers 1..{MAX_DIMENSION}", "$.size")
        )
        size = None
    palette = plan.get("palette")
    if not isinstance(palette, dict) or not palette:
        errors.append(diagnostic("PLAN_PALETTE", "palette must be a non-empty object", "$.palette"))
        palette = {}

    components = plan.get("components")
    if not isinstance(components, list) or not components:
        errors.append(
            diagnostic("PLAN_COMPONENTS", "components must be a non-empty array", "$.components")
        )
        return errors
    if len(components) > MAX_COMPONENTS:
        errors.append(
            diagnostic(
                "PLAN_COMPONENT_BUDGET",
                f"component count {len(components)} exceeds hard maximum {MAX_COMPONENTS}",
                "$.components",
            )
        )

    ids: set[str] = set()
    usable: list[dict[str, Any]] = []
    declared_by_id = {
        item.get("id"): item
        for item in components
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    for index, component in enumerate(components):
        path = f"$.components[{index}]"
        if not isinstance(component, dict):
            errors.append(diagnostic("PLAN_COMPONENT_TYPE", "component must be an object", path))
            continue
        component_id = component.get("id")
        if not isinstance(component_id, str) or not NAME_RE.fullmatch(component_id):
            errors.append(
                diagnostic("PLAN_COMPONENT_ID", "component id must be a stable lowercase name", f"{path}.id")
            )
            continue
        if component_id in ids:
            errors.append(
                diagnostic("PLAN_DUPLICATE_ID", f"duplicate component id {component_id!r}", f"{path}.id", component_id)
            )
            continue
        ids.add(component_id)
        usable.append(component)
        kind = component.get("kind")
        if not isinstance(kind, str) or kind not in COMPONENT_KINDS:
            errors.append(
                diagnostic("PLAN_COMPONENT_KIND", f"unsupported component kind {kind!r}", f"{path}.kind", component_id)
            )
            continue
        extra = sorted(set(component) - COMMON_FIELDS - KIND_FIELDS[kind])
        if extra:
            errors.append(
                diagnostic("PLAN_COMPONENT_FIELD", f"unknown fields: {', '.join(extra)}", path, component_id)
            )
        missing = sorted(REQUIRED[kind] - set(component))
        if missing:
            errors.append(
                diagnostic("PLAN_COMPONENT_REQUIRED", f"missing fields: {', '.join(missing)}", path, component_id)
            )
            continue
        depends = component.get("depends_on", [])
        if not isinstance(depends, list) or any(not isinstance(item, str) for item in depends):
            errors.append(
                diagnostic("PLAN_DEPENDENCY_TYPE", "depends_on must be an array of component ids", f"{path}.depends_on", component_id)
            )
        elif len(depends) != len(set(depends)):
            errors.append(
                diagnostic("PLAN_DUPLICATE_DEPENDENCY", "depends_on entries must be unique", f"{path}.depends_on", component_id)
            )

        for field in ("from", "to", "at", "origin"):
            if field in component:
                value = component[field]
                if not _point(value):
                    errors.append(diagnostic("PLAN_POINT", f"{field} must be [x,y,z] integers", f"{path}.{field}", component_id))
                elif size is not None and not _in_bounds(value, size):
                    errors.append(diagnostic("PLAN_BOUNDS", f"{field} {value} is outside size {size}", f"{path}.{field}", component_id))
        for field in (
            "block", "wall_block", "floor_block", "ceiling_block", "clear_block", "fill", "lintel", "fill_gable"
        ):
            if field in component and not _token(component[field], palette):
                errors.append(
                    diagnostic("PLAN_BLOCK_TOKEN", f"{field} references an unknown block token", f"{path}.{field}", component_id)
                )

        if kind == "room" and _point(component["from"]) and _point(component["to"]):
            spans = [abs(component["to"][axis] - component["from"][axis]) + 1 for axis in range(3)]
            if spans[0] < 3 or spans[1] < 3 or spans[2] < 3:
                errors.append(
                    diagnostic("PLAN_ROOM_INTERIOR", "room bounds must leave an interior on every axis", path, component_id)
                )
        if kind in {"opening", "roof"}:
            host = component.get("host")
            if not isinstance(host, str):
                errors.append(diagnostic("PLAN_HOST_TYPE", "host must be a component id", f"{path}.host", component_id))
            elif host not in declared_by_id:
                errors.append(diagnostic("PLAN_HOST", f"unknown host {host!r}", f"{path}.host", component_id))
            elif declared_by_id[host].get("kind") != "room":
                errors.append(diagnostic("PLAN_HOST_KIND", "opening and roof hosts must be room components", f"{path}.host", component_id))
            else:
                host_component = declared_by_id[host]
                if _point(host_component.get("from")) and _point(host_component.get("to")):
                    host_min = [min(host_component["from"][axis], host_component["to"][axis]) for axis in range(3)]
                    host_max = [max(host_component["from"][axis], host_component["to"][axis]) for axis in range(3)]
                    if kind == "opening":
                        face = component.get("face")
                        expected_wall = {
                            "north": ("wall_z", host_max[2]),
                            "south": ("wall_z", host_min[2]),
                            "west": ("wall_x", host_min[0]),
                            "east": ("wall_x", host_max[0]),
                        }.get(face) if isinstance(face, str) else None
                        if expected_wall and component.get(expected_wall[0]) != expected_wall[1]:
                            errors.append(
                                diagnostic(
                                    "PLAN_OPENING_HOST_WALL",
                                    f"{expected_wall[0]} must equal host boundary {expected_wall[1]}",
                                    f"{path}.{expected_wall[0]}",
                                    component_id,
                                )
                            )
                        width = component.get("width")
                        height = component.get("height")
                        y = component.get("y")
                        center = component.get("center_x") if face in ("north", "south") else component.get("center_z")
                        axis_min, axis_max = (host_min[0], host_max[0]) if face in ("north", "south") else (host_min[2], host_max[2])
                        if all(isinstance(value, int) and not isinstance(value, bool) for value in (width, center)) and width >= 1:
                            half = width // 2
                            start = center - half
                            end = center + (width - half) - 1
                            if start < axis_min or end > axis_max:
                                errors.append(diagnostic("PLAN_OPENING_HOST_SPAN", "opening width exceeds its host wall", path, component_id))
                        if all(isinstance(value, int) and not isinstance(value, bool) for value in (y, height)) and height >= 1:
                            opening_top = y + height - 1 + (1 if component.get("opening_kind") == "arch" else 0)
                            if y < host_min[1] + 1 or opening_top > host_max[1] - 1:
                                errors.append(diagnostic("PLAN_OPENING_HOST_HEIGHT", "opening must stay between the host floor and ceiling", path, component_id))
                    elif _point(component.get("from")) and _point(component.get("to")):
                        roof_min = [min(component["from"][axis], component["to"][axis]) for axis in range(3)]
                        roof_max = [max(component["from"][axis], component["to"][axis]) for axis in range(3)]
                        if roof_min[1] != host_max[1] + 1:
                            errors.append(diagnostic("PLAN_ROOF_HOST_HEIGHT", "roof base must be one block above its host", f"{path}.from", component_id))
                        if not (
                            roof_min[0] <= host_min[0] <= host_max[0] <= roof_max[0]
                            and roof_min[2] <= host_min[2] <= host_max[2] <= roof_max[2]
                        ):
                            errors.append(diagnostic("PLAN_ROOF_HOST_SPAN", "roof X/Z bounds must cover its host room", path, component_id))
            if isinstance(depends, list) and host not in depends:
                errors.append(
                    diagnostic("PLAN_HOST_DEPENDENCY", "host must also appear in depends_on", f"{path}.depends_on", component_id)
                )
        if kind == "opening":
            opening_kind = component.get("opening_kind")
            if opening_kind not in ("doorway", "window", "arch"):
                errors.append(diagnostic("PLAN_OPENING_KIND", "opening_kind must be doorway, window, or arch", f"{path}.opening_kind", component_id))
            if opening_kind == "arch" and "lintel" not in component:
                errors.append(diagnostic("PLAN_ARCH_LINTEL", "arch requires lintel", f"{path}.lintel", component_id))
        if kind == "roof" and component.get("axis") not in ("x", "z"):
            errors.append(diagnostic("PLAN_ROOF_AXIS", "roof axis must be x or z", f"{path}.axis", component_id))

    for index, component in enumerate(usable):
        component_id = component["id"]
        dependencies = component.get("depends_on") or []
        if not isinstance(dependencies, list) or any(not isinstance(item, str) for item in dependencies):
            continue
        for dependency in dependencies:
            if dependency == component_id:
                errors.append(diagnostic("PLAN_SELF_DEPENDENCY", "component cannot depend on itself", f"$.components[{index}].depends_on", component_id))
            elif dependency not in ids:
                errors.append(diagnostic("PLAN_UNKNOWN_DEPENDENCY", f"unknown dependency {dependency!r}", f"$.components[{index}].depends_on", component_id))

    if usable and all(
        isinstance(item.get("depends_on", []), list)
        and all(isinstance(dependency, str) for dependency in item.get("depends_on", []))
        for item in usable
    ):
        _order, cycle = _topological_order(usable)
        if cycle:
            errors.append(diagnostic("PLAN_DEPENDENCY_CYCLE", f"dependency cycle involves: {', '.join(cycle)}", "$.components"))
    if not errors:
        order, _cycle = _topological_order(usable)
        by_id = {component["id"]: component for component in usable}
        operations = [
            operation
            for component_id in order
            for operation in _lower_component(by_id[component_id])
        ]
        if len(operations) > MAX_GENERATED_OPS:
            errors.append(
                diagnostic(
                    "PLAN_OPERATION_BUDGET",
                    f"generated operation count {len(operations)} exceeds hard maximum {MAX_GENERATED_OPS}",
                    "$.components",
                )
            )
        else:
            candidate = {
                key: plan[key]
                for key in (
                    "id", "short_name", "size", "origin", "palette", "meta", "world_grammar",
                    "production_standard", "rotation_policy", "mirror_policy",
                )
                if key in plan
            }
            candidate = {"schema": "aionstruct.blueprint.v1", **candidate, "ops": operations}
            for blueprint_error in validate_blueprint(candidate):
                errors.append(
                    diagnostic(
                        "PLAN_BLUEPRINT_INVALID",
                        blueprint_error,
                        "$.components",
                    )
                )
    return errors


def _comment(component: dict[str, Any]) -> str:
    suffix = str(component.get("comment") or component["kind"])
    return f"[plan:{component['id']}] {suffix}"


def _lower_component(component: dict[str, Any]) -> list[dict[str, Any]]:
    kind = component["kind"]
    comment = _comment(component)
    if kind == "foundation":
        return [{"op": "cuboid", "from": component["from"], "to": component["to"], "block": component["block"], "comment": comment}]
    if kind == "room":
        a = [min(component["from"][axis], component["to"][axis]) for axis in range(3)]
        b = [max(component["from"][axis], component["to"][axis]) for axis in range(3)]
        return [
            {"op": "shell", "from": a, "to": b, "block": component["wall_block"], "walls": True, "floor": False, "ceiling": False, "comment": comment},
            {"op": "floor", "from": [a[0], a[1], a[2]], "to": [b[0], a[1], b[2]], "block": component["floor_block"], "comment": comment},
            {"op": "floor", "from": [a[0], b[1], a[2]], "to": [b[0], b[1], b[2]], "block": component["ceiling_block"], "comment": comment},
            {"op": "cuboid", "from": [a[0] + 1, a[1] + 1, a[2] + 1], "to": [b[0] - 1, b[1] - 1, b[2] - 1], "block": component.get("clear_block", "minecraft:air"), "comment": comment},
        ]
    if kind == "opening":
        fields = {
            key: value for key, value in component.items()
            if key in {"face", "wall_z", "center_x", "wall_x", "center_z", "y", "width", "height", "fill", "lintel"}
        }
        return [{"op": component["opening_kind"], **fields, "comment": comment}]
    if kind == "roof":
        return [{"op": "roof_gable", "from": component["from"], "to": component["to"], "axis": component["axis"], "block": component["block"], "fill_gable": component["fill_gable"], "comment": comment}]
    if kind == "stair_run":
        result = {key: component[key] for key in ("at", "steps", "facing", "block")}
        if "states" in component:
            result["states"] = component["states"]
        return [{"op": "stair", **result, "comment": comment}]
    if kind == "anchor":
        result = {key: component[key] for key in ("name", "at", "type")}
        if "facing" in component:
            result["facing"] = component["facing"]
        return [{"op": "anchor", **result, "comment": comment}]
    if kind == "connector":
        return [{"op": "connector", **{key: component[key] for key in ("name", "face", "origin", "width", "height", "type")}, "comment": comment}]
    raise ValueError(f"unsupported plan component kind {kind!r}")


def lower_plan(plan: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    diagnostics = validate_plan(plan)
    if diagnostics:
        raise ValueError("invalid plan: " + " | ".join(item["message"] for item in diagnostics))
    by_id = {component["id"]: component for component in plan["components"]}
    order, cycle = _topological_order(plan["components"])
    if cycle:
        raise ValueError(f"plan dependency cycle: {cycle}")
    operations: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    for component_id in order:
        component = by_id[component_id]
        first = len(operations)
        generated = _lower_component(component)
        operations.extend(generated)
        if len(operations) > MAX_GENERATED_OPS:
            raise ValueError(f"generated operation count exceeds hard maximum {MAX_GENERATED_OPS}")
        entries.append(
            {
                "component_id": component_id,
                "kind": component["kind"],
                "depends_on": list(component.get("depends_on") or []),
                "blueprint_op_indices": list(range(first, first + len(generated))),
            }
        )

    blueprint = {
        key: plan[key]
        for key in (
            "id", "short_name", "size", "origin", "palette", "meta", "world_grammar",
            "production_standard", "rotation_policy", "mirror_policy",
        )
        if key in plan
    }
    blueprint = {"schema": "aionstruct.blueprint.v1", **blueprint, "ops": operations}
    blueprint_errors = validate_blueprint(blueprint)
    if blueprint_errors:
        raise ValueError("lowered Blueprint v1 is invalid: " + " | ".join(blueprint_errors))
    source_map = {
        "schema": "aionstruct.plan_source_map.v1",
        "plan_id": plan["id"],
        "plan_sha256": sha256(plan),
        "blueprint_sha256": sha256(blueprint),
        "topological_order": order,
        "components": entries,
        "proof_boundary": [
            "semantic_plan_to_blueprint_only",
            "not_voxel_ir_or_mcstructure_proof",
            "not_bds_client_gameplay_or_release_proof",
        ],
    }
    return blueprint, source_map


def load_plan(path: Path) -> dict[str, Any]:
    return load_blueprint_json(path)
