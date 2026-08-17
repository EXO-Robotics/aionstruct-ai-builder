# Plan v1 format

Use `aionstruct.plan.v1` as the semantic authoring layer for new structures. Plan v1 is deliberately small: it adds architectural components and dependency order without changing Blueprint v1, voxel IR v1, or the Bedrock writer.

## Components

Every component has a unique stable `id`, a strict `kind`, and optional `depends_on` and `comment` fields. The alpha vocabulary is:

- `foundation`: one bounded solid base;
- `room`: walls, floor, ceiling, and explicit-air interior;
- `opening`: a doorway, window, or arch hosted by a room;
- `roof`: a bounded gable hosted by a room;
- `stair_run`: one ordinary Blueprint stair run;
- `anchor`: a named local traversal or discovery point;
- `connector`: a bounded exterior attachment face.

Coordinates are inclusive local `[x,y,z]` points. A room's bounds include its shell. Its X, Y, and Z spans must each be at least three blocks so the lowerer can emit a real interior.

## Dependencies

Dependencies are architectural overwrite order. Openings and roofs must name a `host`, and that host must also appear in `depends_on`. Independent ready components are lowered by lexical component ID, making output canonical even if the JSON component array is reordered.

Use dependencies whenever later geometry intentionally cuts or overwrites earlier geometry. Missing references, duplicate IDs, self-dependencies, and cycles fail before Blueprint emission.

## Lowering and source maps

```bash
python3 tools/aionstruct.py plan validate aionstruct/examples/semantic_roadside_house.aionplan.json
python3 tools/aionstruct.py plan lower aionstruct/examples/semantic_roadside_house.aionplan.json
```

Validation emits stable JSON diagnostics with `code`, `severity`, `message`, `path`, and, when known, `component_id`.

Lowering emits:

- an ordinary `aionstruct.blueprint.v1` document containing only existing supported operations;
- an `aionstruct.plan_source_map.v1` sidecar binding Plan and Blueprint hashes and mapping every component to generated operation indices.

The source map is authoring provenance only. It is not voxel equality, `.mcstructure`, BDS, client, or gameplay evidence.

## Alpha boundary

Plan v1 alpha does not implement assemblies, instances, repeat, sections, rotation, mirroring, arbitrary transforms, imports, or a general module operation. Compose those explicitly in Blueprint v1 until a future Plan generation defines state-safe transform behavior and collision policy.

Use the non-mutating inspectors after lowering:

```bash
python3 tools/aionstruct.py materials build/semantic_roadside_house.blueprint.json
python3 tools/aionstruct.py layers build/semantic_roadside_house.blueprint.json
python3 tools/aionstruct.py fingerprint build/semantic_roadside_house.blueprint.json
python3 tools/aionstruct.py diff left.blueprint.json right.blueprint.json
```
