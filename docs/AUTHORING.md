# Adding dress physics to an armour mod

Two ways, same runtime. Players install **HD2 Dress** (the physics addon) once, like Bingus Shared
Loader. Each dress mod then adds a small rig patch and a tiny registration addon.

## 1. Quick and dirty: the auto-rig (no work for the author)

    ~/apps/blender-5.2.2-linux-x64/blender -b -P tools/dress_autorig.py -- MOD/9ba626afa44a3aa3.patch_0 OUT --name "My Dress"

About a minute. It finds the Torso/Hip pieces that have cloth below the waist and adds 12 chains of
4 bones that follow the skirt's real shape (A-line, flare, a longer back). It then weights the cloth
to them, fading from the body's own weights over the top 8 cm (`--waist`, `--blend`, `--chains`,
`--joints`, `--exclude-back` for a tail).

OUT gets:
- `9ba626afa44a3aa3.patch_0` (+ .gpu_resources, .stream): only the rigged pieces. Install it AFTER
  the original mod, so it overrides those pieces. The mod's textures and materials stay in the
  mod's own patch.
- `hd2dress_register.lua`: the registration addon (pack it with `tools/pack.py luazip`).
- `hd2dress_register.json`: the chain layout, for the simulator (`sim/dress_rest.py`).

Preview before the game: `sim/dress_rest.py OUT/hd2dress_register.json sim/work/x.lua`, then
`luajit sim/run_sim.lua sim/work/run_stop.lua out.csv DRESS=sim/work/x.lua`. It reports how often
the legs get through the cloth, physics against rigid.

## 2. Hand-made quality (minimal extra effort)

Rig it yourself in Blender with the HD2SDK and follow three rules:

1. **Names:** `dress_c01_b1` ... `dress_cNN_bK`. Chain number first (01, 02, ... going around the
   body), then bone number from the waist down (b1 at the waist).
2. **Parents:** each `b1` is parented to `hips` (or any body bone); each next bone is parented to the
   one above it. Point each bone along the cloth, toward the next bone.
3. **Weights:** skin the cloth to these bones as you like (that's where the quality comes from). Keep
   the waistband on the body bones.

Chains may differ in length; every chain needs the same number of bones (K). Then write the
registration (or run the auto-rig's writer):

    HD2DRESS_REGISTRY = rawget(_G, "HD2DRESS_REGISTRY") or {}
    table.insert(HD2DRESS_REGISTRY, { name = "My Dress", unit = "<unit id, 16 hex digits>", chains = 12, bones = 4 })

`lengths` is optional (the runtime measures the bones); give it only to set the last bone's length.

## What the runtime does

Every frame, for the local player's dress: a spring chain per column, with neighbours tied together
so no gap opens, and the whole cloth surface pushed out of the thighs and shins. All feel values are
in `HD2Dress_settings.txt` (live; END toggles it). The physics is client-side: other players
see the dress move with plain skinning.
