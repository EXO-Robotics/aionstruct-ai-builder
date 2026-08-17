# Evidence and BDS qualification

## Proof ladder

Keep claims at the narrowest completed layer:

1. Source validation: schema, bounds, operations, palette typing.
2. Final-IR analysis: traversal, apertures, support, materials, optimistic light.
3. Static artifact proof: deterministic encode, independent full-volume decode, hashes and receipts.
4. Disposable BDS proof: exact structure load, full-volume classification, air-versus-void sentinel, restart persistence.
5. Client review: exact pack at day, night, and weather; architecture, lighting, collision, and input.
6. Integrated gameplay/worldgen: terrain admission, rotation, multiplayer, mechanics, performance.
7. Physical console/release: platform-specific installation, controller, memory, rights, and publishing requirements.

Never collapse these layers into one “works in Minecraft” statement.

## Disposable server requirements

Use a fresh temporary world and behavior pack. Pin the BDS image by immutable digest, disable network unless required, publish no gameplay ports, use random container names, mount only the fixture, and remove the container after the run. Do not attach to a live development or production world.

For every compiled candidate:

- bind blueprint, compiler, `.mcstructure`, pack, image digest, and command hashes;
- use an asymmetric coordinate sentinel to catch axis/index mistakes;
- prefill explicit-air and nearby-void probes with a marker, then prove air clears while void preserves;
- scan the full volume for large or first-of-kind assets;
- verify stateful and support-sensitive blocks at realistic supported positions;
- restart and repeat stable signatures;
- record unreadable cells, mismatches, server logs, exit state, and exclusions.

Runtime success for one BDS version does not prove future block runtime versions or client appearance.

## AI and external models

An AI model may propose architecture, strict JSON, tests, or review findings. Treat all output as untrusted draft material. Keep private evidence and credentials out of external prompts. The repository owner or trusted agent must validate, edit, compile, and run authoritative gates.
