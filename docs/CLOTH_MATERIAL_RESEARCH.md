# Cloth material research (2026-10-18)

Question: how can a mod author put their OWN textures on engine cloth, and how do we kill the camo
squares? Offline data analysis only (no game run). Tags: **[V]** = verified from game data,
**[G]** = guess / inference, needs an in-game test.

Scripts and dumps: `~/.cache/hd2-dress/clothmat_research/` (scan.py, scan_tex.py, analyze.py,
dump_tex.py, search_ids.py, gen_textures.py, build_tests.py; texture dumps in tex/ and png/, contact
sheets sheet_*.png, decal_rects.png).

## 1. The cape shader and who uses it

- [V] The cape shader is itself a root material (parent 0) `15780315333863701079` in archive
  `18235e0c9ec0e636`. Only THREE materials in the whole game (10016 materials, 9715 packages scanned)
  use it as parent:
  | material | archive | used by |
  |---|---|---|
  | 8444775596724238472 | 18235e0c9ec0e636 | cape unit 0x3c33cf10a26cbb3e (cloth A) |
  | 4088526467780291396 | 18235e0c9ec0e636 | cape unit 0xea846ef460cc5ba0 (cloth B) |
  | 15108509647022664765 | c40e3b3fa79052ec | flag unit 0xb0f1b354ba1d38d8 (CQC-1 One True Flag) |
- [V] Only THREE cloth resources (type d7014a50477953e0) exist in the game: the two capes
  (4338038536439380798, 16898753697676024736 in 18235e0c9ec0e636) and the One True Flag
  (12750169196543686872 in c40e3b3fa79052ec). All three draw with the cape shader.
- [V] So no other cloth-capable material is in use anywhere. Ship banners / hanging flags
  (content/env_ship/customization/flag_hanging_01 etc.) have no cloth resource; they are not engine
  cloth. [G] Other shaders might still be cloth-capable in the shader code, but there is no stock
  example to copy, so the cape shader is the only practical choice.
- [V] There are no per-cape materials. The ~106 cape designs live in small texture-only packages
  (each: 23x5 MaterialLut, 16x5 CapeLut, a 256/512 zone mask, often the shared 512 BC4 gradient
  13415522394280285038 and a shared 2048 BC3 decal sheet). [G] The game swaps these textures onto
  the cape material at runtime. A search of every package for five of those texture ids found them
  only in package manifests, so the slot mapping is in code, not in data.
- [V] "Foe Smasher" (0fe88d9b08f6fe80, texture 3675953607041943145) holds a MaterialLut that is
  byte-for-byte the same as the stock default cape LUT 11899498302424885466. Its real look comes
  from the zone mask in its second package 4b3085719366f5f2. Our installed "Foe Smasher" material
  is therefore just the default LUT.

## 2. Slots (14 textures, 38 shader variables, same list on all three materials)

