# AIONSTRUCT AI Builder

A Codex plugin and standalone offline toolkit for AI-assisted Minecraft Bedrock structure development—without Minecraft Editor and without driving a player to place blocks.

**[Explore the castle and house showcase →](https://exo-robotics.github.io/aionstruct-ai-builder/)**

![Wayfarer's Hearth engineering board](plugins/aionstruct-ai-builder/assets/screenshots/wayfarers-hearth-board.png)

## What it does

- Converts strict, finite JSON blueprints into deterministic final voxel IR.
- Checks traversal, full-depth apertures, stair clearance, fixture support, lighting coverage, material balance, and stale previews.
- Renders top-down, floor, elevation, isometric, cutaway, and static-light engineering views.
- Compiles little-endian `.mcstructure` bytes using Bedrock's Z-fastest index order.
- Reopens and compares every compiled voxel with an independent NBT reader.
- Preserves explicit air separately from structure void.
- Keeps static, BDS, client, gameplay, world-generation, and console evidence separate.

The repository includes the multi-level **Wayfarer's Hearth House** as an editable reference project.

## Install in Codex

```bash
codex plugin marketplace add EXO-Robotics/aionstruct-ai-builder --ref main
codex plugin add aionstruct-ai-builder@aionstruct
```

Start a new Codex task, then ask:

```text
Use $build-aionstruct-structures to design and validate an original Bedrock roadside inn.
```

## Use as a standalone toolkit

Create a clean project:

```bash
python3 plugins/aionstruct-ai-builder/scripts/bootstrap_project.py ./my-structure-project
cd my-structure-project
python3 -m pip install -r requirements.txt
```

Build the included example:

```bash
python3 tools/aionstruct.py build \
  aionstruct/examples/wayfarers_hearth_house.aionstruct.json \
  --contract aionstruct/examples/wayfarers_hearth_house.quality.json
```

The command writes deterministic IR, `.mcstructure` bytes, a full-volume decode receipt, engineering previews, and a static quality report.

## Commands

```bash
python3 tools/aionstruct.py doctor
python3 tools/aionstruct.py validate <blueprint>
python3 tools/aionstruct.py expand <blueprint>
python3 tools/aionstruct.py preview <blueprint> --contract <quality-contract>
python3 tools/aionstruct.py quality <blueprint> --contract <quality-contract>
python3 tools/aionstruct.py compile <blueprint>
python3 tools/aionstruct.py build <blueprint> --contract <quality-contract>
```

## Evidence boundary

A successful offline build proves strict source validation, deterministic expansion, static spatial analysis, optimistic light coverage, deterministic encoding, and independent decode equality. It does **not** prove BDS placement, runtime light, mob spawning, client appearance, terrain fit, multiplayer behavior, console compatibility, or release readiness.

Qualify exact compiled bytes separately in a disposable, digest-pinned Bedrock Dedicated Server before making runtime claims.

## Development

```bash
python3 plugins/aionstruct-ai-builder/scripts/self_test.py
python3 plugins/aionstruct-ai-builder/scripts/package_plugin.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for validation expectations.

## License

MIT

Minecraft is a trademark of Microsoft. This independent project is not affiliated with or endorsed by Microsoft or Mojang.
