# Engine cloth: tested values

These are the values we have actually tried in game with the engine (Havok) cloth, no Lua, on the
B-01 hip test rig: a floor-length skirt (36 panels around, 0.85 m long, 972 cloth points with the
shoulder strips) on the female and male bodies. Tested 2026-10-17 and 2026-10-18.

**You can use any values you like.** Nothing here is a hard limit of the engine (except substeps, see
below). This page records what we tested, what happened, and what the test rig ships with, so you have
a known-good starting point. Other garments (short skirts, sleeves, hair, capes) may want different
numbers, and every model needs its own fine tuning (kneepads, armour shapes and lengths differ).

The hardest tests for skirts are three emotes: **Thumb of Approval** (thumbs up: the diver drops to one knee fast
and the raised knee pushes hard into the front of the skirt), **Squat** (deep knee bend, legs wide) and
**Front-Leaning Rest Position** (push-ups: the body flat over the ground, the skirt hangs down). Also check the
**hellpod / armory / loadout preview** (it shows a cloned diver, see substeps).

All values below are set in the settings file (see `examples/engine_cloth_testrig.toml`, every key is
commented) and built with `blender -b -P tools/hd2dress_cloth.py -- build SETTINGS.toml`.


## How loose can you go (read this first)

HD2's cloth engine is used by Arrowhead as a **tarp with a wobble**: the stock cape follows its animated shape and only
gets a few centimetres of physics on top (leash ~1.7 cm). It never moves far enough to fold through itself, and the
engine has **no self-collision**.

- **Tight or short garments** (capes, tabards, sashes, short skirts, loincloths): tune them like the cape (small leash,
  bend ~0.8). They look flawless.
- **Long, loose garments** (floor dresses, robes): real flowing cloth is possible (the test rig), but expect occasional
  self-clipping in extreme poses (the "front rest leaning position" push-up emote is the worst case: the skirt is pressed
  between the legs and the floor). Tighten the leash where the garment should not gather (waist, hips) and keep it
  loose only where the legs need room.

## What Arrowhead ships (the stock cloths)

The best "known good" values are the game's own. Extracted from the two stock capes and the One True
Flag (the only three engine cloths in the game):

| Setting | Stock cape | Flag | Test rig dress |
|---|---|---|---|
| Substeps / iterations | **1 / 1** | 1 / 1 | 1 / 4 |
| Point mass | 0.003 | 0.0025 | 0.004 |
| Collision ball radius | ~0.04 m (0.006 to 0.06) | 0 | 0.025 |
| Friction | 0.5 to 1, mostly 0.6 to 0.75 | 0.5 | 0.3 |
| Leash | 0.003 to 0.10 m, median 0.017 | 0.11 to 0.49 m | 1.0 m (skirt) |
| Bend stiffness | 0.6 to 1.2, median ~0.8 | 0.25 to 1.4, median 0.44 | 0.24 |
| Gravity / damping | 9.81 / 0.7 | 9.81 / 0.95 | 14 / 0.7 |
| Floor gap (landscape radius) | 0.07 m | | 0.015 m |
| Bone planes | 457 on its bone | none | 423 on thighs/shins |
| Volume constraint | yes | no | no |

The cape gets away with 1 substep and 1 iteration because its leash is tiny (it barely leaves its
animated shape), its balls are bigger, and it has bone planes.

## The test rig's values

| Setting | Value | Settings key |
|---|---|---|
| Substeps | **1 (keep 1)** | `[sim] substeps` |
| Solver iterations | 4 | `[sim] iterations` |
| Link passes | 3 | `[sim] link_passes` |
| Leash (skirt) | 1.0 m | `[part] leash` |
| Stretch limit | 0.60 | `[part] stretch` |
| Neighbour link stiffness | 1.0 | `[part] stiffness` |
| Bend stiffness | 0.24 | `[part] bend` |
| Point mass | 0.004 | `[part] mass` |
| Particle (ball) radius | 0.025 m | `[sim] radius` |
| Friction | 0.3 | `[sim] friction` |
| Gravity | 14 | `[sim] gravity` |
| Floor gap | 0.015 m | `[sim] landscape_radius` |
| Bone planes | on, reach 0.15 m, margin 0 | `[planes]` |
| Kneecap capsules | l/r_knee, -0.05..0.05, +0.03 m | `[collision] extra` |
| Thigh follow | 0.6, front follows its own thigh | `[follow]` |
| Motion transfer | translation 0.5 to 2.0 m/s, rotation 90 to 360 deg/s | `[motion]` |

## What we tested and what happened

### Substeps (physics steps per frame): KEEP 1

