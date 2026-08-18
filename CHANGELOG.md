# Changelog

## 0.3.0 - 2026-08-18

- Add palette-independent `topology` fingerprints invariant to translation and horizontal rotation/reflection.
- Add a `portfolio` audit that detects repeated architectural topology across multiple Blueprints.
- Add optional purpose contracts requiring approach, entry, and departure-change answers plus at least two distinctness axes.
- Preserve explicit-air versus void semantics in topology comparison and keep visual/gameplay/worldgen claims explicitly excluded.
- Extend the standalone starter tests, deterministic package gate, documentation, and skill workflow for portfolio review.

## 0.2.0 - 2026-08-17

- Add bounded `aionstruct.plan.v1` semantic authoring for foundations, rooms, openings, gable roofs, stair runs, anchors, and connectors.
- Add deterministic dependency-graph lowering to ordinary Blueprint v1 plus a hash-bound component source map.
- Add structured Plan diagnostics and a semantic roadside-house example.
- Add non-mutating `materials`, `layers`, `fingerprint`, and `diff` commands.
- Preserve the exact Wayfarer's Hearth Blueprint-v1 `.mcstructure` bytes with a golden regression test.
- Require byte-identical plugin packaging in CI.

Plan v1 alpha does not yet include assemblies, instances, repeat, sections, transforms, imports, project registries, or automated benchmark suites.
