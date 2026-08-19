---
name: build-aionstruct-structures
description: Plan, design, audit portfolios, preview, and compile original Minecraft Bedrock structures with the offline AIONSTRUCT JSON pipeline, or adapt its semantic architecture workflow for Unreal Engine qualification. Use for AI structure development involving semantic rooms, clone detection, exploration-purpose contracts, traversal, supported lighting, engineering views, deterministic .mcstructure output, UE MCP placement evidence, measured lighting heatmaps, or Grok-guided art direction.
---

# Build AIONSTRUCT Structures

Create architecture as constrained semantic data, lower it to the frozen Blueprint vocabulary, inspect the final voxels, and compile only after spatial quality passes. Keep static, BDS, client, gameplay, world-generation, and console evidence separate.

## Start safely

1. Inspect the target repository and preserve unrelated or dirty work.
2. Locate the plugin root two directories above this skill directory.
3. If no AIONSTRUCT runtime exists, bootstrap the packaged starter into a new empty directory:

```bash
python3 <plugin-root>/scripts/bootstrap_project.py <new-project-directory>
```

4. Run `python3 tools/aionstruct.py doctor` in the project. Install `requirements.txt` only when PNG previews are required and the dependency is missing.
5. Read [workflow.md](references/workflow.md) before authoring. Use [plan-format.md](references/plan-format.md) for new semantic designs. Read [portfolio-audits.md](references/portfolio-audits.md) when producing or reviewing multiple structures. Read [blueprint-format.md](references/blueprint-format.md) when inspecting lowered source or maintaining a legacy Blueprint. Read [lighting-and-traversal.md](references/lighting-and-traversal.md) for enclosed or multi-level Bedrock builds. Read [unreal-engine-mcp-and-grok.md](references/unreal-engine-mcp-and-grok.md) when adapting plans to Unreal, operating a UE MCP server, measuring target-world lighting, or using Grok for art direction. Read [evidence-and-bds.md](references/evidence-and-bds.md) before making qualification or shipping claims.

## Authoring loop

1. Freeze the envelope, datum, silhouette, room program, route widths, headroom, exits, anchors, apertures, lighting zones, palette budget, and exclusions in sidecar contracts.
2. For a new build, draft a strict `.aionplan.json` with stable component IDs and explicit dependencies. Run `plan validate`, then `plan lower`. Keep intended clearance as explicit `minecraft:air`; leave untouched terrain absent as void.
3. Validate the lowered `.blueprint.json`, then run `expand`. Inspect final IR rather than trusting component names or operation comments. Existing Blueprint v1 sources remain supported directly.
4. Require every intended walkable cell and anchor to share the declared traversal component. Verify full-depth apertures, stair support/headroom/landings, and support-sensitive fixtures.
5. Render core SVGs, the isometric engineering board, and the static lighting heatmap. Review massing and cutaways visually.
6. Run the static quality contract. Fix failed gates in the source; do not weaken contracts to make a design pass.
7. For a multi-structure slate, run the portfolio audit and redesign any unintended topology clone; palette changes alone do not count as a new layout.
8. Compile `.mcstructure` bytes and require independent full-volume decode equality.
9. Qualify the exact artifact separately in a fresh, digest-pinned, portless BDS fixture before claiming runtime placement or persistence.

Use the packaged end-to-end command after the source and contract exist:

```bash
python3 tools/aionstruct.py build path/to/structure.aionstruct.json \
  --contract path/to/structure.quality.json
```

For a Plan source, lower it first:

```bash
python3 tools/aionstruct.py plan validate path/to/structure.aionplan.json
python3 tools/aionstruct.py plan lower path/to/structure.aionplan.json
python3 tools/aionstruct.py build build/structure.blueprint.json \
  --contract path/to/structure.quality.json
```

## AI collaboration rules

- Treat model output as an architectural proposal, never as proof.
- Require the model to return dimensions, room bounds, routes, apertures, anchors, palette roles, fixture coordinates/support, exclusions, and acceptance tests.
- Translate proposals into supported Plan components and dependencies; reject invented fields. Use Blueprint operations directly only when Plan v1 cannot yet express the design.
- Treat source-map output as traceability for lowering, not voxel or runtime proof.
- Detect conflicts in final IR, especially windows versus doors, furniture versus routes, roofs versus upper rooms, and fixtures versus headroom.
- Preserve source, contract, IR, preview, compile-receipt, and artifact hashes.

For an Unreal target, keep AIONSTRUCT as semantic authoring/static-analysis authority and use a separate import, map, collision, lighting, PIE, and human-review evidence chain. The Bedrock compiler does not emit Unreal assets.

## Fail closed

Stop static promotion when validation fails, any required anchor is unreachable, intended walkable islands remain, an aperture is partially overwritten, a fixture lacks support, lighting coverage is incomplete, preview hashes are stale, or independent decode differs.

Never describe static light math as runtime lighting, darkness as spawn proof, a decoded file as BDS placement proof, or a server check as client/console/release proof.