| Substeps | Result |
|---|---|
| 1 | knee jumps through the cloth on fast moves (with the old settings) |
| 3 | much better on your own diver |
| 5 | best on your own diver |
| 10 | about **20 fps lower** and no better than 5 |
| any > 1 | **engine bug**: the cloned diver in the hellpod / armory / loadout preview draws long garbage spikes |

The spike bug is the game's, not ours: the **stock capes rebuilt with 3 substeps spike too**. The
physics stays fine; the clone's render data gets mixed with the real diver's (28 m away). Arrowhead
ships every cloth at 1 substep, so they never hit it. Changing substeps or iterations **live crashes
the game** (bake only).

### Iterations (solver passes per step)

| Iterations (at 1 substep) | Result |
|---|---|
| 1 | knee goes through |
| **4** | knee held (shipped). The skirt is stiffer, so a kneel lifts the hem more |

### Leash (how far a point may move from where the dress would normally hang)

| Leash | Thumbs-up kneel |
|---|---|
| 0.40 m | knee falls through |
| 0.45 m | knee falls through |
| 0.55 m | holds (5 substeps); at 4 iterations the hem rides up the leg after a second |
| 0.70 m | holds |
| **1.00 m** | holds, no riding up (shipped) |

Why: the leash pulls every point toward its "normal" spot. With thigh follow, the front skirt's normal
spots ride on the thigh, so in a kneel they swing up and forward (or end up inside the bent leg). A
tight leash drags the cloth after them. A loose leash costs safety: less pull back into shape after
falls, hoverpack or ragdoll; bone planes and collision do the anti-clipping instead.

### Stretch limit (how far a point may get from the waist row)

| Stretch | Result |
|---|---|
| 0.05 | fine for short strips |
| 0.60 | fine (shipped); was never the knee problem |
| 1.00 | fine, not needed |

### Neighbour link stiffness

| Stiffness | Result |
|---|---|
| 0.7 | points spread apart under the knee and the knee slipped through the gaps |
| **1.0** | points keep their spacing (shipped) |
| x0.3 (live) | close to exploding |

### Bend stiffness

