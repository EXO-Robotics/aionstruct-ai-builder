# AIONSTRUCT workflow

## Contents

1. Project layout
2. Commands
3. Constraint contract
4. Design iterations
5. Review checklist

## Project layout

The packaged starter is self-contained:

```text
aionstruct/
  examples/
  schemas/aionstruct.blueprint.v1.schema.json
  schemas/aionstruct.plan.v1.schema.json
  schemas/aionstruct.portfolio.v1.schema.json
tools/
  aionstruct.py
  aionstruct_plan.py
  aionstruct_validate.py
  aionstruct_expand.py
  aionstruct_quality.py
  render_aionstruct_preview.py
  render_aionstruct_isometric.py
  render_aionstruct_lightmap.py
  lib/
requirements.txt
```

Generated output uses `build/`, `dist/`, and `reports/`. Keep authored blueprints and contracts outside generated directories.

## Commands

Run from the project root:

```bash
python3 tools/aionstruct.py doctor
python3 tools/aionstruct.py plan validate aionstruct/examples/semantic_roadside_house.aionplan.json
python3 tools/aionstruct.py plan lower aionstruct/examples/semantic_roadside_house.aionplan.json
python3 tools/aionstruct.py validate aionstruct/examples/wayfarers_hearth_house.aionstruct.json
python3 tools/aionstruct.py expand aionstruct/examples/wayfarers_hearth_house.aionstruct.json
python3 tools/aionstruct.py preview aionstruct/examples/wayfarers_hearth_house.aionstruct.json \
  --contract aionstruct/examples/wayfarers_hearth_house.quality.json
python3 tools/aionstruct.py quality aionstruct/examples/wayfarers_hearth_house.aionstruct.json \
  --contract aionstruct/examples/wayfarers_hearth_house.quality.json
python3 tools/aionstruct.py compile aionstruct/examples/wayfarers_hearth_house.aionstruct.json
python3 tools/aionstruct.py build aionstruct/examples/wayfarers_hearth_house.aionstruct.json \
  --contract aionstruct/examples/wayfarers_hearth_house.quality.json
python3 tools/aionstruct.py materials build/semantic_roadside_house.blueprint.json
python3 tools/aionstruct.py layers build/semantic_roadside_house.blueprint.json
python3 tools/aionstruct.py fingerprint build/semantic_roadside_house.blueprint.json
python3 tools/aionstruct.py topology build/semantic_roadside_house.blueprint.json
python3 tools/aionstruct.py portfolio first.blueprint.json second.blueprint.json \
  --contract aionstruct/examples/example_portfolio.aionportfolio.json
python3 tools/aionstruct.py diff left.blueprint.json right.blueprint.json
```

`plan lower` writes an ordinary Blueprint v1 file and a hash-bound component-to-operation source map. `compile` writes deterministic `.mcstructure` bytes, reopens them through an independent NBT reader, compares the full volume, and writes a receipt. Neither command contacts Minecraft.

`portfolio` compares final explicit-cell topology after removing palette identity, translation, and horizontal rotation/reflection. It preserves explicit air as distinct from absent void. Use it to catch recolored or reoriented clones, not to claim visual quality or player memorability.

## Constraint contract

Write the contract before voxels. Include:

- envelope and local ground datum;
- intended visual identity and ordered silhouette masses;
- named rooms with bounds, entrance, focal feature, circulation anchor, furnishing intent, and minimum usable floor;
- public, service, vertical, escape, and encounter routes with minimum widths and headroom;
- full-depth aperture prisms;
- external anchors and connectors;
- lighting zones and exact source strategy;
- palette roles, maximum primary-material ratio, and minimum material variety;
- entity, block-entity, terrain, rotation, gameplay, performance, and release exclusions.

Use a separate program sidecar for architectural intent and a quality sidecar for machine gates. Bind both to the exact blueprint identifier.

## Design iterations

Work outside-in, then inside-out:

1. Compose three to six major masses with different heights/depths.
2. Establish roof hierarchy and landmark silhouette.
3. Carve rooms and full-depth connections.
4. Add floors and a conservative full-block stair before decorative geometry.
5. Add facade depth, framed apertures, structural rhythm, and furnishings.
6. Reserve protected route cells before selecting lights.
7. Place supported visible fixtures on route edges, tables, shelves, newels, or masonry plinths.
8. Expand and inspect. Correct collisions by architectural priority, not operation order accidents.

## Review checklist

- Does the exterior read as the requested building type from two opposing isometric views?
- Are roof tiers and projections legible rather than one box with trim?
- Does every room have a reason to exist and a route to reach it?
- Are all intended walkable cells connected, including bays and exterior returns?
- Are primary routes clear at their promised width?
- Are stairs traversable at every step with full headroom?
- Are doorways full-depth after every later write?
- Are windows on exterior faces rather than blocking internal doors?
- Does every lantern or support-sensitive block retain its backing cell?
- Is explicit air used only for intended replacement/clearance?
- Do previews and reports hash-bind the source they depict?