| slot | stock cape 8444 | other cape 4088 / flag | varies per cape design? | what it is |
|---|---|---|---|---|
| MaterialLut | 23x5 RGBA16F | 23x5 / 23x8 | yes (every design) | [V] per-zone material table, same 23-column layout as armour LUTs (23x8). Rows = zones. Cols 0,2,5,6 are colours; col1.x is an integer (13/16/19/20, [G] material-type index); col21 = (x, angle, z, w) with w in {-1,0..4}, [G] camo/pattern params with w = tiler slice, -1 = off |
| CapeLut | 16x5 RGBA16F | 16x5 | yes | [V] per-zone decal table: cols 4-6, 7-9, 10-12, 13-15 = up to 4 decals per row. Empty decal = (0,0,1,1),(0,0,0,1),(1,0,0,0). Second vector holds angles (1.57, 3.14) and signed scale. [G] the first vector is NOT a plain atlas rect (overlay in decal_rects.png doesn't match the emblems) |
| IdMasksArray | dummy 1x1 black | dummy | yes (256 or 512, RGBA8/BC7/BC3) | [V] UV-mapped zone mask in cape UV space: flat R/G/B blobs = design regions (stripes, chevrons, trims; see sheet_capes.png). [G] channel picks the MaterialLut/CapeLut row |
| DecalSheet | dummy 1x1 | 2048 BC3 atlas | 2 shared atlases | [V] full-colour RGBA emblem atlas (skulls, globes, stripes). Only full-colour image the shader takes |
| BaseData | 1024 BC7 | 1024 BC7 / 1024x512 | per mesh, not per design | [V] UV0 map: RG = tangent normal (cape folds/hems), B = white with dark folds ([G] AO/cavity), A = grey detail ([G] height/roughness detail) |
| CapeGradient | dummy | 512 BC4 / 256x128 | shared 512 BC4 | [V] UV vertical gradient (white top, black bottom). [G] height/fade mask |
| CapeTear | 1024 BC4 | 1024/512 BC4 | shared | [V] UV mask with ragged edges. [G] tear/burn reveal (TearAmount, the jetpack "hazard" burn lines) |
| CapeScalarFields | 4x4 RGBA16F (all 0, a=1) | dummy | no | [G] scalar params |
| CustomizationCamoTilerArray | 256x256x5 RGBA8 | same id everywhere | no (shared by all) | [V] 5 slices x 4 channels of tileable patterns: slice0/1 noise, slice2 arrows and octagons (reads as SQUARES), slice3 blotch camo, slice4 stripes. Same texture armour uses for player camo |
| CompositeArray | 256x256x2 BC7 | same | no | [V] detail normals: slice0 hexagon, slice1 weave |
| WeatheringSpecial / WeatheringDirt | 512 / 256 BC7 | same | no | [V] normal-ish detail tilers for weathering |
| BloodSplatterTiler / BugSplatterTiler | 256 BC7 | same | no | gore tilers |

Variables (all the same on the three materials except DetailTileFactorMult 1.0 / 1.5): CapeHeightMult
1.5, CapeHeightFromGround 0.2, TearAmount 0, PaletteSlot 0, DetailTileFactorMult, WeatheringTileFactor
8, WeatheringVariant 3, Blood*/Gunk*/Frost/Wetness weights, DebugMode 0, plus 8 unnamed hashes.
[V] None of the variables is named after camo. Material binary: 1328 bytes, no trailing data.

UV sets [V]: the cape meshes have 3 UV sets with UV0 ~= UV1 ~= UV2 (one 0..1 layout, the cape
flattened). The flag: UV0 = planar 0..1 over the flag, UV1 = planar but offset/scaled so 0..1 is a
centred square (back face mirrored), UV2 mostly (0,1). [G] UV1 = decal space, UV0 = BaseData /
IdMasks space. All vertex colours are 0.

## 3. Is the look LUT-only?

[V] No. A stock cape = UV0 zone mask (IdMasksArray) -> per-zone row of MaterialLut (colours,
roughness etc.) + UV-mapped BaseData normals + decals from DecalSheet placed by CapeLut + shared
tiled detail (CompositeArray, camo tiler, weathering). There is NO plain albedo slot.

Why our rig shows squares [G]: the rig has every cloth vertex at UV (0.5,0.5), so every UV-mapped
slot reads one texel. What is left that varies across the surface is the position-tiled stuff, and
the camo tiler slice 2 (arrows/octagons) is the only pattern that reads as squares. Which LUT
column turns camo on is not proven: the default LUT has col21.w = -1 in every row and the squares
show anyway. They flicker between two looks (metal vs bright), which fits a blend between the
LUT's colour columns (col0 0.24 grey, col2 0.18, col5 0.50 bright, col6 0.23).

## 4. Killing the camo squares (cheapest first)

1. [G, best bet] Point OUR material's CustomizationCamoTilerArray at a flat texture (5 slices,
   constant). It's the shared id 17920474440659607336 in stock materials, so a private copy only
   affects our material. Built both constants (0 and 255) because we don't know which one means
   "no pattern".
