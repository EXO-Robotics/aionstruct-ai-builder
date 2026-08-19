# IronStruct Unreal Engine, MCP, lighting, and Grok field guide

## Scope and proof boundary

IronStruct is a separate Unreal-focused workflow. It borrows the useful idea of semantic structure plans, but it does not use AIONSTRUCT's Bedrock compiler, schemas, package identity, or `.mcstructure` output. IronStruct carries rooms, routes, apertures, anchors, layers, lighting zones, and purpose contracts through a Blender/GLB/FBX and Unreal qualification pipeline.

Keep these claims separate:

- the semantic plan proves authored intent and dependency order;
- Blender export proves only exchange-file contents;
- Unreal editor readback proves imported packages, actors, transforms, materials, and collision configuration;
- a saved-map hash proves the exact map bytes that were written;
- PIE audits prove only the runtime contracts they actually observe;
- screenshots and analytical heatmaps support visual review but do not prove human traversal, navigation, exposure comfort, or gameplay fairness.

Do not promote an asset because its concept image is attractive or because it imports without errors. Require a dimensioned plan, collision readback, player-scale review, runtime duplication check, and target-world lighting/traversal evidence.

## Translate the semantic plan for Unreal

Preserve semantic structure rather than exporting anonymous merged geometry:

- stable component IDs for foundations, floors, shells, roof masses, porches, ladders, walkways, doors, windows, and dressing zones;
- explicit dependencies and exclusions;
- player and AI route bands with widths, headroom, steps, landings, apertures, and escape paths;
- anchors and sockets for objectives, lights, audio, doors, hiding, traversal, and VFX;
- material roles rather than final colors alone;
- lighting zones and sample points;
- collision roles: walkable support, shell blocker, thin post/rail, interaction volume, and visual-only detail;
- a local datum, units, axes, pivot, and intended world transform.

Create top-down, elevation, section/cutaway, layer reveal, component schedule, and light-intent views before mesh generation. These expose layout defects that a single cinematic render hides.

Treat semantic markers as data. Plain Unreal `AActor` markers are inert until gameplay code or a Blueprint consumes their tags or IDs. A marker's presence is not interaction proof.

## Grok as an art-direction partner

Grok is most useful before and between deterministic build passes. It is strong at quickly exploring mood, silhouette, material language, prop density, weathering, and visual storytelling. It is not a geometry, collision, scale, or gameplay authority.

### Give Grok a production brief, not a vague image prompt

Provide:

- game genre, biome, time of day, weather, and emotional target;
- building purpose and the story it should communicate from a distance;
- player height and real dimensions;
- required entrances, exits, rooms, objectives, hiding places, and traversal lanes;
- hero silhouette masses and which mass must dominate;
- material families, age, damage, and maintenance history;
- prop-density zones and deliberately empty navigation zones;
- light-source locations, color-temperature intent, dark zones, and objective readability;
- negative constraints such as no fantasy ornament, no modern hardware, no blocked doorways, no impossible cantilevers, and no texture-only fake structure;
- requested deliverables: opposing isometrics, top-down layout, front/side elevations, cutaway, material callouts, prop list, and lighting pass.

Ask for several structurally different variants. Reject variants that change only palette, trim, fog, or camera angle. A portfolio needs distinct topology, approach, entry sequence, landmark, and departure experience.

### Convert the chosen image into build data

For every accepted concept, write down:

1. envelope, datum, pivot, dimensions, and player-scale reference;
2. named masses and their ordered silhouette hierarchy;
3. room and exterior-zone bounds;
4. route widths, headroom, door and window apertures, stairs, ladders, and landings;
5. component IDs, dependencies, repeated modules, and exclusions;
6. material slots and procedural-versus-textured intent;
7. objective, light, audio, hiding, interaction, and VFX anchors;
8. collision roles and expected convex counts;
9. acceptance tests and the views needed to judge them.

Do not trace perspective pixels into final dimensions. Infer a coherent plan, then render that plan back from matching angles and compare it with the reference.

### Iterate in a tester world

Place new work in an isolated Unreal qualification map first. Use a stable actor namespace and predictable bays so reference, plan, mesh, and screenshot remain comparable.

A productive loop is:

1. Grok reference and variant sheet.
2. IronStruct plan, layers, and component schedule.
3. Blender generation and collision authoring.
4. Unreal import and exact actor readback.
5. Player-scale editor and PIE captures from fixed cameras.
6. Grok critique of the captures against the original brief.
7. Deterministic plan or material revision.

Use Grok critiques for observations such as "the roof mass no longer dominates" or "the porch lacks a readable entry rhythm." Convert each accepted observation into a measurable source change. Never let a model's aesthetic approval replace collision, traversal, lighting, or runtime gates.

Preserve prompts, accepted images, prompt revisions, and file hashes when available. Use original art direction; do not copy copyrighted structures or branded assets.

## Blender and exchange-file lessons

### Coordinate frames and marker transforms

Record the actual imported local frame. Do not assume plan axes survive Blender and GLB/FBX conversion unchanged.

One validated GLB pipeline mapped plan-local coordinates into Unreal as:

```text
UE local = (plan X, -plan Y, plan Z)
world = actor location + actor yaw rotation * UE local
```

This is a pipeline-specific observation, not a universal Unreal rule. Prove it with an asymmetric socket or bounds sample, then encode it in one shared transform helper. Derive semantic-marker positions from the same helper as the mesh.

In Unreal Python, `unreal.Rotator` positional order is roll, pitch, yaw. Prefer keyword arguments or an explicit named helper. A positional `Rotator(0, -8, 0)` pitches the actor; it does not apply yaw `-8`.

### UCX collision

Give every collision proxy a unique sequential name such as:

```text
UCX_SM_MyStructure_00
UCX_SM_MyStructure_01
```

Duplicate Blender names that become `.001`, `.002`, and so on may import as standalone meshes instead of attaching to the render mesh. After import, require:

- expected render-mesh cardinality;
- expected attached convex-element count;
- zero standalone `UCX_*` assets;
- expected collision-enabled mode and profile;
- a live player-capsule and navigation check.

Do not hide a combined structure from traversal queries merely because its floor is walkable. Ignoring the whole actor also hides walls, pillars, and rails. Split pure supports from blockers or use a ground-resolved audit that tests the standing capsule at the selected support height.

## Operate Unreal through MCP safely

Prefer narrow MCP tools over arbitrary Python or UI typing. A useful tool should declare its exact project, engine family, map, operation, expected inputs, mutation boundary, and receipt schema.

### Before mutation

1. Verify exact project file, engine version, editor map, and whether PIE/SIE is stopped.
2. Require the target map to be clean.
3. Inventory exact labels, classes, meshes, tags, folders, transforms, collision, and dirty packages.
4. Back up the exact `.umap` and record SHA-256, size, and modification time.
5. Allow one live Unreal writer. Keep reviewers and analyzers read-only.

### During mutation

- Use exact actor labels plus ownership tags and folders.
- Mutate only actors whose pre-state matches the receipt contract.
- Use explicit, named transform fields.
- Save only the intended map or package.
- Record before and after values; do not record the requested spec as if it were observed readback.
- Stop if duplicates, unexpected dirty packages, wrong project identity, or active PIE are found.

### After mutation

1. Read back the saved actor and asset state independently.
2. Hash the saved map.
3. Restart or otherwise ensure compiled native changes are actually loaded.
4. Start PIE through a guarded request, then poll live status until the exact PIE world is observed. A dispatched request is not completion proof.
5. Run narrow audits and canaries.
6. Stop PIE through a guarded request and poll until the editor is demonstrably stopped.
7. Compare map and active-save identities before and after PIE.

Keep the raw MCP ledger. Bind submitted audit receipts to the exact tool responses rather than copying only PASS strings into a summary.

Avoid direct text entry while the PIE viewport has focus. Gameplay bindings can interpret command text as player input. If a console-only script is unavoidable, use a calibrated real click on the console field, clipboard paste, visual confirmation, and then Return. Record any accidental gameplay mutation and invalidate the affected immutability run.

### Runtime duplication

Editor placement can coexist with transient runtime spawners. Search gameplay code and PIE actors for old proxy structures before promotion. Suppress only the exact duplicate call or add a narrow production-presence guard; retain unrelated workyards, props, and effects.

## Unreal lighting heatmaps and calibration

