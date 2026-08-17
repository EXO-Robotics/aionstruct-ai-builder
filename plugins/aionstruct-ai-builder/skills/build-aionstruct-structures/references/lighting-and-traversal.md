# Lighting and traversal

## Traversal

Derive walkable cells from final IR: a supporting cell below plus the declared number of clear air cells at feet and head levels. Use three-block headroom by default.

Require:

- every required anchor is walkable and reachable from the start anchor;
- no unintended walkable component or decorative floor island remains;
- primary and service route bands retain their promised width;
- full-depth apertures remain explicit air after all later operations;
- every stair tread has support, three-block clearance, a legal one-block transition, and connected landings;
- furnishings and fixtures do not consume protected route cells.

Do not infer a route from room adjacency or comments. Test coordinates in expanded IR.

## Lighting zones

Use separate zones:

- `showcase_safe`: public routes and architecture, normally static estimate `>= 8`;
- `spawn_enabled`: deliberately hostile floors, fail-closed maximum `0` until exact entity rules are known;
- `transition`: bounded threshold between safe and hostile space;
- `scenic_dark`: visually dark but made non-spawnable by verified geometry or floor treatment.

Light values are `0..15`. For an unobstructed source:

```text
estimate = max(0, emission - |dx| - |dy| - |dz| - attenuation)
```

Multiple sources use the maximum arriving value, never a sum. Geometry can attenuate or block real propagation; this estimate is deliberately optimistic.

## Fixture support

Record the exact source block, states, coordinate, emission, and support coordinate.

- standing lantern: solid support below;
- hanging lantern: solid support above;
- wall fixtures: backing on the state-directed face;
- carpets, plates, and plants: support below;
- doors and tall plants: both halves and clearance;
- sand, gravel, and concrete powder: deliberate support or an explicit falling intent;
- fluids: explicit containment.

Prefer visible sources on architectural edges, tables, shelves, plinths, and stair newels. Do not conceal sources merely to make a static metric pass.

Static coverage proves only that the optimistic estimator covers the declared final-IR floors. Runtime light sampling, mob-spawn observation, and day/night/rain client review remain separate gates.