2. [G] Make the LUT colour columns identical inside each row (col2/5/6 rgb = col0 rgb), so whatever
   mask drives the blend, the result is one colour. Also flattens rows (as before) and CapeLut rows.
3. If neither works, the squares are not camo: suspect CompositeArray / weathering, and test by
   pointing those slots at the 1x1 dummy 17544421564454316850.

## 5. Recipes for "author's own texture on engine cloth" (ranked)

All need the cloth mesh to have a real UV layout (UV0, and UV1 = same layout, all in 0..1)
instead of the current single (0.5,0.5) UV. The cape meshes themselves have UV0 = UV1 = UV2.

A. Zone mask + palette (how every stock cape is made; most likely to work).
   Author paints a 256-512 RGBA8 mask in UV0 (R, G, B, A regions + empty), picks up to 5 colours
   (one MaterialLut row per zone, cols 0/2/5/6 set equal). Limit: flat colours, no photos.
   Plus their own normal map in BaseData (RG normal, B ~white, A ~0.5).
B. Decal sheet as albedo (only full-colour route).
   Author image -> DecalSheet (any RGBA format; RGBA8 works for the sampler), CapeLut row with a decal
   whose placement covers the whole UV1 0..1. Needs the CapeLut decal encoding decoded first
   (vectors: [G] v1 = (u, v, angle, signed scale)). Risk: decal blending/opacity may not be full.
C. Custom camo tiler.
   Author pattern in a private 5-slice CustomizationCamoTilerArray. Repeats in 3D space, not
   UV-mapped. Good for fabric-type patterns (plaid, weave), useless for images or logos.

## 6. Test patches built (NOT installed)

`~/.cache/hd2-dress/clothmat_research/build/<variant>/9ba626afa44a3aa3.patch_0` (+ .gpu_resources,
.stream). Each is a copy of 8444775596724238472 with one change and its own material id:

| variant | material id | change | in-game test / what to look for |
|---|---|---|---|
| camo0 | 7200101010101010201 | camo tiler -> flat 0 | squares gone? (works with the current 0.5,0.5 UV rig) |
| camo255 | 7200101010101010202 | camo tiler -> flat 255 | same; one of the two should be uniform |
| colflat | 7200101010101010203 | MaterialLut rows flattened + cols 2/5/6 = col0; CapeLut rows flattened | squares gone even with the stock tiler? |
| zones | 7200101010101010204 | IdMasksArray = quadrant mask (TL=R, TR=G, BL=B, BR=A, centre band empty); LUT rows 0..4 = white, red, green, blue, yellow | NEEDS UVs. Which colour shows in each quadrant = channel -> row mapping. Uniform colour = mask not on UV0 |
| decal | 7200101010101010205 | DecalSheet = 512 labelled 4x4 colour grid (build/decal_probe.png), CapeLut = stock decal setup of cape 1ff9ac94b5d8c7cd, colflat LUT | NEEDS UV1. Which grid cells appear, and where = decoding the CapeLut decal vectors |
| ridges | 7200101010101010206 | BaseData = horizontal ridge normal map, colflat LUT | NEEDS UVs. Ridges along the UV0 v axis = author normal maps work |

To install one for a test: copy the three files into the game data folder as the next free
contiguous patch slot of 9ba626afa44a3aa3, and either point the rig armour's cloth mesh at the
variant's material id, or rebuild the variant with the id the rig already uses (edit IDS in
build_tests.py, then `blender -b -P build_tests.py -- VARIANT`). Order: camo0/camo255/colflat first
(no mesh change), then give the rig real UVs and test zones, ridges, decal.


## Update 2026-10-18 (in-game results)

- The "camo squares" were NOT a material effect: the test rig had two coincident layers (front + reversed
  back) and the two-sided cape shader z-fought them. One layer = solid cloth. Every texture/LUT test before
  that fix (camo0, camo255, colflat, allflat, stripes, redstripes, nodecal, nobump, opaque) was hidden by
  the z-fighting and must be re-run.