| Bend | Result |
|---|---|
| 0.8 (the cape's value) | the skirt stands out like a stiff cone (it springs back to its built flare) |
| **0.24** | softer folds (shipped) |

### Friction

| Friction | Result |
|---|---|
| 0.97 (cape max) | grips: fine at 5 substeps |
| 0.8 | at 4 iterations the knee carries the skirt up the leg |
| 0.5 | slid up the leg when kneeling (old 1-substep setup) |
| **0.3** | the knee slides under the cloth (shipped) |

### Gravity ("heavier")

Giving every point the same extra mass changes nothing in Havok (gravity pulls all masses equally, and
bend stiffness is computed from the masses). What reads as "heavier fabric" is stronger gravity on this
cloth only: **14** (shipped) falls faster and swings less. Real per-part weight (a heavy hem) needs
per-vertex mass.

### Particle (ball) radius

| Radius | Result |
|---|---|
| 0.01 m | lies closer to the body |
| 0.02 m | a tiny hole could open at the knee |
| **0.025 m** | shipped |
| 0.03 m | floats visibly off the legs |

The cloth rests on the invisible capsules, not the visible armour. Points are 6 to 8 cm apart here and
only the balls collide, so smaller balls leave bigger gaps.

### Collision shapes

| Change | Result |
|---|---|
| Thigh/shin capsules +2 to +5 cm | stops the leg, but reads as "tubes" around the legs |
| Kneecap capsule +3 cm with soft (0.7) links | worse: pushed the cloth further, gaps opened |
| **Kneecap capsule +3 cm with firm links + bone planes** | the raised knee no longer pokes a hole (shipped) |
| Body-size capsules | the cloth lies flat on the body |

### Bone planes (the cape's anti-clipping tool)

Each loose point near a leg gets one invisible wall fixed to the nearest thigh or shin capsule, on the
side facing the point. The wall moves with the bone: a raised thigh keeps the cloth on top of it, a shin
keeps it in front. The cloth can't end up on the wrong side of a leg. 423 planes on the test rig; the
build checks every one starts on the allowed side. Settings: `reach` (which points get a wall),
`margin` (wall distance from the capsule surface), `stiffness`, `bones`.

### Inward limit (leash normal limit)

`[part] inward` stops a point sinking more than X behind its normal spot. Built and working, but on the
skirt with thigh follow it made the cloth **climb the thigh** in a kneel (0.03 and 0.10 m both). Off on
the test rig; bone planes do the job better. May suit garments without thigh follow.

### Floor gap (landscape radius)

The cape keeps cloth 7 cm off the floor. Between a kneeling knee and the floor that leaves no room, so
the cloth gets pinched. 0.015 m on the test rig. Havok also has pinch detection (switches present, all
off on every stock cloth); not tested yet.

### Mesh rules for cloth (found 2026-10-18)

- **One layer only.** The cape shader draws both sides of every face. A front layer plus a reversed back
  copy at the same positions z-fights: blocky light/dark (metal/cloth) squares that look stable while the
  cloth is still and turn to TV static when it moves. No material or texture change affects it. The build
  refuses double-layered cloth (`cloth.allow_double_layer = true` to override).
- **Real, continuous UVs.** HD2 meshes store no tangents; the shader builds its tangent frame from the UVs.
  The cape uses UV0 = UV1 = UV2. A single shared UV (one dot) or Blender's per-face default UVs give
  broken shading. With UVs, the cape's fold texture (BaseData) shows on the cloth.
- **LOD1+ must not use the cloth material** (see Detail levels).

### Detail levels (LODs)

The cloth drives one mesh (LOD0). If LOD1+ meshes use the cloth material with nothing driving them, the
game draws garbage on far or preview views. Give LOD1+ a normal material (the dress shows stiff at a
distance), or no auto LODs.

## Stock cloth reference (complete)

Everything we can read out of the game's three engine cloths (extracted 2026-10-18 from the game files).
These are Arrowhead's tuned values, the safest known-good reference. Ranges are over the loose points;
"median" is the typical value. Stiffness 1 = full strength.

### Cape A (medium cape, 18235e0c9ec0e636 / 3c33cf10a26cbb3e)

States: Simulate, Simulate_Backpack, Simulate_LOD1, Simulate_LOD0, Simulate_Backpack_LOD1, Simulate_Backpack_LOD0, Off, Backpack_LOD1>Backpack_LOD0

| Setting | Value |
|---|---|
| Particles (pinned) | 984 (130) |
| Substeps / iterations | 1 / 1 (adapt stiffness True) |
| Solve order | BonePlanes > LocalRange > StandardLink > StandardLink > StandardLink > BendStiffness > StretchLink > Volume |
| Gravity / damping per second | 9.81 / 0.7 |
| Point mass (loose points) | 0.003 |
| Collision ball radius | 0.006 to 0.05 (median 0.0459) |
| Friction | 0.5 to 1 (median 0.661) |
| Max particle radius | 0.05 |
| Floor gap (landscapeRadius) | 0.07 (stuck-particle detection True, collisionTolerance 0.2) |
| Landscape collision | True |
| Motion transfer | translation 8.0 to 12.0 m/s (blend 0.0 to 1.0), rotation 430.0 to 1080.0 deg/s; enabled True |
| Neighbour links | 2508 links, rest length 0.00558 to 0.13 (median 0.0407) m |
| Stretch links | 852 links, stiffness 1 |
| Bone planes | 457 planes, stiffness 1 |
| Bend stiffness | 0.615 to 1.19 (median 0.779) (2320 hinges, clamp True) |
| Volume constraint | 964 frame entries, apply stiffness 0 to 0.08 (median 0.0757) |
| Leash (max distance) | 0.00318 to 0.101 (median 0.0168) m, stiffness 1.0, normal limit False |
| Collision shapes (capsule radius m) | chest (convex), head 0.131, hips 0.146, l_elbow 0.065, l_foot 0.055, l_hand 0.048, l_knee 0.093, l_shoulder 0.084, l_thigh 0.127, r_elbow 0.060, r_foot 0.065, r_hand 0.044, r_knee 0.100, r_shoulder 0.086, r_thigh 0.132, spine1 0.172, spine2 (convex), attach_knife 0.030, attach_samplepouch 0.061, l_clavicle 0.076, r_clavicle 0.075 |

### Cape B (18235e0c9ec0e636 / ea846ef460cc5ba0)

States: Simulate, Simulate_LOD1, Simulate_Backpack, Simulate_Backpack_LOD1, Simulate_LOD0, Simulate_Backpack_LOD0, Off, Backpack_LOD1>Backpack_LOD0

| Setting | Value |
|---|---|
| Particles (pinned) | 943 (140) |
| Substeps / iterations | 1 / 1 (adapt stiffness True) |
| Solve order | BonePlanes > LocalRange > StandardLink > StandardLink > StandardLink > StandardLink > BendStiffness > StretchLink > Volume |
| Gravity / damping per second | 9.81 / 0.7 |
| Point mass (loose points) | 0.003 |
| Collision ball radius | 0.03 to 0.06 (median 0.0453) |
| Friction | 0.5 to 1 (median 0.795) |
| Max particle radius | 0.06 |
| Floor gap (landscapeRadius) | 0.07 (stuck-particle detection True, collisionTolerance 0.2) |
| Landscape collision | True |
| Motion transfer | translation 8.0 to 12.0 m/s (blend 0.0 to 1.0), rotation 430.0 to 1080.0 deg/s; enabled True |
| Neighbour links | 2356 links, rest length 0.0065 to 0.133 (median 0.0462) m |
| Stretch links | 800 links, stiffness 1 |
| Bone planes | 398 planes, stiffness 1 |
| Bend stiffness | 0.615 to 1.21 (median 0.833) (2180 hinges, clamp True) |
| Volume constraint | 844 frame entries, apply stiffness 0 to 0.08 (median 0.08) |
| Leash (max distance) | 0.01 to 0.0901 (median 0.0408) m, stiffness 1.0, normal limit False |
| Neighbour links | 2181 links, rest length 0.0161 to 0.205 (median 0.0791) m |
| Collision shapes (capsule radius m) | chest (convex), head 0.131, hips 0.147, l_elbow 0.065, l_foot 0.055, l_hand 0.048, l_knee 0.093, l_shoulder 0.084, l_thigh 0.127, r_elbow 0.060, r_foot 0.065, r_hand 0.044, r_knee 0.099, r_shoulder 0.086, r_thigh 0.132, spine1 0.172, spine2 (convex), attach_knife 0.031, attach_samplepouch 0.061, l_clavicle 0.077, r_clavicle 0.076, butt (convex) |

### One True Flag (c40e3b3fa79052ec / b0f1b354ba1d38d8)

States: Simulate

| Setting | Value |
|---|---|
| Particles (pinned) | 112 (8) |
| Substeps / iterations | 1 / 1 (adapt stiffness True) |
| Solve order | LocalRange > StandardLink > BendStiffness > StretchLink |
| Gravity / damping per second | 9.81 / 0.95 |
| Point mass (loose points) | 0.0025 |
| Collision ball radius | 0 |
| Friction | 0.5 |
| Max particle radius | 0.0 |
| Floor gap (landscapeRadius) | 0.05 (stuck-particle detection False, collisionTolerance 0.2) |
| Landscape collision | False |
| Motion transfer | translation 0.0 to 0.0 m/s (blend 0.0 to 1.0), rotation 0.0 to 0.0 deg/s; enabled False |
| Leash (max distance) | 0.11 to 0.491 (median 0.244) m, stiffness 1.0, normal limit False |
| Neighbour links | 286 links, rest length 0.0686 to 0.167 (median 0.1) m |
| Stretch links | 104 links, stiffness 1 |
| Bend stiffness | 0.253 to 1.42 (median 0.44) (244 hinges, clamp True) |
| Collision shapes | none (the flag collides with nothing) |

Notes:
- Both capes run **1 substep, 1 iteration** with a **tiny leash** (1.7 to 4 cm typical), bigger balls
  (~4.5 cm) and **bone planes** on the cape bone, plus a volume constraint. The flag is much looser
  (leash ~24 cm) with no collision at all.
- Cape B has a second neighbour-link set (longer links, ~8 cm) on top of the first.
- The cape collides with more than the body: hands, the knife and sample pouch attachments, and a "butt"
  convex shape (Cape B). Our generator copies the cape's shapes for bones the armour unit has.
- Motion transfer on the capes starts at 8 m/s (only really fast moves carry the cape); the test rig
  starts at 0.5 m/s (the skirt needs to follow kneels and emotes).
- The cape's LOD/backpack states (Simulate_LOD0/1, Simulate_Backpack...) are how the game swaps cape
  detail and the backpack variant; our generated cloth only has Simulate and Off.

## Live testing (no restart)

Tools in `tools/havok/re/` (Linux / Proton only: they write game memory from outside. Windows needs an
in-game route, see the guide):

- `livetune.py ... --reset` changes a value in the running game, then restarts the cloth smoothly.
- `clothreset.py [--flare 1.4]` puts the cloth back at rest with zero speed, spread outward so it falls
  onto the body. (It checks the shared scratch memory really holds this cloth; otherwise it fits the
  built rest shape onto the pinned waist points.)
- `restorelinks.py CLOTH.bin` copies the constraint data back from your built file after a bad edit.

| Live edit | Status |
|---|---|
| Gravity (`--gravity`), friction, particle radius, floor gap (`--landscape-radius`) | safe |
| Leash (`--leash lo:hi:value`), inward (`--inward`), bend (`--bend-scale`) | safe |
| Stretch limit, link stiffness | not re-tested since the leash bug fix |
| Collision capsule size / extra capsules, bone planes | copied per cloth at spawn: bake |
| Substeps, iterations | **crash**: bake only |

Note: before 2026-10-18 the live leash edit overwrote the neighbour links (a bug in our tool), which was
the "bunching after a live edit" in earlier sessions, not the engine.
