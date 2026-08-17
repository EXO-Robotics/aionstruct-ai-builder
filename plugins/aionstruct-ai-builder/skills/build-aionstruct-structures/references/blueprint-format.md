# Blueprint format

Blueprint v1 is the stable low-level operation language and remains a supported direct input. For new architecture, prefer semantic Plan v1 and inspect the lowered Blueprint; see [plan-format.md](plan-format.md).

## Contents

1. Coordinates and identity
2. Palette and states
3. Operations
4. Air, void, and operation order
5. Bedrock encoding

## Coordinates and identity

A blueprint uses local integer coordinates `[x, y, z]` inside `size`. Use a lowercase namespaced identifier such as `mypack:structures/roadside_house`. The public starter schema is `aionstruct.blueprint.v1` with `AIONSTRUCT_WORLD_GRAMMAR_V1` and `AIONSTRUCT_STRUCTURE_STANDARD_V1`.

All coordinates must remain inside the finite envelope. Keep local Y large enough for foundation, occupied floors, three-block headroom, roofs, and protrusions.

## Palette and states

Palette aliases resolve to a block identifier or a typed permutation:

```json
{
  "air": "minecraft:air",
  "wall": {"block":"minecraft:stonebrick","states":{"stone_brick_type":"mossy"}},
  "beam": {"block":"minecraft:dark_oak_log","states":{"pillar_axis":"y"}},
  "lantern": {"block":"minecraft:lantern","states":{"hanging":false}}
}
```

State values remain typed booleans, signed integers, or strings. Do not guess Bedrock state keys. Unsupported permutations may encode successfully yet canonicalize or fail at runtime, so BDS remains authoritative.

## Operations

The strict vocabulary is finite:

- `cuboid`, `floor`, `wall`, `shell`
- `pillar`, `set`
- `doorway`, `window`, `arch`
- `roof_gable`, `stair`
- deterministic `scatter`, bounded `replace`
- `anchor`, `connector`

Unknown fields fail validation. Prefer a few meaningful cuboids and explicit carving operations over thousands of hand-written cells. Use comments only as provenance; tests must inspect expanded cells.

## Air, void, and operation order

- An explicit `minecraft:air` cell clears the destination when the structure loads.
- An absent coordinate compiles to `-1` structure void and leaves the destination unchanged.
- A `void` operation removes an earlier authored cell.
- Operations apply in source order. Later operations overwrite earlier cells.

This distinction is central to terrain preservation. Carve player clearance and apertures with explicit air. Leave surrounding landscape, natural corners, and deliberate sparse regions absent.

Always examine the final IR for late-write conflicts. Common failures are a window frame overwriting a door, a roof overwriting upper headroom, a fixture overwriting a route cell, or a weathering pass replacing an anchor floor.

## Bedrock encoding

The bundled encoder writes little-endian NBT. Bedrock structure indices are Z-fastest, then Y, then X:

```text
flat = x * size_y * size_z + y * size_z + z
```

Static round trips alone did not originally establish this order; it requires an asymmetric BDS sentinel. The portable compiler nevertheless reopens every output using an independent reader and compares the full volume before issuing a static receipt.

The bundled default block runtime version is `18168865`, inherited from the proven development lane. Treat it as version-bound configuration: requalify against the target BDS release before claiming compatibility with a different runtime.