### Separate three kinds of evidence

1. **Design-intent heatmap:** normalized falloff from planned fixtures. Useful before Unreal placement; not a measurement.
2. **Saved-light analytical field:** calculated from the read-back Unreal transforms, lumens, inverse-square falloff, attenuation radius, sample surface, and zones.
3. **Rendered target-world review:** fixed exposure, actual materials, fog, shadows, indirect lighting, post processing, and player camera in editor and PIE.

Never label the first two as calibrated physical lux readings. A Visibility-channel trace is a collision diagnostic, not equivalent to rendered shadowing. Analytical fields do not include Lumen bounce, BRDF, bloom, eye adaptation, or tone mapping.

### Inspect the whole world first

If a location is too bright, inventory every active directional light, skylight, fog actor, post-process volume, and exposure override before reducing the local fixture. In one field case, seven directional repair lights, five skylights, and three fog actors were stacked. The stack—not the porch-light placement—was the main brightness defect.

Consolidate superseded global rigs or disable them with evidence. Do not delete uncertain content. Lock exposure for comparable captures; otherwise auto exposure can make two different light fields look deceptively similar.

### Measure zones, not one point

Define a fixed sample plane and named zones such as threshold, porch, approach, objective, hazard, and scenic dark. Store median and p95 limits. Use the same grid and fixed color scale for before/after heatmaps.

For an ideal isotropic point light using lumens and an Unreal-style radius fade:

```text
candela = lumens / (4 * pi)
horizontal_lux = candela * max(dot(surface_normal, direction_to_light), 0)
                 / distance_m^2 * radius_fade
radius_fade = max(1 - (distance / attenuation_radius)^4, 0)^2
```

Search intensity and attenuation radius together. Increasing lumens alone can fix a doorway while leaving the approach outside the attenuation radius; increasing only radius can flatten the scene. Favor the lowest-energy candidate that satisfies every zone median and p95 contract.

An illustrative rural-horror porch calibration began at 900 lumens per light and looked floodlit. A 195-point grid found 260 lumens with an 800 cm radius as a better qualified pair: the threshold median fell near 3.9 lux, porch near 2.7, and approach near 0.33 while p95 limits remained bounded. These values describe one scene, not reusable defaults.

Keep emissive mesh strength separate from point-light energy. A bright emissive material can look clipped without making the route readable. In the same case, reducing emissive strength from 24 to 8 improved fixture appearance while the point lights carried navigation.

### Accept lighting only with paired evidence

Require:

- exact saved light transforms and settings;
- a global-light inventory;
- fixed-scale heatmap plus zone statistics;
- locked-exposure editor captures;
- target-world PIE captures;
- objective and hazard readability checks;
- performance evidence after lights, fog, and shadows are active.

Then repeat the measurement across the full gameplay route. Local porch success does not prove forest, marsh, sawmill, bridge, or interior readability.

## Practical visual lessons

- High-contrast procedural noise quickly reads as camouflage. Remap noise to a restrained range and use related base/accent colors.
- Material separation should reinforce silhouette, structure, and wear history rather than cover every surface with variation.
- Solid colors are acceptable during blockout when value hierarchy is intentional. Add a small material family before adding a large texture library.
- Use physical fixture meshes and player-scale reference; a floating point light alone gives weak visual authorship.
- Keep objective lights, safe lights, ambience, and hazard lights semantically distinct so they can be measured and tuned separately.
- Review the developed POI against neighboring locations. One polished building can make the rest of the world read as unfinished even when it is individually attractive.

## Promotion checklist

- Concept variants are topologically and functionally distinct.
- Chosen concept has dimensions, layers, routes, anchors, material roles, and negative constraints.
- Exchange file has the intended frame, pivot, scale, sockets, and unique UCX names.
- Unreal import has exact assets, collision counts, labels, tags, folders, and transforms.
- Semantic markers align with the imported local frame.
- Production placement does not overlap a transient runtime proxy.
- Local and global lighting inventories are known.
- Heatmap zones pass on a fixed scale and rendered captures remain readable at locked exposure.
- Live player capsule, navigation, and interaction tests remain separate required gates.
- Backups, hashes, MCP ledger, saved readback, PIE lifecycle, and proof boundaries are preserved.
