# HD2 Dress: status for a new maintainer (2026-10-29, version 0.6.24)

Read this first, then [PROJECT_LOG.md](PROJECT_LOG.md) for detail (the release list near the top has one entry per
version with what was measured). Tests: `tests/run_tests.sh [blender]`, 27/27 on Blender 5.2.2 and 4.0.2 (needs your own
test scene, see [../tests/README.md](../tests/README.md)).

## How it works (one paragraph)

The stock cape's cloth resource (`hclClothData`, Havok tagfile, in game archive `18235e0c9ec0e636`, id
`3c33cf10a26cbb3e`) is the template. For the author's armour unit, `tools/gen_engine_cloth.py` builds particles from the
cloth vertices, links/stretch/bend/leash constraints, pins (skinned to the unit's bones), the cape's body colliders
(capsules on the diver bones, resized by Body fit), and a "render copy" (the engine's copy of the display mesh, written
in a Stingray tail block after the Havok data). `tools/hd2dress_cloth.py` puts that resource, keyed by the unit id, into
patches of the unit's archives and of the author's armour patch, and (colour-map look) builds a character-shader
material from the author's textures.

## Engine facts learned (all verified in game)

- A mesh that carries cloth is drawn with **one material: its first**. Cloth needs a unit of its own with one material.
- The cloth must also sit in the **archive of the author's armour patch** (where the modded unit lives); with it only in
  the unit's original archive the store preview froze and one mod crashed the game.
- Patch TOC entries must not sit at odd offsets: HD2SDK packs TOC data unaligned, and a misaligned cloth entry made the
  game ignore the whole patch. `tools/align_patch.py`; the build aligns every patch.
- Wind: `hclSimClothData.totalMass` is the sum of the free particle masses (stock cape 854 x 0.003 = 2.562); the engine's
  wind acceleration goes with 1/totalMass. The build writes real mass / wind. The engine's wind code also uses particle
  0's mass for every particle, so particle 0 must be free (the generator swaps one in).
- A collider the cloth STARTS deep inside shoves those points every frame (jitter). The build shrinks such capsules
  (auto fit); a few points resting on a collider are fine.
- Near-singular bend hinges (three pinned points, the free one barely involved) produce enormous stiffness values and
  fling single vertices hundreds of metres; the generator skips and clamps them (0.6.24).
- Meshes on a moved node (many armours keep a mesh's origin away from zero): the physics runs without the node offset,
  the drawing adds it. Fix all moves the node to the origin (and its armature bone, which HD2SDK writes back on export).
- Substeps above 1 render garbage on cloned divers, the stock capes too. Kept at 1.
- Bones added to a unit by Fix all (knees, chest on a hip unit) are not animated by the game: they ride along from
  their parent.

## Open problems

1. **Cloned divers draw the cloth as huge spikes** (loadout terminal, armour screen, mission loadout). Seen with every
   HD2 Dress cloth tested. Ruled out: LOD copies on the cloth material, duplicate cloth in two archives, substeps.
   A memory read found one live cloth instance only: clones probably draw from the real diver's cloth. Unconfirmed.
   Compare with how the stock cape's clone rendering is set up.
2. **More than one material on a cloth mesh.** The render copy describes one draw batch (no stock example of more:
   all three stock cloths use one material). Options considered: pack textures into one (no tiling), split parts
   across units driven by one simulation, or add mesh slots to the unit outside HD2SDK. See the 2026-10-24 entries in
   PROJECT_LOG.md. Today: a Check PROBLEM and a guide rule.
3. **Wind on big cloths** may still feel stronger than the cape (more area per mass). Tune if authors report it.
4. **Keep my material** puts the author's textures and values on the full character template (HD2SDK-made materials
   carry about half the shader values and no IgnoreSkinning switch). Worth re-testing on a one-material unit.
5. The store preview shows cloth static (no physics). Harmless.

## Not in this repository

- Game files and test fixtures (made from game assets): make your own, see tests/README.md.
- Reverse-engineering and live-memory tools used during research (they read or write a running game that has
  anti-cheat; publishing them is a ban and ToS risk for users). The findings are in PROJECT_LOG.md.
- Old builds: see Releases.
