# Making a dress with engine cloth (no Lua): command line

> **Most authors want the Blender panel instead: see [GUIDE.md](GUIDE.md).** The panel writes the same settings file
> and runs the same build. This page is the command-line route and the full list of settings.

HD2 Dress engine cloth uses the game's own cloth physics (the system that moves the capes). Your armour piece gets
real swinging, draping fabric, and **players need no extra mod or script**: they install your armour patch and the
cloth patches the build makes. This guide walks through it for the "character shader" look (a normal colour texture,
the easiest route).

Read `ENGINE_CLOTH_VALUES.md` "How loose can you go" first: HD2's cloth has no self-collision, so long loose garments
can fold through themselves in extreme poses.

## What you need

- Blender with the HD2SDK Community Edition add-on (the same setup you use for armour mods)
- Helldivers 2 installed
- This repo (the tools in `tools/`)

## 1. Model the cloth (Blender)

Work in your normal HD2SDK armour scene.

1. **The cloth part is one layer.** No Solidify or separate inner wall (two sheets simulate apart). The cape shader
   draws both sides (a back layer flickers, "z-fighting squares"); the character (colour map) look draws the outside
   only: give it an exact reversed copy of the cloth faces (panel: Add back side; settings: cloth.allow_double_layer).
2. **Unwrap it properly.** Continuous UVs, like any textured mesh. Not every vertex on one UV point, and not Blender's
   default "each face fills the whole texture".
3. **Faces point outward.** (Recalculate Outside in Blender.)
4. **Mark the cloth.** Put every vertex that should move like cloth in a vertex group named `cloth`. The top row of each
   connected cloth piece (where it attaches, e.g. the waistband) is pinned to the body automatically.
5. **Weights:** skin the cloth to the bone it hangs from (e.g. `hips`), like a rigid part. The physics takes over from
   there.
6. **Lower LODs** (lod1, lod2, ...) must **not** use the cloth's material. Give them a normal armour material, or ship
   without auto LODs. (A cloth-material LOD draws garbage in the armory and loadout previews.)

## 2. Prepare the scene (prep tool)

```
blender -b MY_ARMOUR.blend -P tools/hd2dress_prep.py
```

It saves `MY_ARMOUR_hd2dress.blend` (your file is never changed) after it:

- adds the collision bones the cloth needs if your armature lacks them (knees, feet, spine, chest, neck, head,
  clavicles, shoulders, elbows), with the exact rest pose of the game's diver skeleton,