- Reference: the community "HELLDIVERS 2 LUT Modding Guide" (Google Doc,
  https://docs.google.com/document/d/1A_bsjh-wc6nhuxYodRk5LURugD0mQd2kyctkOqZysks) documents every column
  of the primary LUT (23 columns; col 22 alpha = camo type, -1 = off; col 2 = bump map tile/strength) and
  the cape LUT (col 1-4 overlay/gradient, cols 5-16 = four icon layers: boundary, atlas focus, strength),
  the cape RGBA ID mask (RGB = zone rows, alpha = cape shape) and the icon atlases.


## SOLVED 2026-10-18: how to colour engine cloth (verified in game)

Engine cloth draws only with the cape shader (verified again with a clean pipeline: an armour material on the
cloth mesh is invisible). The cape shader's own resource list (read from the game's memory) is: cape_gradient,
cape_lut, cape_scalar_fields, cape_tear, blood/weathering/bug tilers, decal_sheet, customization_camo_tiler_array,
composite_array, base_data, material_lut, customization_material_detail_tiler_array, brdf luts.
It does **not** read `IdMasksArray`. Per-object variables include palette_slot and a set of decal controls.

The recipe (material = a copy of the stock cape material 8444775596724238472):

| Slot | What it does on cloth |
|---|---|
| **CapeScalarFields** | the RGBA **zone + shape mask** (what the guide calls the cape RGBA mask), sampled with the cloth UVs. RGB picks the zone, **alpha cuts the shape** (alpha 0 = no cloth drawn) |
| **CapeLut** (16 x 5) | per-zone colour. Rows: 0 = black zone (base fabric), 1 = red, 2 = green, 3 = blue, 4 = **inside** (back faces). Column 1 RGB = the zone's colour; columns 2 and 3 = how strongly it is applied (B = 1, A = 1 is full); columns 4-16 = gradient and the four icon (decal) layers, as in the community guide |
| **MaterialLut** (23 x 5) | the base material (the black zone's fabric: bump tile, roughness, metal...), same column layout as the armour primary LUT |
| **BaseData** | the fold/normal map (RG normal, B AO, A curvature), sampled with UV0 |
| DecalSheet | the icon atlas the CapeLut icon layers cut from |
| PaletteSlot (material scalar) | leave 0 (other values went dark) |

Mesh rules: one layer only, three identical UV sets (UV0 = UV1 = UV2, like the cape), faces pointing OUTWARD
(back faces get the "inside" row), LOD1+ not on the cloth material.

Proof: band mask (black band + red/green/blue thirds, alpha solid) + CapeLut column 1 = black/red/green/blue/yellow
at full strength: the dress showed red, green and blue bands, the black band showed the stock fabric (woven bump),
and back faces showed yellow (the inside row).


## Full-colour textures on cloth (verified in game 2026-10-18)

Zones are hard-edged (a smooth RGB mask gives hard lines, no blending): 4 flat zone colours + the inside per cloth.
For any number of colours use a **decal layer as the texture**:

- DecalSheet = the author's full-colour texture (tested 512x512 RGBA8; stock sheets are 2048x2048 BC3).
- CapeLut, every zone row: decal layer 1 = column 5 (box) **(0.5, 0.5, 1.0, 1.0)** = centred, covering the whole
  0..1 UV square; column 6 (sheet window) **(0, 0, 0, 1)** = centre, no rotation, zoom 1 = the whole sheet;
  column 7 **(1, 1, 0, 0)** = full strength, opaque, no gradient. Other layers off (column 7 of each = 0).
- Result: the sheet is mapped over the cloth's UV square like a normal colour texture (a labelled 4x4 grid sheet
  showed all 16 cells in order around the skirt, rows top to bottom).
- Half-size boxes / zoom 2 show half the sheet or half the cloth (the earlier spectrum tests).
- Columns 1-3 (zone overlay colour) set to 0 so the zones don't tint the picture; the mask still sets the shape
  (alpha) and the zones' base fabric.
