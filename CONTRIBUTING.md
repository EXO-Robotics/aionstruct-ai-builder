# Contributing

Keep changes deterministic, bounded, and evidence-labeled.

Before opening a pull request:

```bash
python3 plugins/aionstruct-ai-builder/scripts/self_test.py
python3 plugins/aionstruct-ai-builder/scripts/package_plugin.py --output /tmp/aionstruct-ai-builder.zip
```

Codex plugin maintainers should also run the bundled plugin and skill validators from their local Codex installation.

Requirements:

- Preserve explicit air versus void behavior.
- Preserve Bedrock index order `x * size_y * size_z + y * size_z + z`.
- Add a regression test for compiler, schema, traversal, support, or rendering changes.
- Preserve Blueprint v1 and IR v1 canonical behavior when extending the semantic Plan layer.
- Require deterministic dependency ordering and complete Plan-to-Blueprint source-map coverage.
- Never weaken a quality contract merely to make a structure pass.
- Keep BDS, client, gameplay, world-generation, and console claims separate from static evidence.
- Do not add copyrighted Minecraft assets or copied third-party structure layouts.
