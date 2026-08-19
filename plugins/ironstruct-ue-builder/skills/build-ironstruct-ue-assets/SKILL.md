---
name: build-ironstruct-ue-assets
description: Plan, build, place, and qualify semantic structures for Unreal Engine with IronStruct. Use for Grok-guided architectural art direction, dimensioned layouts and layers, Blender GLB or FBX exchange, UCX collision, UE MCP map operations, marker alignment, lighting heatmaps, tester-world iteration, or evidence-gated production promotion. Do not use for Minecraft Bedrock compilation.
---

# Build IronStruct Unreal Assets

IronStruct is an Unreal-focused workflow. Keep it separate from AIONSTRUCT's Bedrock schemas, compiler, `.mcstructure` output, plugin identity, and skill.

## Core workflow

1. Turn the art brief or Grok reference into a dimensioned semantic plan with stable component IDs, layers, routes, apertures, anchors, material roles, collision roles, and acceptance tests.
2. Generate or author the asset in Blender with an explicit datum, units, axes, pivot, sockets, material slots, and uniquely numbered UCX proxies.
3. Import into an isolated Unreal tester world and independently read back the asset, actor, bounds, transform, collision, marker, and dirty-package state.
4. Review fixed cameras at player scale, run capsule and navigation checks, measure lighting on a fixed grid, and iterate from source rather than patching anonymous map geometry.
5. Promote only qualified assets through guarded UE MCP mutation with a map backup, exact ownership tags, saved readback, map hash, runtime-duplication canary, PIE lifecycle evidence, and explicit deferred human tests.

Read [the Unreal Engine, MCP, lighting, and Grok field guide](references/unreal-engine-mcp-and-grok.md) before operating UE, directing concept-art iterations, authoring collision, calibrating lighting, or promoting a tester asset.

## Proof boundaries

- A concept image proves visual intent, not geometry or gameplay.
- A semantic plan proves authored structure and dependencies, not imported assets.
- An exchange-file check proves file contents, not Unreal interpretation.
- Editor readback proves saved packages and actors, not PIE behavior.
- PIE audits prove only their observed contracts, not human traversal, fairness, comfort, or final art quality.

Fail closed on wrong project or map identity, active PIE during editor mutation, unexpected dirty packages, duplicate ownership, transform-frame ambiguity, missing collision, stale receipts, runtime proxy overlap, or unbound map/save evidence.
