"""Deterministic little-endian Bedrock ``.mcstructure`` encoder.

The encoder deliberately has no decoder code.  On-disk verification belongs to
``mcstructure_reader.py`` so a writer bug cannot validate itself by sharing the
same implementation.

Bedrock's structure index order is Z-fastest, then Y, then X:
``x * size_y * size_z + y * size_z + z``.  A missing coordinate is structure
void (index ``-1``); an authored ``minecraft:air`` cell is a real palette entry
and therefore clears the destination block when placed.
"""
from __future__ import annotations

import struct
from typing import Any, Callable, Mapping


# Bedrock block runtime version used by the existing factory authors.
BLOCK_VERSION = 18168865
StateValue = bool | int | str
PermutationKey = tuple[str, tuple[tuple[str, str, StateValue], ...], int]


class NbtWriter:
    def __init__(self) -> None:
        self.parts: list[bytes] = []

    def u8(self, value: int) -> None:
        self.parts.append(struct.pack("<B", value))

    def i8(self, value: int) -> None:
        self.parts.append(struct.pack("<b", value))

    def i32(self, value: int) -> None:
        self.parts.append(struct.pack("<i", value))

    def string_payload(self, value: str) -> None:
        encoded = value.encode("utf-8")
        if len(encoded) > 0xFFFF:
            raise ValueError("NBT string exceeds 65535 encoded bytes")
        self.parts.append(struct.pack("<H", len(encoded)))
        self.parts.append(encoded)

    def head(self, tag_type: int, name: str) -> None:
        self.u8(tag_type)
        self.string_payload(name)

    def byte_tag(self, name: str, value: int) -> None:
        self.head(1, name)
        self.i8(value)

    def int_tag(self, name: str, value: int) -> None:
        self.head(3, name)
        self.i32(value)

    def string_tag(self, name: str, value: str) -> None:
        self.head(8, name)
        self.string_payload(value)

    def list_tag(self, name: str, tag_type: int, values: list, emit: Callable) -> None:
        self.head(9, name)
        self.u8(tag_type)
        self.i32(len(values))
        for value in values:
            emit(value)

    def list_payload(self, tag_type: int, values: list, emit: Callable) -> None:
        self.u8(tag_type)
        self.i32(len(values))
        for value in values:
            emit(value)

    def compound(self, name: str, emit: Callable[[], None]) -> None:
        self.head(10, name)
        emit()
        self.u8(0)

    def finish(self) -> bytes:
        return b"".join(self.parts)


def flat_index(x: int, y: int, z: int, sy: int, sz: int) -> int:
    """Return Bedrock's X-major, Z-fastest linear structure index."""
    return x * sy * sz + y * sz + z


def _canonical_states(states: Mapping[str, Any] | None) -> tuple[tuple[str, str, StateValue], ...]:
    """Return a stable, type-bearing state tuple.

    Bedrock block states in this lane are intentionally finite: bool is encoded
    as TAG_Byte, int as TAG_Int, and str as TAG_String.  Python bool must be
    checked before int because bool is an int subclass.
    """
    if states is None:
        return ()
    if not isinstance(states, Mapping):
        raise TypeError("block states must be an object")
    result: list[tuple[str, str, StateValue]] = []
    for name in sorted(states):
        if not isinstance(name, str) or not name:
            raise TypeError("block state names must be non-empty strings")
        value = states[name]
        if isinstance(value, bool):
            result.append((name, "bool", value))
        elif isinstance(value, int):
            if not -(2**31) <= value < 2**31:
                raise ValueError(f"block state {name!r} is outside signed int32")
            result.append((name, "int", value))
        elif isinstance(value, str):
            result.append((name, "string", value))
        else:
            raise TypeError(
                f"unsupported block state type for {name!r}: {type(value).__name__}; "
                "expected bool, int, or string"
            )
    return tuple(result)


def canonical_permutation_key(
    identifier: str,
    states: Mapping[str, Any] | None = None,
    version: int = BLOCK_VERSION,
) -> PermutationKey:
    """Canonical palette identity: identifier, typed sorted states, version."""
    if identifier == "air":
        identifier = "minecraft:air"
    if not isinstance(identifier, str) or not identifier or ":" not in identifier:
        raise ValueError(f"invalid namespaced block identifier: {identifier!r}")
    if isinstance(version, bool) or not isinstance(version, int):
        raise TypeError("block version must be an integer")
    if not -(2**31) <= version < 2**31:
        raise ValueError("block version is outside signed int32")
    return identifier, _canonical_states(states), version


def _palette_document(key: PermutationKey) -> dict[str, Any]:
    identifier, typed_states, version = key
    return {
        "name": identifier,
        "states": {name: value for name, _kind, value in typed_states},
        "version": version,
    }