- makes sure the mesh has 3 UV sets,
- gives one cloth vertex a tiny `root` weight (the look needs `root` in the mesh's bone list),
- checks for a double layer, inward faces, a single-point UV map, and LODs using the cloth material.

Fix anything it reports, then **export your armour patch with HD2SDK as usual** from the `_hd2dress` file.

## 3. Write the settings file

Copy `examples/engine_cloth_testrig.toml` next to your project and edit it. The important parts:

```toml
cloth_name = "my_dress"                       # unique per mod
armour_patch = "9ba626afa44a3aa3.patch_0"     # the patch you exported in step 2
blend = "MY_ARMOUR_hd2dress.blend"

[[unit]]
id = "2f66b9373cb58485"                       # your armour unit (slim body)
mesh_name = "g_legs_hips_female"              # the mesh's node name in the unit
object = "Hip_Armor_Slim_lod0"                # its object in the .blend
[[unit]]                                      # and the stocky body version, if any
id = "0387a158d04848f4"
mesh_name = "g_legs_hips_male"
object = "Hip_Armor_Stocky_lod0"

[cloth]
vertex_group = "cloth"
strip_scene = true                            # default: empty the cape template scene (much smaller files)

[look]
shader = "character"
color = "my_dress_color.png"                  # your colour map (on the UVs from step 1)
normal = "my_dress_normal.png"                # optional normal map (OpenGL / Blender style)
roughness = 0.7                               # 0 glossy .. 1 matte
# weave = "fabric_weave_normal.png"           # optional fine fabric detail, tiled (keep weave_strength low, ~0.2;
#                                             # it can darken folded cloth because the base lighting is frozen)
# weave_tiling = 40
```

The physics values (`[sim]`, `[part]`, `[follow]`, `[planes]`, `[collision]`) start at the tested values; every key
is explained in the example file and in `ENGINE_CLOTH_VALUES.md`. Tight garments: use a small `leash` (the cape uses
about 0.02 m). Long skirts: a large leash so the legs can move.

## 3b. Several pieces and pins

Instead of one `cloth` group, a garment can have **pieces**: vertex groups `cloth_<name>`, each with its own settings,
plus a `pin` vertex group for the vertices that stay on the body (a piece without pins hangs from its top row).

```toml
[cloth]
pin_group = "pin"

[[piece]]
group = "cloth_skirt"
follow_legs = true        # the hem follows the thighs (skirts); false for capes, hair, sleeves
leash = 1.0
stretch = 0.6
bend = 0.24
[[piece]]
group = "cloth_hair"
leash = 0.3
```

Each `[[unit]]` reads only its own object in the .blend (matched by HD2SDK's object id; or set `object = "..."`), and
`mesh_name` is looked up from HD2SDK's name list when you leave it out.

## 4. Build

```
blender -b -P tools/hd2dress_cloth.py -- build my_dress.toml
```

The build:

- makes the cloth for each unit (with your settings),
- finds every game archive that holds your armour unit (the cloth must sit in the unit's own archive),
- makes the material from your colour/normal maps (block-compressed),
- writes everything to `dist/other/<cloth_name>/` (or `out`), with `_debug/manifest.txt` listing each file.

With the character look, `9ba626afa44a3aa3.patch_0` in the output is **your armour patch with the cloth material added**:
ship it instead of your original armour patch, plus every cloth patch. Do not ship `_debug/`.

`--install` copies them into your own game folder for testing (it never overwrites another mod's patch; the material
goes to the next free patch slot of the base archive).

## 4b. Preview in Blender (optional)

```
blender -b MY_ARMOUR_hd2dress.blend -P tools/hd2dress_preview.py -- --settings my_dress.toml --object MyDressObject
```

Renders front/side/back images of your colour map, normal map, roughness and weave on the real UVs (Cycles, no game
needed). It shows texture placement and surface detail; it does not run the game shader or the cloth physics (the
cloth hangs in its modelled shape).

## 5. Test in game

- Walk, sprint, dive, kneel, and the emotes **Thumb of Approval** (thumbs up), **Squat** and **Front-Leaning Rest Position** (push-ups) (the hardest tests for skirts).
- Check the armory and the hellpod preview (cloned diver).
- Linux/Proton only: `tools/havok/re/livetune.py` changes leash, gravity, friction, bend and more in the running game,
  and `clothreset.py` drops the cloth fresh. On Windows, change the settings file and rebuild.

## Wind

`[sim] wind` (default 1): how strongly the game's wind blows the cloth. The Super Destroyer has a constant breeze; calm
planets have none. 0 = off, 1 = like the stock cape, 2 = double. (Engine detail: the game's wind code uses the mass of the
cloth's FIRST particle for every particle, so the generator always puts a free particle first; the strength goes through
hclSimClothData.totalMass, which only the wind code reads.)

## Limits to know

- **Substeps must stay 1.** Above 1 the game draws garbage on cloned divers (also with the stock capes).
- **Lighting does not follow the folds** with the character-shader look: the folds show by shape and shadow. Subtle
  shading painted into the colour or normal map helps.
- **No self-collision**: loose cloth can fold through itself in extreme poses.
- The cloth pins its top row to the body; everything below hangs and moves.

## The other look: the cape shader

`shader = "cape"` keeps the game's cape shader: the lighting follows the folds, but colours come from the cape's zone
system (4 flat colours from a mask) or a full-cover decal (any picture), and a full-cover decal shows glints along
folds. See `CLOTH_MATERIAL_RESEARCH.md`. The build tool does not make cape materials yet.
