# Portfolio uniqueness and purpose

Use a portfolio audit when a slate contains multiple structures or material variants. The audit operates on validated, expanded Blueprint final IR rather than filenames, comments, or component labels.

```bash
python3 tools/aionstruct.py portfolio \
  aionstruct/structures/*.blueprint.json \
  --contract aionstruct/contracts/region.aionportfolio.json \
  --output reports/region.portfolio-audit.json
```

The topology fingerprint treats every non-air block as solid, preserves explicit air, leaves absent coordinates as void, removes empty translation margins, and chooses a canonical form across the eight horizontal rotations/reflections. Consequently, palette swaps and orientation changes do not manufacture new architectural layouts.

Each contract row answers:

- why a player would walk toward the structure;
- why they would enter;
- what changes after departure;
- which two or more axes differ: silhouette, approach, traversal, function, or environmental story.

One representative may intentionally define a material-variant family. Do not submit multiple family members to the same uniqueness gate unless identical topology is meant to fail. If repetition is intentional, separate the family-variant inventory from the distinct-layout portfolio instead of weakening the fingerprint.

A passing report proves static topology distinctness and authored contract completeness only. It does not measure aesthetics, reward quality, gameplay memorability, natural placement, or client rendering.