def _emit_state(writer: NbtWriter, name: str, kind: str, value: StateValue) -> None:
    if kind == "bool":
        writer.byte_tag(name, 1 if value else 0)
    elif kind == "int":
        writer.int_tag(name, value)
    elif kind == "string":
        writer.string_tag(name, value)
    else:  # defensive: canonicalization is the only producer
        raise TypeError(f"unsupported canonical state kind: {kind}")


def encode_mcstructure(
    size: tuple[int, int, int],
    cells: list[dict[str, Any]],
    *,
    structure_world_origin: tuple[int, int, int] = (0, 0, 0),
    block_position_data: dict[int, Callable[[NbtWriter], None]] | None = None,
) -> tuple[bytes, list[dict[str, Any]], list[int]]:
    """Encode IR cells and return ``(bytes, structured_palette, primary_indices)``.

    Each cell is ``{x, y, z, block, states?, version?}``.  Duplicate positions
    are rejected rather than relying on order-dependent overwrite behavior.
    Empty coordinates remain structure void.  Explicit air is encoded normally.
    """
    if len(size) != 3 or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in size):
        raise ValueError("size must contain three positive integers")
    if len(structure_world_origin) != 3 or any(
        isinstance(v, bool) or not isinstance(v, int) for v in structure_world_origin
    ):
        raise ValueError("structure_world_origin must contain three integers")
    sx, sy, sz = size

    positioned: dict[tuple[int, int, int], PermutationKey] = {}
    for cell in cells:
        if not isinstance(cell, dict):
            raise TypeError("each cell must be an object")
        try:
            x, y, z = int(cell["x"]), int(cell["y"]), int(cell["z"])
            block = cell["block"]
        except KeyError as exc:
            raise ValueError(f"cell missing required field {exc.args[0]!r}") from exc
        if any(isinstance(cell[axis], bool) or not isinstance(cell[axis], int) for axis in ("x", "y", "z")):
            raise TypeError("cell coordinates must be integers")
        if not (0 <= x < sx and 0 <= y < sy and 0 <= z < sz):
            raise ValueError(f"cell out of bounds {(x, y, z)} size={size}")
        pos = (x, y, z)
        if pos in positioned:
            raise ValueError(f"duplicate cell coordinate {pos}")
        positioned[pos] = canonical_permutation_key(
            block, cell.get("states"), cell.get("version", BLOCK_VERSION)
        )

    palette_keys = sorted(set(positioned.values()))
    palette_index = {key: i for i, key in enumerate(palette_keys)}
    palette = [_palette_document(key) for key in palette_keys]

    volume = sx * sy * sz
    indices = [-1] * volume
    for (x, y, z), key in positioned.items():
        indices[flat_index(x, y, z, sy, sz)] = palette_index[key]

    n = NbtWriter()
    n.head(10, "")
    n.int_tag("format_version", 1)
    n.list_tag("size", 3, [sx, sy, sz], n.i32)
    n.list_tag("structure_world_origin", 3, list(structure_world_origin), n.i32)

    def emit_structure() -> None:
        n.list_tag(
            "block_indices",
            9,
            [indices, [-1] * volume],
            lambda layer: n.list_payload(3, layer, n.i32),
        )
        n.list_tag("entities", 10, [], lambda _value: None)

        def emit_default() -> None:
            def entry(key: PermutationKey) -> None:
                identifier, typed_states, version = key
                n.string_tag("name", identifier)
                n.compound(
                    "states",
                    lambda: [_emit_state(n, name, kind, value) for name, kind, value in typed_states],
                )
                n.int_tag("version", version)
                n.u8(0)  # list compounds contain payloads, not named tags

            n.list_tag("block_palette", 10, palette_keys, entry)

            def emit_bpd() -> None:
                if not block_position_data:
                    return
                for key in sorted(block_position_data):
                    if isinstance(key, bool) or not isinstance(key, int) or not 0 <= key < volume:
                        raise ValueError(f"block_position_data key out of bounds: {key!r}")
                    n.compound(str(key), lambda k=key: block_position_data[k](n))

            n.compound("block_position_data", emit_bpd)

        n.compound("palette", lambda: n.compound("default", emit_default))

    n.compound("structure", emit_structure)
    n.u8(0)
    return n.finish(), palette, indices


def decode_palette_and_counts(data: bytes) -> dict[str, Any]:
    """Deprecated header probe retained for callers; not artifact validation."""
    if len(data) < 8 or data[:3] != b"\x0a\x00\x00":
        raise ValueError("not a little-endian unnamed-root .mcstructure")
    return {"byte_length": len(data), "header_ok": True, "sha_prefix": None}
