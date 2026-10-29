# Project log: dress physics for Helldivers 2 (started 2026-10-15 as the handoff/research plan)

## Goal
A dress or long skirt on a Helldiver that moves right: follows the legs when walking, running,
diving and going prone, sways and settles, and never lets a leg poke through. Possibly a public
release later ("people would go nuts"), so keep it a clean, separate mod (see Release below).

## Why model mods hit a wall (reasoning, not confirmed by any modder write-up)
- The game's jiggle bones (used by mods, e.g. a ponytail with a `jiggle_bone`, Nexus helldivers2
  mod 318) swing from inertia/gravity but do not collide. Fine for a ponytail in free air; a skirt
  sits around the thighs and gets crossed by a leg every stride.
- Skinning alone cannot solve it: weighted to the legs it tears between them, to the pelvis the legs
  poke through, to both it pinches.
- Model mods ship DATA only (meshes, skeletons, existing bone behaviours). "Push this bone out of the
  thigh" is per-frame logic; no data asset in the game provides it.
- Helldiver poses are extreme (sprint, dive, prone, ragdoll); the game's own armour uses short split
  front/back flaps, probably for this reason.

## Our approach (the standard game-industry one)
Runs in Lua every frame (Bingus Shared Loader addon, like hd2-vr):
1. **Leg-driven skirt bones**: ~8-12 vertical chains of 3-4 bones around the hips. Each chain's
   root follows a blend of pelvis and the nearest thigh (front chains follow the stepping leg).
2. **Spring layer**: verlet/spring per bone (stiffness, damping, gravity, drag) for sway and settle.
3. **Collision**: capsules around both thighs and shins (from the live leg bones); any skirt bone
   inside one is pushed out, then the chain length is restored.
4. **Write**: `Unit.set_local_rotation` per skirt bone, every frame (same way the Jaeger aims its
   lamps).
All feel values (stiffness, damping, gravity, capsule radii, leg blend) are live tunables on a Mod
Options page (user rule: UX values are always tunable, never hardcoded).

## What is already proven (sources)
- Adding bones to an armour unit works in game: StalkerDiver adds leg bones to its torso piece;
  our Jaeger patch added 3 lamp bones and they kept position, parent and direction
  (hd2-jaeger docs/PATCH.md, "Searchlights" and "Reference mods").
- Patch pipeline for armour: hd2-jaeger tools/build_patch.py, skeleton_edit.py, verify_patch.py,
  dump_unit.py, analyze_mod.py (facts only from other mods, never copy their code or assets).
  One patch on the base archive 9ba626afa44a3aa3; Blender + HD2SDK setup: tools/setup_blender_sdk.sh.
- Per-frame bone rotation writes stick on a unit the mod owns, ~0.01 ms/frame (Jaeger puppet,
  hd2-vr mod/lib/jaeger_puppet.lua, origin/main v0.18.x).
- On the player's own animated Helldiver, the bone mode is position_and_rotation: the animation
  REWRITES every animated joint every frame, so writes to animated joints are lost
  (hd2-jaeger docs/PATCH.md, "Joint tests in game"). Owning the whole pose (state machine off +
  bone mode 'ignore') works but kills normal animation, so it is NOT the dress route.
- Bone map of the player skeleton (77 bones, legs 8-19, pelvis 5-7/20): hd2-memtools
  findings/skeleton.md. Reads by name in Lua: Unit.node + Unit.world_pose (hd2-vr ENGINE_NOTES).
- Engine safety: bindings do not check args (wrong unit = native crash); never iterate World.units
  calling into each unit (crashed the game 2026-10-11); wrap engine calls in pcall; find things from
  OUTSIDE with hd2-memtools first.

## THE gating question (do this first)
Do bones that exist only in the armour piece (not in any animation) keep a rotation the mod writes,
while the Helldiver animates normally?
- Hypothesis: yes. The animation only writes joints it has tracks for; added bones have none.
- Test: patch one armour piece (a lower-body/torso piece of a common armour) with 1 added bone
  parented to the pelvis, weighted to a visible test flap. In Lua, find the local player's armour
  unit (reuse hd2-vr's own-Helldiver lookup, not a World.units loop), find the node by name, write a
  fixed 45 deg rotation every frame in the render hook before the original render (then try once
  only, and the update phase). Watch: does the flap hold the angle while walking? Confirm from
  outside with hd2-memtools bonescan (find the armour unit's matrices, see the bone's value).
- Also read: how the game's own jiggle bones are defined (what the ponytail mod's `jiggle_bone`
  relies on: a name convention? a physics/props resource?). If the engine simulates them, does
  it overwrite our writes, and does it expose parameters we can reuse? Facts only.
- If yes: build the chains + solver. If no: look for the engine's late pose hook
  (update_animations_with_callback was noted as an IK hook in hd2-vr's plan) or set a per-bone mode.

## Progress 2026-10-15 (aero): gating test built, waiting for the in-game run
- Built: `./build.sh 0.1.0` -> dist/HD2-Dress-0.1.0.zip (Lua addon, mod/hd2dress.lua) and
  dist/HD2-Dress-gate-armour-0.1.0.zip (armour patch, tools/build_gate_patch.py). Offline checks:
  tools/test_hd2dress.lua (fake engine: kept / reset detection, key cycle, world change),
  pack.py selftest, the addon patch is byte-identical to hd2-vr's packer output, and the armour
  patch reloads in the SDK with the 3 bones (names, parents, positions) and weights intact.
- Test armour: B-01 Tactical hip armour (Hip_Armor_Slim 2f66b9373cb58485, Hip_Armor_Stocky
  0387a158d04848f4). 3 added bones: dress_test_a (parent hips, written by the mod), dress_test_b
  (child of a, never written), dress_ctrl (parent hips, never written: control); a flap behind the
  hips on each (back-left = test, back-right = control), facing the third-person camera.
- **B-01 variations share their units** (Variation 1 and 2 have identical unit ids; only
  materials differ). So the gate patch and the HD2 Jaeger patch touch the same units: disable the
  Jaeger zip in Arsenal while testing. Any B-01 variation shows the test.
- HOME cycles: off -> hold @render -> hold @update -> once -> swing @render -> off. The log
  (%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\HD2Dress.log) says every 2 s how many frames
  the bone still held our rotation (kept), was back at rest (reset) or held something else (other),
  the measured flap angle, and whether the control stayed on the pelvis.
- How to read it: kept ~ all frames + the flap visibly tilted 45 deg while walking = YES (gate
  passed, go to milestone 2). reset ~ all frames = the engine rewrites added bones (look for the
  late pose hook). kept in the log but the flap does not show it = the renderer uses an earlier
  pose (the Jaeger flicker case): compare hold @render vs hold @update.
- Engine jiggle bones (SDK facts, HD2SDK CE v3.11.0): they are NOT in the armour unit. They are
  per-bone "ragdoll" entries in the animation STATE MACHINE resource (stingray/state_machine.py:
  bone index, 9 floats; the SDK's disabled "Set Jiggle Bone" button names the first two Weight and
  Gravity (-9.8 default), the other 7 are unknown; plus a u64 hash and an enum). So a jiggle bone
  needs the bone in a skeleton that state machine drives; the engine simulates it, with no
  collision we know of. Open: does the engine also simulate jiggle on armour-only bones, and would
  it overwrite our writes (only matters if we ever add ragdoll entries; the gate patch adds none).
- Tooling on aero: Blender 5.2.2 + HD2SDK in ~/apps (hd2-jaeger tools/setup_blender_sdk.sh, now
  with an ar + tar fallback because aero has no bsdtar).

## Gate run 1 (2026-10-15, aero, v0.1.0, ship, solo): the engine leaves added bones alone
- Every mode: kept = every frame, reset 0, other 0 (hold @render, hold @update, once, swing; ~17 fps
  on aero). "Once" held for 8 s from a single write: nothing rewrites armour-only bones.
- The WORLD pose follows: flap angle (test -> child bone direction vs the body's down axis) went
  from ~1-5 deg (off) to 30-42 deg (hold 45; the body lean while running is in that number). Swing
  averaged ~32 deg = the mean of |50 sin| over one full cycle (the 2 s window is one 0.5 Hz cycle),
  as expected. The child bone follows its parent; the control never moved (0.0000 m drift).
- Visual check was too hard at aero's resolution. v0.1.1 adds HD2Dress_trace.csv (every frame:
  bone positions in the pelvis frame, angle vs the untouched control flap) and a per-window
  "vs the control flap" line (avg/min/max).
- Still open: does skinning (what is drawn) use this pose? The scene graph has it; the Jaeger
  flicker case had a renderer using an older pose. A visible check (or a larger test flap) closes it.
- Install note: the patches were copied into the game folder as patch_4 (addon) and patch_5
  (armour), not through Arsenal; an Arsenal deploy may remove them.

## Gate run 2 (v0.1.1, aero, 640x360 gamescope) and two freezes
- Hold @render / hold @update / once: the test bone's WORLD rotation was exactly 45.0 deg from the
  control's on every frame (min = max = 45.0), and the child tip sat at a fixed spot in the pelvis
  frame (-0.164 0.021 0.100) while walking. Trace: 951 rows. The scene graph side is settled.
- The game froze twice on aero with the addon running: run 1 when opening the loadout menu
  (~142 s, swing mode), run 2 while walking ~4 s into "once" (~78 s). Logs end cleanly, no errors,
  no OOM in the journal. Unknown whether the addon is involved (aero barely runs the game). To
  separate: one session without patch_4/5, or run on bongo.

## v0.2.0: milestone 2 (one spring chain) + freeze diagnosis
- HOME mode 5 "SPRING CHAIN": dress_test_a + dress_test_b become a 2-joint verlet chain
  (mod/lib/chain.lua, pure Lua, no engine calls: gravity, damping, spring back to the rest shape,
  exact segment lengths, cone limit MAX_ANGLE, teleport reset, FOLLOW). Fixed 60 Hz physics step
  with interpolated anchor/targets: same sway at 17, 60 and 144 fps (tools/test_chain.lua).
  Bone rotations: shortest rotation from each bone's rest direction (Rh * rest) to its simulated
  segment, converted back to local; b's tip direction = a -> b at rest (both bones built pointing
  the same way). Writes both test bones in the render hook, then World.update_unit.
- Live tuning: HD2Dress_settings.txt beside the log (written with defaults + one-line help on first
  start), re-read every 2 s. Defaults: GRAVITY 9.81, DAMPING 0.05, STIFFNESS 0.02, FOLLOW 0,
  MAX_ANGLE 110, SUBSTEP_HZ 60, TELEPORT 1.5, TIP_LEN 0.2. Claude can edit it from Linux in the
  prefix while the user plays. (Mod Options page = milestone 6.)
- Trace adds tip_x/y/z (chain tip in the pelvis frame) and b_vs_a_deg (bend).
- Freeze diagnosis: HD2Dress_heartbeat.txt is rewritten at every stage of every frame; run
  `python3 tools/freeze_watch.py` while playing. On a stall of 8 s it writes freeze-reports/<time>.txt:
  the last stage ("(not ours)" = inside the game's own update/render), per-thread CPU and the
  syscall each waits in, memory, log/trace tails, GPU/OOM kernel messages. Read-only: no debugger
  attach (anti-cheat).

## Freezes on aero = Intel GPU hangs, not our code (2026-10-15)
- All three freezes today line up with kernel "i915 ... GPU HANG ... context reset" (09:14:06,
  09:18:30, 09:31:15). The v0.2.0 heartbeat at the third: "render: done (between frames)": our
  code had finished; the hang was in the game's rendering. Reports: freeze-reports/.
- Triggers seen: opening the loadout menu; ~4 s into "once" (one write, then nothing written);
  standing up from a crouch emote with the spring chain on.
- Not settled whether the gate armour patch is involved: no GPU hang in 15 aero launches on Oct 9
  and 14, three today, all with patch_5 installed, BUT today is also the first real play at
  640x360 through gamescope. The patch data checks out (no NaN/inf/huge values in any LOD; bone
  remaps in range; LOD1-3 are now LOD0 copies via SDK Auto LODs, LOD4 untouched).
- To separate: play the same way (B-01, crouch emote, loadout menu) without patch_4/5; or the
  same with them on bongo (AMD).
- Spring chain in game (before the hang): kept every frame; standing still it hangs ~11 deg from
  the control flap (it hangs plumb under gravity while the control follows the pelvis tilt); the
  crouch-to-stand swung it to ~57 deg.

## Offline simulator (2026-10-15): develop without the game
- `sim/run.sh NAME "ID:LOOPS ..." [KEY=value ...]` -> sim/videos/NAME.mp4 in ~30 s. Same
  mod/lib/chain.lua as the game, on the game's OWN animations: sim/anim_export.py loads the avatar
  unit 4d1c334d294dfa97 (archive 18235e0c9ec0e636) and its state machine through HD2SDK (3201
  animations, 31 layers; 6 ragdoll/jiggle entries) and samples joint world positions + the rest
  pose. Layer 0 (320 animations, base body) is exported to sim/anims/layer0.json (not committed,
  rebuilt by run.sh). State names are murmur64 hashes; only "dead" matched common words, so
  sim/classify.py sorts by motion. Animations run in place; prepare.py rebuilds world motion from
  the planted foot.
- Known ids: standing 14033616244713305418; forward run 8958390548417319837 (~1.3 m/s);
  faster 4928390151762733173 (~1.7 m/s); crouch walk 10224704622709553933; layer 0 state 1 =
  0.75 s directional jog cycles; states 25-32 crouch cycles; 62/63 upright run/sprint cycles.
- Skirt model in run_sim.lua: ring of N_CHAINS=10 chains x 3 joints (14 cm) on an elliptic waist
  ring (z 0.93, 20 x 16 cm), 18 deg flare; capsules on thighs (r 8.5 cm) and shins (6 cm).
- milestone 4 done in chain.lua: capsule colliders (interpolated across substeps, COLLIDE_ITER,
  MARGIN). Results: run+stop rigid skirt has legs through it in 73/159 frames (7.7 cm deep),
  physics 0; crouch walk rigid 121/199 (8.1 cm), physics 0. 0.2 ms per frame for 10 chains (LuaJIT).
- Video: red = physics + collision, blue = rigid (plain skinning), side by side.

## Surface collision (skirt.lua), after the user saw legs flow through the cloth
- User (video review): "the red one does have physics but seems to make no attempt to not clip the
  legs". Correct: chain.lua only pushed JOINTS out; the cloth between joints and between chains
  went through the leg, and the renderer's subdivision pulled the cloth inward too. My stat was
  joint-only, so it said 0 while the video showed clipping. Lesson: measure what is drawn.
- mod/lib/skirt.lua: all chains solved together; neighbours tied (may bunch, may not spread more than
  STRETCH 15%); collision samples each panel (SAMPLES 4 per side) and pushes the 4 joints that span
  the point; anchors fixed; ITER 3; scalar inner loop + bounds test. 0.8 ms/frame for 10x3 in LuaJIT.
- Thigh collider starts THIGH_START 10% down the thigh (its top is inside the hips); MARGIN 2 cm.
- Measured on the drawn surface (6x6 per panel, no margin): run+stop 0 frames > 5 mm (rigid 78/159,
  8.2 cm); crouch walk 0 frames (worst 0.3 cm; rigid 125/199, 8.3 cm). The waistband row is fixed to
  the body: the thigh reaches 5.8 cm into it when crouching (a real dress weights it to the body).
- tools/test_skirt.lua: a thigh capsule through the front panel: joint-only chains leak 6 cm, the
  surface solver 0.
- Open (looks): running shoves the skirt up and it bunches/crumples at the hips (no bending
  stiffness, light damping). Tuning + a bend constraint next.
- User wish, later step: other players' dresses simulated too (needs finding their armour units
  without a world scan, plus their legs).

## v0.3.0: generic dress runtime + auto-rig (2026-10-15)
- tools/dress_autorig.py: any armour mod patch -> a small rig patch (only the rigged units; install
  after the mod) + hd2dress_register.lua/.json. ~50 s. Needs st.AutoSaveUnitMaterials = False (else
  HD2SDK re-saves the mod's materials and BC7-encodes every texture: 10+ min) and a NEW patch (not
  re-saving the mod's whole patch). Hem = lowest cloth per sector (a percentile cut the slim front).
- First mod: "Arknight Endfield Xaihi EX-00" (Nexus 8340, ~/Downloads zip), replaces CM-10
  Clinician AND EX-00 Prototype X (shared units). Dress in Torso_Undergarment Slim
  52258dfe5839afd3 / Stocky 2cf4f8d5b5b713e1 (21.8k verts); originally weighted rigidly to
  hips/thighs; its rig already has the game's cape1..8 bones (unused by the dress). Slim cut is
  shorter at the front (hem 0.70) than stocky (0.29-0.41).
- Runtime (mod/hd2dress.lua, dress section): HD2DRESS_REGISTRY (global, filled by registration
  addons; all Bingus addons share one Lua state); finds the registered unit nearest the avatar
  (units_by_resource only), bones dress_cNN_bK, measures rest rotations/directions/lengths once,
  legs = avatar l/r_thigh/knee/foot; Skirt.step + bone write in the render hook. END toggles.
  Settings file gained DRESS, STRETCH, SAMPLES, ITER, MARGIN, THIGH_R, SHIN_R, THIGH_START.
- Sim on the real chains (sim/dress_rest.py, run_sim.lua DRESS=...): Arknight stocky run+stop and
  crouch walk: 0 frames with legs through the cloth (rigid-to-hips 68/159, 124/199).
- Zips: dist/HD2-Dress-0.3.0.zip; dist/thirdparty/ (gitignored: derived from someone else's mod)
  holds the Arknight rig + registration zips. docs/AUTHORING.md = the two author paths.
- Admin (Nexus/Discord): "cloth only by injecting something like VRC cloth; the game's Havok cloth
  is not cracked". We do inject our own: a bone-chain solver in Lua (like VRChat PhysBones /
  Unity Dynamic Bone), not the game's Havok cloth. Idea for later: the game's cape bones
  (cape1..8, simulated by the game) might move a coat tail for everyone, other players included.

## Real-armour preview + first in-game install of a dress (2026-10-15)
- sim/render_armor.py: poses a whole armour mod (every piece of one body type) from the game's own
  animation (anim_export.py --all-bones -> prepare.py also writes JSON), bends the dress bones to
  the simulation, renders it beside the mod as published. Added bones come back from a patch under
  their murmur32 hash, not their name (dname()). ~2 min per 160 frames at 960x720.
  Videos: sim/videos/arknight_armor_run_stop.mp4, arknight_armor_crouch.mp4.
- Looks: it trails and swings; at a stop it swings forward and the back panels splay apart; the
  tail (part of the dress mesh) swings with the skirt (--exclude-back would keep it rigid). Feel
  tuning still open.
- Installed on aero (not through Arsenal): patch_4 HD2 Dress 0.3.0, patch_5 the original Arknight
  mod (replaced my B-01 gate armour), patch_6 the rig, patch_7 the registration. Settings file got
  the v0.3 keys appended. Wear CM-10 Clinician or EX-00 Prototype X (the user's Helldiver is stocky).

## v0.4.0: cloth without spring, inelastic leg contact, tails (2026-10-15)
- User review of v0.3 videos: needs damping; running = legs hit the dress and it "spasms"; a
  jiggle at the end (bounce back after the A-pose snap): "it's cloth, it has no spring, it just
  is heavy and drapes where it's pushed"; the tail should barely move and slither like a reptile.
- Physics changes (chain.lua + skirt.lua): SHAPE = pull toward the rest shape that adds NO speed
  (velocity-neutral: p and pp move together), SHAPE_HEM tapers it down the skirt; STIFFNESS (springy)
  now 0. Collisions are inelastic: a pushed joint loses its speed INTO the leg, keeps its sliding
  speed, and the push adds only BOUNCE (0). Keeping the inward speed (first try) made the cloth
  tunnel through the knee when crouching (19 m/s spikes). Defaults: DAMPING 0.25, SHAPE 0.08,
  SHAPE_HEM 0.04, BOUNCE 0.
- Sim feel metrics (run_sim.lua): cloth speed vs its rest place (median/99%/max) and the number
  of back-and-forth hem swings after the stop. Old springy model: run max 9.3 m/s, 45 swings after
  the stop (crouch 54). v0.4: run max 4.2 m/s, 0 swings; crouch max 4.9, 1-2 swings. Clips still 0.
- Tails: autorig finds connected mesh pieces reaching > 0.6 m behind the hips axis and < 0.4 m
  wide (--tail none to skip), gives them their own chain dress_t01_b1..b5 (root nearest the hips,
  joints by distance from the root), root blends into the body. Registry entry gains
  tails = { { prefix, bones, lengths } }. Runtime/sim: chain.lua with Chain.group_params(P, 'TAIL',
  Chain.TAIL_DEFAULTS) (settings TAIL_<key>), plus Chain.wave: a sideways travelling wave, scaled by
  walking speed (TAIL_WAVE 4 cm at the tip, 1.2 Hz). Tail defaults: DAMPING 0.35, SHAPE 0.35->0.15,
  FOLLOW 0.5, GRAVITY 0.5. Tail tip off rest: avg ~6 cm, peak ~22-26 cm (leg bumps / snaps).
  Arknight tail: 292 vertices, 1.15 m, 5 bones.
- In-game test moved to bongo tonight (user won't launch on aero). The aero game folder still has
  v0.3 installed (patch_4..7). On bongo: install via Arsenal in this order: the original Arknight mod,
  HD2-Dress-0.4.0, the rig zip, the registration zip (all in dist/ and dist/thirdparty/).
- aero CPU at 11:15: five Dolphin thumbnail workers (kioworker thumbnail.so) at 100 % each, one on
  /tmp/gd_laptop.bin (not ours).

## v0.5.0: anti hula hoop (2026-10-15)
- User: "acts like a hula hoop, hoops of bones instead of vertical lines; should flex and compress
  to swish with the legs". Causes: the ring tie (every level held as a hoop), only 4 bend heights
  (creases ring the whole skirt), no leg-driven swing, uniform heavy damping.
- skirt.lua: TIE 0.3 (was effectively 1), STRETCH 0.3, DAMPING_HEM 0.12 (waist 0.25),
  WEIGHT_TOP 3 (per-level inverse weight in the collision push), LEG_FOLLOW 0.6 + LEG_EMA 1.5 s:
  Skirt.leg_follow turns each strip's rest targets about the hip joint by the thigh's swing away
  from its running average direction (in the hips frame; no rest pose needed), shared by strips by
  1/d^2 to each hip. Autorig default 6 bones per strip.
- Sim: clean (0 clip frames, 0-1 swings after a stop). Hoop metric (share of hem motion that is
  per-strip, not ring-wide) ~72 % run / 64 % crouch, barely changed: it doesn't capture the look;
  judge by video (sim/videos/arknight_v05_*.mp4, 800x600, both rendered in parallel in 5 min).
- Zips for bongo: dist/HD2-Dress-0.5.0.zip, dist/thirdparty/*-0.5.0.zip (rig is 12x6 + tail).
- /tmp on aero: SDK texture dumps (numbered .dds/.png) land there on every Blender run; cleaned.

## v0.5.1 (bongo, 2026-10-16): the skirt starts at the belt
- User screenshot (armory): the bones started too low; the red line = the belt. Mesh profile of the
  Arknight torso: corset narrowest at z 1.18-1.20, belt = dense band at 1.12-1.16. Re-rigged with
  --waist 1.11 --blend 0.06 (was 0.93 = an estimate from the hip joint): 11.6k cloth vertices (was
  8.5k), the belt stays rigid, everything under it moves (checked by bending the bones in Blender).
- Longer chains -> bigger panels: 7 run frames clipped up to 1.4 cm with MARGIN 0.02; more samples
  didn't help, MARGIN 0.03 did (0 frames). Default MARGIN now 0.03 (runtime + sim).
- Cost in the sim: 2.2 ms per frame for 12x6 + tail (LuaJIT on bongo). Watch it in game.
- Lesson for the auto-rig: guess the waist from the mesh (the belt / narrowest girth above the
  hips), not a fixed 0.93. To do.

## v0.5.2 (bongo, 2026-10-16): crash in the Superstore preview fixed
- First in-game run of the dress (bongo): the user owns neither EX-00 nor CM-10, so the dress only
  appeared on the Superstore preview Helldiver. HD2 Dress found it ("12 chains x 6 bones, 1 tail;
  legs found"), the dress fell with gravity (physics ran), then the game crashed ~5 s later.
- freeze-reports/2026-10-16_01-21-51.txt: heartbeat "render: dress step" (inside OUR code), all
  threads idle = a native crash, not a hang. The gate log showed 2 Helldivers (the store spawns a
  preview one). Cause: dress_find checked U.alive only every 2 s; the store swapped its preview
  Helldiver and dress_step kept calling into the deleted unit (native crash, pcall can't catch).
- Fix: U.alive on the dress unit AND the legs' Helldiver every frame, before any other call; forget
  and re-find if either is gone. tools/test_dress_runtime.lua now deletes both mid-run and counts
  calls into deleted units: old code 936, fixed 0.
- Testing problem: the user can't wear the dress (doesn't own the armours). Options: preview-only,
  or retarget the Arknight pieces onto an armour the user owns (B-01 is owned by everyone).

## Retarget onto B-01 (bongo, 2026-10-16)
- dev/retarget.py (moved out of tools/ 2026-10-17: a personal test helper, not shipped or documented for authors): copies a mod's pieces (whole units, like HD2SDK "copy to new id") onto another
  armour's unit ids by (slot, piece type, body type); the rigged dress pieces come from the rig
  patch; target pieces without a counterpart become a 1 mm triangle; --helmet maps the mod's head
  piece onto the target helmet; writes a new registration with the target ids. ~80 s.
- Arknight on B-01: 19 pieces copied, 4 shoulder pads blanked, helmet = the mod's head piece
  (59c8aa2adc6c60fe). Torso undergarments: slim fa269172bd08695b, stocky e57627fe6214bdd8 (192
  bones, 77 dress bones = 12x6 + 5 tail). Verified by reloading the patch.
- Install: original Arknight mod (materials/textures), HD2-Dress-0.5.2, "Arknight on B-01" patch,
  its registration. Jaeger (also B-01) must be off. Wear B-01 Tactical armour + helmet.

## v0.5.3 (bongo, first real in-game tuning, 2026-10-16): body-relative damping
- In game on B-01 (retarget): 0.6-0.75 ms per frame, the safety check handled preview/armory unit
  swaps without crashing. But walking (not even running) pushed the dress through the legs; with a
  20 cm test clearance the skirt ballooned at one ring and "rode up"; screenshots while running:
  the skirt streamed out horizontally behind the Helldiver, legs uncovered.
- Cause: DAMPING acted on the speed over the GROUND = a gale at game speeds (the sim's animation
  moved at ~1.3 m/s; the game moves several times faster). Walking pressed the front panels back
  into the legs. Also measured: the dress's inner layers sit ~5-6 cm inside the median cloth radius
  the chains follow (worst sectors 10-20 cm, pouches/tabs); a to-do for the auto-rig.
- Fix (chain.lua + skirt.lua): damping on the speed relative to the strip's anchor (the body),
  REL_DAMP 1 (0 = old), plus AIR 0.01 over the ground. FOLLOW-carried motion is not counted twice.
  prepare.py --speed scales the rebuilt world motion; run_sim reports hem trailing (max + mid-run).
- At ~5 m/s (sim): old 108 clip frames, 79 cm mid-run trailing; body-relative 64 / 51; plus heavier
  cloth (DAMPING 0.4 / HEM 0.25, SHAPE 0.12 / 0.07, MAX_ANGLE 60): 3 frames (<1 cm), 23 cm, 0 bounces.
  Slow run and crouch: 0 clip frames, 0 bounces. These are the new defaults.
- Deployed by swapping the addon file in place (patch_3 on bongo) and editing the settings file
  (test values out, REL_DAMP/AIR in). Needs a game restart.

## WORKS IN GAME (bongo, 2026-10-16, v0.5.3)
- User, running in a mission in B-01 with the Arknight dress: "works well now" (screenshot: the skirt
  covers the legs mid-stride and flows with the run). ~0.7 ms per frame, armour/preview swaps handled.
- Open next: auto-rig waist detection from the mesh (belt), chains on the innermost cloth layer,
  body colliders + safeties (dive/prone/ragdoll), Blender editing panel, weapon pinning, other
  players, data-only fallback (weight optimizer) in case Lua mods get blocked.

## NEXT SESSION (set by the user 2026-10-16): post it, perfect the auto-rig, settings UI
1. Post it (release). Before anything public: the fleet rule = do the pending 1Password secrets
   review with the user before any public push/repo; pick a licence (user's call); ship ONLY our
   own work: the HD2 Dress addon + tools (autorig, retarget, sim), never dist/thirdparty (the
   Arknight mesh belongs to its author; ask that author, or ship instructions to run the tool on
   their mod). Release page text: the Discord explainer + the 1-paragraph summary; videos from
   sim/videos and in-game screenshots. Remove the B-01 gate test (HOME key) from the release build.
2. Perfect the auto-rig: find the waist from the mesh (belt band / narrowest girth above the hips,
   Arknight: belt 1.12-1.16, corset 1.18-1.20; we had to pass --waist 1.11 by hand); chains on the
   innermost cloth layer (inner layers sit ~5-6 cm inside the median, worst 10-20 cm); keep tail
   detection; one command from a mod zip to installable zips (rig + registration, optional
   retarget onto an owned armour).
3. Settings UI for fine-tuning the physics: in game via Mod Options Menu (installed on bongo: a
   native MODS tab with toggles/choices/sliders, needs BSL) with sliders for the live values
   (damping waist/hem, shape, weight, leg follow, tail feel, clearance); keep the text file as the
   store. Check how Mod Options Menu registers a mod's options before writing code.

## MAIN NEXT STEP (2026-10-16): the author add-on for Blender
User decision: authors tune the physics themselves in Blender; players get one file. The user knows
little Blender and will test it with an author who is a known Blender pro (design for that person's
normal workflow, test with them before any public release).
- Flow: the author rigs/weights their model as usual with HD2SDK. Then the HD2 Dress panel:
  1. Rig: auto-rig button (belt detection, strips, tail, weights), preview colours, move joints,
     add/remove strips, mark groups (skirt ring / free chain like hair or ribbons / tail).
  2. Tune: per bone / strip / group sliders (damping, weight, shape memory, gravity, max swing, leg
     follow, collision on/off, tail slither). Stored as Blender custom properties on the bones.
  3. Live preview: the game's own animations (walk, jog, sprint, stop, crouch, dive, prone) looping
     in the viewport at real game speed, the SAME Lua solver running live (Lua inside Blender's
     Python, e.g. lupa; fallback a Python port), sliders change it while it loops; readout of clip
     frames / trailing / bounces; slow-motion toggle; red marks where cloth gets close to a leg.
  4. Export: the rig patch + registration (values baked in); ideally the registration inside the
     same patch (one patch can hold units and a Lua resource); one release zip offering "with
     physics" (needs HD2 Dress + BSL) and "plain" as Arsenal options. Check how Arsenal shows
     Options (pick-one vs toggles) first.
- Runtime: per-bone values from the registration > group values > global; the player's in-game
  overlay SCALES the author's values (e.g. +10 % damping for everything), never replaces them.
- Also planned: in-game tuning overlay (user wants in game, not desktop), auto-rig fixes (belt
  detection, smooth the zig-zag back strips, innermost cloth layer), explosion gusts (physics easy,
  the signal needs research with the memory tools on bongo), body colliders + safeties.
- Effort estimate given to the user: frame + auto-rig + export ~1 day, live preview ~2 days, joint
  editing + per-bone sliders + groups ~1-2 days, polish + docs + a second dress mod ~1 day.

## Add-on v0.1 in use (aero, 2026-10-16) + the "parts" plan
- First real use by the user on a fresh mod: Miyabi (Nexus 9100, for SC-37/AF-50/CE-64/CM-17/FS-05).
  GUI bugs fixed: auto-rig on a hidden skeleton (mode_set poll), Reload Scripts not reloading helper
  modules, HD2SDK resetting its game path on Reload Scripts, a property update lambda returning a
  value. The skeleton now shows after auto-rig (dress bones only, coloured per strip).
- "Black" in strip-colour view = meshes without our colour data: here the mod's REPEATED copies of
  each piece (one per armour, 15 copies) overlapping the rigged one. Load now shows one copy and
  remembers all their unit ids; export writes the rigged unit under every copy's id + one
  registration entry per copy.
- Miyabi has: a two-layer skirt (inner pleats + outer slit panel, separate mesh parts in the torso
  piece), very long hair as a curtain down the back to the knees + fox ears (helmet piece), one wide
  open sleeve on the right arm (arm piece), an empty jacket sleeve draped off the left shoulder and
  the jacket's front panels (torso piece).
- User: "I don't want it to be a half-assed attempt that barely works": build a general PARTS system:
  1. find every loose mesh part in every piece, where it attaches (bone), and its shape;
  2. part types: RING (skirt; several layers, outer kept outside inner), SHEET (open row of chains:
     hair curtain, cape, coat tail, hanging sleeve, front panels), STRAND (single chain: tail, ear,
     ribbon), CUFF (ring around a limb: wide sleeves);
  3. body colliders for all of them: thighs, shins, pelvis, torso, upper arms, forearms, head;
  4. add-on: a parts list (suggested type, tick to enable, highlight, per-part settings), parts in
     several pieces (helmet, arms, torso) per dress;
  5. runtime: a dress = several units and parts; skirt.lua gains open sheets (no wrap-around) and
     layer ordering.

## Pro-modeller track (bongo, 2026-10-16): auto-rig parked, "Use my bones"
User: a pro modeller places bones without help; remove the auto-rigger for now and close the gaps
one by one: 1 use my bones, 2 several pieces per outfit, 3 open sheets + body colliders,
4 one-zip export + pro guide.
- Step 1 DONE: the add-on panel has no auto-rig; "Use my bones" reads hand-placed bones by name
  (dress_c01_b1.. = skirt strips, dress_<part>_c01_b1.. = other strip parts, dress_t01_b1.. =
  single chains), positions from the rest pose (heads + the last tail), and checks: numbering
  gaps, equal bone count per strip, parent chain, first bone on a body bone, cloth actually
  weighted. Problems are listed in plain language in the panel. Preview, tuning and export work
  on hand-made bones (tested: stand-in rig on the Arknight dress, then deliberately broken).
  rigging.autorig / detect_waist stay in the code, unregistered, for later.
- bongo add-on setup: lupa in Blender's Python, ~/apps/.../addons/hd2_dress -> repo, enabled,
  app-menu entry "HD2 Dress Blender".
- Step 2 DONE (v0.6.0): several pieces per outfit. Runtime: every registered piece within 1.5 m
  of one Helldiver is simulated (DR.items), each chain hangs from its own parent bone (registry
  entry.parents per strip, tails[i].parent; default hips), pieces with only single chains (hair
  strands in a helmet) work, leg-follow only for strips hanging from the hips, per-frame alive check
  per piece. Add-on: Use my bones on each piece; the preview drives every rigged piece; export puts
  all pieces (and their repeated copies) into ONE rig patch + ONE registration. Tested: Arknight
  dress strips + a hand-placed 4-bone hair chain on the head piece (registration: 3 entries, head x2
  copies + dress); runtime fake-engine test now has two pieces.

- Step 3 DONE (v0.7.0, bongo 2026-10-16): open sheets, layers, whole-body colliders, safeties.
  - Runtime: a piece has several strip parts (registration entry.parts: name, type RING|SHEET,
    layer, strips, parents, format, per-bone values); 0.6 entries still load as one ring. A SHEET is
    not joined last strip to first. Outer layers keep LAYER_GAP (2 cm) more clearance per layer
    (cheap stand-in for cloth-cloth collision; outer stays outside inner wherever the body pushes).
  - mod/lib/body.lua: capsules for thighs, shins, pelvis (hip to hip), torso (spine1 to neck), upper
    arms, forearms, head (sphere above the head joint); one file for the game, Blender and the tests.
    A part ignores only colliders its anchors start INSIDE (not inside the clearance: a cape on the
    back must keep the torso). BODY_COLLIDE 0 = legs only.
  - Safeties: DEEP (cloth a body part passes through in ONE substep goes back to the side it came
    from; the first try, "the rest side", yanked a leg-pushed skirt back through the leg: wrong),
    MAX_SPEED 12 m/s against the body, a floor from each joint's body thickness (Body.SURFACE: right
    standing and prone) that drops at once but rises at FLOOR_RISE 0.5 m/s (in a jump or dive the
    cloth may hang below the body), MAX_ANGLE_PUSHED 120 deg (cloth a body part is pushing may
    fold further than the free 60 deg limit, or the hem sinks into a sitting Helldiver's thigh).
  - Stress run (sim/stress_prepare.py + sim/stress.lua): the 3014 game animations exported with arm
    and torso joints (sim/anim_export.py now records them), moves picked by motion: dive
    15973994310853105570, prone crawl 962193287716325945, get up 2463154135084150628, hit reaction
    2635010984077288310 (hips 9 m/s, hands 17 m/s), knock-down 14215076477113324800 (hips 10 m/s; its
    hand reaches 55 cm below the start, a slope). Outfit: Arknight skirt 12x6 + cape sheet 5x5 + 3 hair
    strands, 1.1 ms/frame. Cloth inside the body: legs only 6483 joint-frames (hair 13 cm in the
    torso) -> whole body 18 (worst 1.4 cm: the hem sat on under a thigh on the floor). Below the
    body's lowest surface: 53 cm without the floor -> under 5 cm, except right after the knock-down's
    55 cm drop (the floor rises slowly by design). Run/crouch feel unchanged vs 0.6.
  - Add-on: parts list (Ring/Sheet guess + buttons, layer -/+, saved on the skeleton as hd2d_parts),
    every part previewed against the whole body, Body tuning box, new preview moves (Dive, Prone
    crawl, Get up, Hit reaction), export writes entry.parts + the body sizes. tools/test_addon.py:
    66/66 in a real Blender window.
  - Not yet: an in-game test of 0.6/0.7 (dist/HD2-Dress-0.7.0.zip built); real cloth-cloth
    collision between layers; cuffs on arms are rings hanging from an elbow (should work, untested
    on a real mesh).

## Milestones
1. Gating test (above). 2. One chain, spring only. 3. Full skirt ring, leg-driven roots.
4. Thigh/shin capsule collision. 5. Extreme poses: sprint, dive, prone, ragdoll, sitting in
vehicles, the drop pod. 6. Tuning page. 7. A real dress mesh (the user makes or picks the art; do
not make art assets).

## Limits to state honestly
- Client-side code mod: other players see the plain mesh moving with plain skinning, no physics.
- Only works where the mod runs: ship, missions (test both; the Jaeger puppet crashed once on a
  mission spawn, cause was a spawned armour piece without an owner; we spawn nothing here).
- Cape: the game already simulates capes; check how a dress coexists with one.

## Release (only if the user decides to publish)
- Its own repo/mod, nothing from hd2-jaeger (that one is never published).
- Originality check against reference mods (hd2-vr docs/RELEASE_CHECKLIST.md approach).
- Pick a license (user's call). Do the pending 1Password secrets review before any public push
  (fleet rule). Until then Forgejo only.

## Where things are
- This repo: https://github.com/OceanMan20/hd2-dress.git
- Related (git fetch/pull first, clones go stale): OceanMan/hd2-vr (runtime patterns, F5 reload,
  Mod Options page), OceanMan/hd2-jaeger (patch tools, added-bone proof), OceanMan/hd2-memtools
  (outside reader), OceanMan/llm-kit (in-game research only).
- In-game steps for the user go at the END of a message; start timed captures only after the reply.

## 2026-10-17: Havok cloth edited without Lua (first success)

- Earlier "patch ignored" results were a false negative. Arsenal redeployed patch_0..11 at 02:46, so
  patch_12..15 vanished and the test file sat at patch_16 after a gap. The game stops at the first
  missing patch number. Moved to patch_12 and it loads.
- Each cape cloth resource (avatar archive 18235e0c9ec0e636, ids 3c33cf10a26cbb3e / ea846ef460cc5ba0)
  holds simulation settings twice: tagfile 2 (hclClothSetupContainer, the authoring recipe) and
  tagfile 4 (hclClothData, the baked runtime). Both get loaded into memory (memory search shows both).
- Flipping gravity to +9.81 in **tagfile 4 only** makes the cape float up in game
  (docs/img/havok_cape_gravity_up.jpg vs havok_cape_normal.jpg). hclClothData is the live data;
  the recipe copy is not needed for the sim.
- Data after the last tagfile (~247 KB) has no gravity values: a native blob, not yet decoded.
- Scripts: tools/havok/ (run with Blender + HD2SDK, write a base-archive patch).
- Next: change other hclClothData values (constraints, max distance, collidables), then try binding
  hclClothData to a different unit (dress mesh).

## 2026-10-17 (later): how the engine attaches cloth, and live tuning

Engine (helldivers2.exe, cloth code is in the exe, not game.dll; dump from memory, the file is packed):
- Unit spawn (fn 0x788e90) looks up FOUR resources by the unit's own id: physics (table +0x40),
  cloth (+0x48), ragdoll_profile (+0x50), unknown type 57a13425279979d7 (+0x58); type list at
  rva 0x165ddd0. Tables hang off [rva 0x235e310]; lookup fn 0x9f6d60, key = resource id.
- Spawn-physics fn 0x7880c0 creates the cloth (fn 0x7d51d0, "cloth: using %s cloth resource for")
  when the cloth pointer is set and the world allows cloth.
- Live objects found by RTTI vtables: hclClothInstance 0x14d95b8, hclSimClothInstance 0x14d9650,
  hclClothData 0x14ebe98 (tools/havok/re/instances.py).
- A cloth resource placed ONLY in the base-archive patch (9ba626afa44a3aa3.patch_N) under a new id is
  deserialized but never instanced. Placed in a patch of the archive that holds the unit
  (18235e0c9ec0e636.patch_0 under body unit 4d1c334d294dfa97) it IS instanced. Rule: ship the cloth
  in a patch of the unit's own archive (package), with the unit's id.
- That probe (stock cape cloth under the body unit id) took over the visible cape.
- Patch numbers must be contiguous (game stops at the first gap).

Live tuning: writing hclClothData values straight into game memory takes effect at once (gravity
+9.81 written to the probe's 12 settings blocks: cape floated within seconds, no restart).
tools/havok/re/livegrav.py. So tuning can be live; structure changes need a restart for now.

## 2026-10-17 (evening): Havok writer works in game

- tools/havok_writer.py rebuilds all three stock cloth files (both capes, flag) byte for byte: TYPE
  section copied, DATA laid out (unchanged items keep their slot, grown/new items appended 16-aligned),
  ITEM rebuilt, PTCH recomputed (non-null string/pointer/array fields, grouped by field type).
- rebuild_file() also fixes the resource header (tagfile offset/size table at +80.., the native tail
  blob offset, lengths at +16 and +76).
- In game: both capes rebuilt with a lengthened hclClothData name (item moved to the end, file grew)
  plus gravity up. All 3 cloth instances use the rebuilt data, cape floats
  (docs/img/havok_writer_test.jpg). So the loader accepts writer output with a changed layout.
- Ghidra 12.1.4 headless analysis of the memory-dumped engine running in ~/hd2-re (REA's CLI times
  out at 5.5 min on a binary this size; status: ~/hd2-re/status.sh).

## 2026-10-17 (night): engine cloth pipeline read with Ghidra

Query tool: ~/hd2-re/dec.sh OUT RVA[,RVA] (decompiles from the saved project, ~10 s; copies in
tools/havok/re/ghidra). Findings (rva in helldivers2.exe build of 2026-10-17):
- The cloth RESOURCE ("CR2 " container) is loaded in place; offsets become pointers:
  +0x50.. tagfile table {u32 off, u32 size, u64 ptr} for tagfiles 0-3 (1 = skeleton container);
  +0x90 offset of the Stingray tail block; +0xa0..+0x100 pointers into the tail (filled at load);
  +0x108 variant count, +0x110 variant keys (u32), then {off,size,ptr} -> hclClothData (tagfile 4).
  Instances pick the variant whose key matches, else variant 0.
- Tail block (starts with its own offset table 0x20,0x30,0x140,0x160,0x1e0,0x310):
  * a vertex layout for the display buffer: 0xd36 = 3382 vertices (= g_medium_cape), stride 0x3c,
    element format words (0x80020820 ...),
  * per-skeleton tables keyed by 0x975cebbd (hash of the cloth skeleton's name, via +0x68 -> tagfile 1):
    a bone list [count 36: unit node indices 0,3,4,5,6,11,...] used each frame to read the unit's
    node world matrices into the cloth transform set (fn 0x7d3f50), and two 35x4x4 matrix sets
    (bind poses) copied into the instance at creation (fn 0x8a1be0),
  * bulk data (0x318c0.. etc.).
- fn 0x7d51d0 creates the instance (0x8a1be0 -> hclClothInstance), then a 0x90-byte wind/aero object
  (defaults incl. 1.225 = air density, 100, 100, 10, 64).
- fn 0x7d4590 = command queue: 0 create (with collision filter from the resource), 1 enable/disable,
  2 destroy, 3 set cloth state BY NAME (hash -> hclClothData state index): how backpack/LOD swap.
- fn 0x7d3830 / 0x7d3910 set wind parameters / wind vector for every cloth in a world (the ship wind).
- Open: where the renderer takes the cloth output (the tail's vertex layout suggests the engine owns
  a vertex buffer for the display mesh); what the unit-side match is (probe on the body unit drove
  the visible cape).
- Rename test: body-unit probe (18235e0c9ec0e636.patch_0, cloth id 4d1c334d294dfa97) with its display
  buffer names changed g_medium_cape -> g_medium_capX. Result: the probe no longer drove the visible
  cape (the cape's own, gravity-up cloth did: cape floated, docs/img/havok_rename_test.jpg), and the
  GAME FROZE shortly after. So the cloth reaches its mesh by buffer NAME, and a cloth whose buffers
  match no mesh can hang the game: generated cloth must be validated before it ships. Probe moved out.

## 2026-10-17 (night): cloth on an ARMOUR unit works

- Stock cape cloth (renamed dress_probe_04, normal gravity) added under the B-01 hip unit ids
  (Hip_Armor_Slim 2f66b9373cb58485, Hip_Armor_Stocky 0387a158d04848f4) in patch_0 of all 23 archives
  that carry those units (havok_test/patch_b01; find_id.py lists them).
- In game: a dress_probe_04 hclClothInstance exists, and it drives the visible cape (cape hangs
  normally while the capes' own cloth has gravity up). docs/img/havok_b01_armour_cloth.jpg.
- So: armour units get engine cloth from a cloth resource with the unit's id in a patch of the
  unit's archive, and the cloth finds its display mesh by name anywhere on the character.
- To do: find which of the 23 archives the game actually used (so mods patch only what is needed).

## Generator plan (engine cloth from a Blender mesh), 2026-10-17

What a garment's hclClothData needs, all seen in the cape and decodable:
- hclSimClothData: particleDatas {mass, invMass, radius, friction}, fixedParticles, pose positions,
  triangleIndices, staticCollisionMasks, pinch flags, collidables (reuse the cape's 21), transfer motion,
  landscape settings, simulationInfo (gravity, damping).
- Constraint sets (all readable): StandardLink Mx (batches of 4: restLengths, stiffnessA/B, particlesA/B
  + singles), StretchLink Mx, LocalRange {particle, referenceVertex, maximumDistance}, BonePlanes,
  BendStiffness Mx, Volume Mx. v0 plan: StandardLink + StretchLink + LocalRange only.
- Operators: Sim Skin Op / Display Skin Op = hclObjectSpaceSkinPNOperator (boneFromSkinMeshTransforms,
  transformSubset, objectSpaceDeformer with 16-vertex blocks: controlBytes pick 1..8-blend block types,
  vertexIndices, boneIndices, uint8 boneWeights; localPNs = hkPackedVector3 int16 x3 + exponent word:
  value = (int16 << 16) * float_from_bits(word << 16), verified on the cape: vertex 0 -> (0.3726,
  -0.3315, 0.3267) vs pose (0.3726, -0.3314, 0.3297)); MoveParticles (vertex/particle pairs);
  Simulate (constraintExecution order, substeps, iterations); MeshMeshDeform (triangleFromMeshTransforms
  per sim triangle + objectSpaceDeformer + localPNs).
- Stingray tail block: display vertex layout (count, stride, element formats), skeleton-keyed bone list
  (unit node indices), bind matrices.
- Validation before writing (a mismatch froze the game): names, vertex counts, bone indices in range.
Steps: (1) decode every operator fully and rebuild the cape's rest mesh from the data (proves the
decoders); (2) encoders, round-trip the cape through decode->encode; (3) generator from a Blender mesh
using the cape as the template (types, collidables, settings); (4) in-game test on a simple skirt.

## 2026-10-18: test rig, generated engine cloth, debugging to the first render

Generator (tools/gen_engine_cloth.py) + rig (tools/build_testrig_patch.py, 12 flared strips on the
B-01 hips) + exporter (tools/export_unit_mesh.py). Findings, each verified live in game memory:
- Engine cloth render path (fn 0x8a11a0, Havok instantiation callback for type-4 buffers): looks up the
  mesh by murmur32(buffer name) in the character's render object, builds its OWN GPU vertex/index buffers
  from the resource's tail block (fixed 60-byte layout), draws one batch with the mesh's material.
- BUG FIXED: mesh-mesh deform localPNs must hold MESH-space positions/normals (Havok applies
  triangleFromMeshTransforms itself; cape: stored == display rest, error 0). Pre-transforming gave
  scattered strips.
- Tail vertex copy: bone indices/weights = the mesh's own GPU palette data (fixed, harmless either way).
- THE RENDER BLOCKER: a cloth-driven mesh is drawn only with a cloth-capable material. With the armour
  material (or cape material 9562029338072652909) the whole mesh was invisible; with the cape's material
  8444775596724238472 it renders (docs/img/havok_testrig_first_render.jpg, cape texture on hip UVs).
  => cloth parts need a cape-style (cloth shader) material; design: cloth mesh separate from rigid armour.
- STILL OPEN: the sim's 4th (w) lane grows exponentially with gravity + standard links (x30/0.4 s with
  3 link passes, x30/2 s with 1 pass) and overflows to NaN after 4-30 s; the cape's w stays ~1e9. Not
  caused by collision, leash, stretch, bend (added, cape-exact formulas), masses, damping, landscape.
  Live bisection tools: /tmp/resetwatch.py-style reset of all particle buffers then timing.
- Added bend stiffness (cape formulas: weights = closest points of lines AB/CD, curvature =
  -h/(dA*dB), stiffness = -k/sum(w^2 invMass); fit corr 0.99996 over 2320 cape constraints).
- Invisible-cape mod (Nohearldcape) is one texture; ruled out.
- CORRECTION (2026-10-18): the "w-lane runaway" is harmless. Particle positions (xyz) of the test rig are
  all finite; only the unused 4th lane overflows to NaN. The stock capes do the same (two cape instances
  have NaN w with valid xyz). My NaN counts included w. The rig WORKS in game: all 12 strips simulate
  (user: marching/kicks/salute behave correctly). Remaining cosmetic issue: with the borrowed cape
  material on hip UVs, texture squares flicker between metal and a washed-out bright value.

## Research note (2026-10-18): custom (non-HD2) rigs without Lua?
- a tester (SA-7 cloak)'s point: anime mods' real problem is proportions, not physics. C-Rig (Nexus 16897, "C-Rig Runtime
  (ShareLoader)") solves it with Lua: the armour keeps its own authored rig; every frame the runtime
  applies the diver animation rest-relative to that rig, with two-bone arm IK for hands.
- To investigate: can a custom rig be driven WITHOUT Lua? Leads: the engine's own retargeting/animation
  features (units carry bones + state_machine resources; Havok animation has skeleton mappers,
  hkaSkeletonMapper); whether an armour piece can carry its own state machine/animation that follows the
  diver; whether engine cloth/physics constraints could drive bones. Not started.
- Own cloth material: tools/make_cloth_material.py copies the cape cloth material (8444775596724238472,
  cape shader 15780315333863701079; the flag's cloth material uses the same shader) with recoloured
  CapeLut (cols 0,3) and MaterialLut (cols 0,2,5). Yellow id 7200101010101010101 renders on the rig
  (docs/img/havok_testrig_yellow.jpg); squares = hip UVs over the cape pattern (BaseData/IdMasks).
  Install now: patch_12 rig armour, patch_13 material, 23 B-01 archive patch_0 = rig cloth.
- Test rig v2 (TESTRIG_LAYOUT=skirt_shoulders, gen spec testrig-full): connected skirt (24 panels, one
  cloth island) + 12 strips at shoulder height pinned to chest (upper-body bones added to the hip unit;
  17 cape collidables incl. chest/spine2 convex, shoulders, elbows, head). Pins = top row of each island.
  Renders and simulates (docs/img/havok_testrig_skirt_shoulders.jpg).
- Window placement: the HD2 gamescope window has NO window class (title only, set late), so KWin rules
  miss it; KWin script tools/kwin/hd2-portrait (installed in ~/.local/share/kwin/scripts) sends any
  "HELLDIVERS" window to DP-1 (portrait).
- FIX: bones added to an armour unit must copy the real bone's full rest matrix (incl. roll), not just
  head/tail: the game drives the added bone with the real bone's animation, so a different roll rotated
  the shoulder ring 90 degrees. Builder now sets EditBone.matrix from the full skeleton; verified the
  added chest/shoulder/knee/spine2 binds equal the cape skeleton's exactly. Shoulder strips now hang
  correctly (docs/img/havok_testrig_v2_fixed.jpg). Also confirms: added body-named bones ARE animated.
- In-game test (user, mission): skirt + shoulder strips work; respawn works. Hoverpack/jetpack draws
  scorch/tear "hazard" lines = the cape shader's burn mechanic (we use the cape shader). Clipping:
  kneeling (leg through skirt), full sprint (knee pokes through briefly). Live-tuned with
  tools/havok/re/livetune.py: leg capsules +3 cm (feet +2), particle radius 2 -> 3 cm.
- CRASH (2026-10-18 22:19): changing simulate-op subSteps/iterations LIVE crashed the game (Havok sizes
  per-instance work memory at creation). livetune.py now refuses it; baked instead (rig: substeps 3,
  iterations 2, skirt leash 0.15). Leash/maximumDistance edits are safe live.
- BLOW-UP (2026-10-18): with substeps 3 / iterations 2 the skirt bunched, spazzed and went NaN in xyz
  (all 564 particles): with substeps > 1 the overflowing w lane leaks into positions. With 1 substep
  (as the cape) w-NaN stayed harmless. Rig now uses the cape's solver settings exactly (1 substep,
  1 iteration, 3 link passes), skirt leash 0.30, legs +2 cm, flare 0.25 (was 0.45: looked "blown by a fan").
- Emote study (thumbs-up): recorded with tools/llm/hd2dress_poserec.lua (docs/emote_thumbsup_bones.txt,
  plot docs/img/emote_thumbsup_bones.png via tools/emote_plot.py): hips drop 0.97 -> 0.43 m in ~0.2 s,
  rotate ~100 deg, right thigh swings fully back (kneeling leg). Skirt gets driven through the thighs and
  stays inside (capsules push to the nearest side). Fix in generator: thigh_follow (lower skirt's
  sim-skin/leash target blends hips -> thigh on its side, up to 0.6 at the hem), leash 0.20, and
  transfer motion from 0.5 m/s (cape: 8 m/s) so the skirt rides along with fast hip moves.
- Crotch bunching: thigh_follow averaged both thighs at the centre front/back, so with split legs the leash
  target sat between the legs. Now only the sides follow their own thigh (centre = hips). Live tests:
  friction 0 + stretch x1.5 + link stiffness x0.3 nearly exploded (soft links are unstable; reverted).
- Capes' looks = their MaterialLut (Foe Smasher archive holds only a 23x5 R16G16B16A16 texture).
  make_cloth_material.py CLOTHMAT_FROM_CAPE=ARCHIVE:TEX copies a cape's MaterialLut into our cloth material.
  Installed: Foe Smasher (black) as patch_13.
- User: the crotch bunching only ever appeared after LIVE constraint edits, never in normal play. So live
  edits of leash/stretch/link stiffness jolt the sim (they also preceded the earlier blow-up). The
  sides-only thigh-follow change is kept but was likely not needed.
- Look: per-face default UVs mapped the whole texture onto every face ("diamond plate"); now one UV
  (0.5,0.5) for all cloth vertices (vertex count 8906 -> 3650, no UV splits). Remaining squares = the cape
  shader's camo tiler (3D-positioned), not the LUTs. Material: Foe Smasher MaterialLut, rows flattened.
- "Easy to pull, hard to clip": skirt stretch limit 60%, leash 0.40, link stiffness 0.7 (0.3 was
  unstable), knees +5 cm, front_follow (front panels follow the thigh on their side, no averaging).
- User: easy-to-pull skirt held over the knee for a moment before giving. Removed the capsule growth and particle radius back to 2 cm (fabric lies flat on the body; growth read as tubes).
- w-lane resolved as a non-issue: stock capes rebuilt with 3 substeps ran 2+ minutes with xyz finite
  (w NaN as usual). The earlier "substeps blow-up" was the LIVE leash edit made right after. Rig now uses
  3 substeps / 2 iterations (baked). Rule: never live-edit constraint data; bake.
- Rig bumped to 5 substeps / 2 iterations (3 was much better: knee holds briefly, then slides off). 972 particles, same size as the largest stock cape.
- 5 substeps: bow clean, knee tip only pokes out, no slide; thumbs-up eventually falls through (much later). Added kneecap capsules (collision_extra: short capsule on the knee joint, +3 cm) instead of growing the whole shin. Fixed havok_model: a Struct linked to a pointer keeps its own subclass type.
- Kneecaps made it worse (pushed further = stretched more). Real cause: links 6-8 cm vs particle radius 2 cm, soft neighbour links (0.7) spread points and the knee slips through the gaps. Now: kneecaps off, neighbour stiffness 1.0, keep stretch limit 60%; next live-test particle radius / friction (safe live).
- Firm neighbours = as good as best: knee tip barely pokes, stays. Particle radius 2 vs 3 cm: same break-through speed, 3 floats off legs; keep 2. Trying 10 substeps (backup old_patches_firm5).
- 10 substeps: -20 fps, same fall-through speed: not a speed problem. Back to 5. Test: leash 1.0 + stretch limit 100% (both loosened).
- SUCCESS: leash 1.0 + stretch 100% keeps the skirt over the knee in thumbs-up (constraints were dragging it back through). Next: which of the two matters; live test particle radius 1 cm for flatter lay.
- Particle radius: author-tunable (1 cm looked fine live; baked stays 2 cm). Bisect test: leash 1.0, stretch back to 60% (backup of the working loose build: old_patches_loose).
- Bisect result: LEASH is the culprit (leash 1.0 + stretch 60% holds). The leash pulls each point toward its skinned spot, which sits inside the bent leg in a kneel. Now testing leash 0.70 (backup: old_patches_leash100).
- New tools/havok/re/clothreset.py (reset running cloth to rest, zero velocity) and livetune --reset, so live constraint edits can start smoothly. Untested on a leash edit yet.
- FOUND the live-edit bunching: livetune --leash took the FIRST constraint set (StandardLink) as the leash and overwrote link rest lengths/stiffness. Fixed (select by name). restorelinks.py repairs a damaged running cloth from the .bin. Leash 0.70 holds the knee; testing 0.55 live with --reset.
- clothreset --flare (default 1.4): reset starts the cloth spread outward per 10 cm height slice and lets it fall onto the body (plain reset left points inside a bent right leg).
- Leash bisect: 0.40/0.45 clip, 0.55 holds = baked and installed. New docs/ENGINE_CLOTH_VALUES.md: every tested value and result (safe bounds for modders, not limits).
- One-command build: tools/hd2dress_cloth.py (runs in Blender: build SETTINGS.toml [--install]; archives UNITID). TOML settings with tested defaults (gen_engine_cloth.DEFAULTS, spec_from_settings refuses unknown keys), cloth chosen by vertex group in the author's .blend (per-unit object) / material slot / positions file, template read from the game, archives found by TOC scan (cached per game build), one patch_0 per archive in dist/<cloth_name>/. examples/engine_cloth_testrig.toml reproduces the shipped rig (float last-bit only); vertex-group route byte-identical. Size problem: 23 archives x 2 cloths x 10 MB = 464 MB.
- Loadout/armory preview SPIKES: the rig's LOD1-3 (HD2SDK AutoLods copies of LOD0) carried the cloth material but no
  cloth drives them; far/preview views draw an LOD and get garbage. LOD meshes themselves are exact copies of LOD0
  (checked). The cape drives its LOD1 via a scratch buffer named after that mesh (g_medium_cape_simple = its LOD1 id).
  HD2SDK names LODs <mesh>_LOD1.. (h32 matches). Test: rig rebuilt with TESTRIG_AUTOLODS=0 (LOD1-3 = original B-01
  hips) installed as patch_12. Also: compact writer layout + Model.prune: cloth 10.1 -> 7.4 MB (content identical).
- OOM: my Blender jobs loading the whole cape archive + agent Blender + game > 32 GB. One Blender at a time, load by id.
- ENGINE BUG: cloth with substeps > 1 renders garbage spikes on CLONED divers (hellpod / armory / loadout preview).
  Proven with the STOCK capes rebuilt at 3 substeps (they spike too); our dress at 1 substep is calm. Sim positions
  stay fine; only the render object of the clone gets mixed data (values from the real diver 28 m away). Arrowhead
  ships capes at 1 substep. Substeps are therefore unusable; testing iterations 4 at 1 substep for the knee.
  (Also: the "scratch" buffer is per-thread shared memory, so clothreset/rest readings from it are unreliable
  with more than one cloth of the same kind.)
- docs/CLOTH_MATERIAL_RESEARCH.md (agent): cape shader slots; author textures = zone mask + palette (+ own normal
  map) or decal atlas; camo tiler is the likely square source; 6 untested material test patches in
  ~/.cache/hd2-dress/clothmat_research/build/.
- 1 substep + 4 iterations holds the knee (hem rides a bit higher, same as 5-substep footage). User tuned friction 0.8, gravity 14 (livetune --gravity, this cloth only; 'heavier' = stronger gravity, uniform mass changes nothing). New: part 'inward' = LocalRange normal limit (applyNormalComponent, minNormalDistance) with reference normals oriented away from the body axis; test 0.03 against cloth sticking inside a leg. Defaults now substeps 1 / iterations 4 / friction 0.8.
- Stock cloth values extracted (cape/cape2/flag): substeps 1 iterations 1, mass 0.003, radius ~4 cm, friction 0.6-0.75, leash median 1.7 cm (cape) / 24 cm (flag), bend k ~0.8 (cape) / 0.44 (flag). The cape also has hclBonePlanesConstraintSet (457 planes on its bone; allowed side = n.p+d >= 0, verified) and hclVolumeConstraintMx, which the generator had dropped. New: [planes] = one bone plane per loose point near a leg, tangent to the nearest thigh/shin capsule, executed first (cape order). Test rig: 423 planes, all valid at rest. Live-tuned values baked: leash 1.0, friction 0.3, radius 0.025, bend 0.24, gravity 14, inward off.
- Bone planes in game: raised knee still pokes a hole (kneepad bigger than the capsules). Added kneecap capsules again (collision_extra l/r_knee -0.05..0.05 +0.03), now with firm links + planes. Also found landscapeRadius 0.07 (cloth keeps 7 cm off the floor); livetune --landscape-radius.
- Kneecaps + bone planes: raised knee no longer pokes a hole. [sim] landscape_radius setting (test rig 0.015). docs/ENGINE_CLOTH_VALUES.md rewritten with all findings (stock values table, substep bug, iterations, leash/friction/bend/gravity, planes, inward, floor gap, LODs).
- Camo squares are NOT a texture: flat camo, flat LUTs, all tilers blank, a loud stripe camo slot: same squares; cape swap no effect; live render data clean (no NaN). Theory: HD2 meshes store no tangents (export zeros), the shader builds its tangent frame from UV derivatives, and single-dot UVs make it degenerate. Rig builder now unwraps cloth as a cylinder (TESTRIG_UV=cylinder default; u around the body, front 0.5, seam at the back; v = height). testrig_uv installed (3706 display verts) for the test.
- Squares investigation: NOT camo/decals/bump/ID-mask alpha/material copy (stock cape material directly: same squares). Memory check: the unit's dress mesh slot uses our material and the patched LUT is loaded. New theory: the rig built every cloth face TWICE (front + back layer at the same positions) and the cape shader is two-sided: coincident layers z-fight = blocky light/dark squares that turn to static when moving. Rig builder now single-layer (TESTRIG_DOUBLE=0 default). Also: HD2 LUT Modding Guide (community Google doc) gives every primary/cape LUT column (col 22 alpha = camo type, -1 off; cape LUT cols 5-16 = 4 icon layers).
- SOLVED: single-layer rig = solid cloth, no squares (user confirmed). Build refuses double-layered cloth. Material tests before this must be re-run.
- Ridges test: BaseData edits SHOW (corrugated tube): our material is drawn; only the colour inputs (MaterialLut/IdMask) are replaced at runtime. Dress colours match the stock cape LUT (11899498302424885466). Test: that stock LUT texture recoloured red in 18235e0c9ec0e636.patch_0.
- Colour still dark chrome with: zones mask, red default 1x1 mask (11263944652919294967, was white), stock LUT red, a full real cape design (11a35cf5481b8b04) on our material. Rig had UV2 = 0 (host mesh had 2 UV layers); cape uses UV0=UV1=UV2. Builder now adds a 3rd UV layer; testing the real design with UV2.
- Shader re-test with the clean pipeline: B-01 armour material on the cloth mesh = INVISIBLE. Cape shader required (confirmed). PaletteSlot (material scalar, default 0) changes the dress look (0 light silver, 1 dark chrome): colours come from a runtime palette indexed by PaletteSlot, not the material's LUT/mask. Testing slot 5.
- Cape shader resource list found in memory (shader reflection strings): __tex_cape_gradient, __tex_cape_lut, __tex_cape_scalar_fields, __tex_cape_tear, blood/weathering/bug tilers, __tex_decal_sheet, __tex_customization_camo_tiler_array, __tex_composite_array, __tex_base_data, __tex_material_lut, __tex_customization_material_detail_tiler_array, brdf luts. NO id_masks_array: the cape shader never reads IdMasksArray. The flag's 'RGBA mask' id sits in CapeScalarFields: the zone/shape mask is likely read via cape_scalar_fields. Test design2 puts the real design mask there.
- SOLVED cloth colours: CapeScalarFields = RGBA zone+shape mask (the cape shader never reads IdMasksArray), CapeLut column 1 = colour per zone (rows black/R/G/B/inside) with columns 2-3 strength. Verified: red/green/blue bands on the dress. Back faces use the inside row: the rig's skirt faces point inward (fix: flip winding). Recipe in docs/CLOTH_MATERIAL_RESEARCH.md.
- Faces turned outward: skirt shows red/green/blue thirds on the outside, black band (base fabric) at the waist. Colour pipeline fully verified.
- Colour wheel test (smooth RGB weights in the mask): HARD zone lines, no blending: 4 flat zone colours + inside per cloth. Testing the full-colour route: a decal layer covering the whole cloth (CapeLut layer 1 box 0.5/0.5/0.5/0.5, atlas 0/0/0/1, strength 1/1) with a 512x512 spectrum DecalSheet.
- FULL COLOUR WORKS: a decal layer shows a smooth spectrum from our DecalSheet (decalfull: box (0.5,0.5,0.5,0.5) covered u 0.25..0.75 at the front; atlas magnify 1 showed about half the sheet). Next: box size 1, magnify 2.
- FULL-COLOUR TEXTURE WORKS: decal layer 1 box (0.5,0.5,1,1), sheet window (0,0,0,1), strength (1,1,0,0) maps the whole DecalSheet over the cloth UVs (grid test: all 16 cells in order). Authors: UV-unwrap + paint a texture -> DecalSheet. Documented in CLOTH_MATERIAL_RESEARCH.md.
- Tartan test (user texture fabrics_0083 tiled 8x4 as DecalSheet, normal+AO as BaseData): works. Black mask zone = metallic foil -> use the red zone. Inside (back faces, no decals) = flat colour in CapeLut row 4: dark red made self-clipping folds look much better (user). Shine = stock roughness 0.9: tartan3 sets primary LUT col 11 R = 8, col 10 off. TODO: thick cloth = display vertices that ride on the nearest sim triangle with a normal offset (solidify inner layer + hem), also lets a detailed display mesh sit on a coarser sim mesh.
- Tartan shine = specular gloss (moves with the light). Roughness col 11 R = 8 alone did not change it; tartan6 sets every matte control from the guide.
- OBSERVATION (user): with the dress rig, the 'front rest leaning position' emote drops the camera to the floor (only that emote). Possible clue: the rig adds copies of body bones (head, neck, chest, spine, knees, feet, arms) to the hip unit; if the game looks up camera targets by node name it may pick our copy. To check: same emote without the dress armour.
- Shine ("wrapping paper" glints along folds, move with the light): NOT fixed. Ruled out: primary LUT roughness/gloss/
  matte controls, BaseData (flat, alpha 0/128), tear/weathering/gore/composite textures, bump tile strength (col 2 G = 0),
  decals in general (stock capes with decals are matte; user compared side by side). Unnamed material vars decoded
  (decal_size_x/y, decal_id(_offset_x/y), decal_lut_id/size_x/y, decal_channel_selection, use_decal_rgb_channels): no
  finish control. Next suspects: coarse sim mesh (648 points over a floor skirt; cape 984 over a small cape) giving
  crinkled facets; a no-decal comparison; normals from MeshDeform.
- Session end 2026-10-18. Installed now: patch_12 = skirt-only rig (testrig_skirt), cloth = dist/hd2dress_testrig_skirt,
  patch_13 = tartan8 test material. Original cloth material backup: clothmat_research/patch13_backup.
- LEAD (user, 2026-10-18, not tested yet): the Illuminate cultist loin cloth material, "an advanced cloth-like material",
  in the "Overseers" Illuminate archive, material ID 10299839715840092488. Check: its shader/parent (cloth-capable? the
  2026-10-17 scan found only 3 cape-shader materials), its texture slots and LUT setup (may be matte fabric without the
  dress's glints), and whether the loin cloth is engine (Havok) cloth or a bone-driven mesh.
- LEAD (user): there are probably OTHER cloth shaders in the game, and the Illuminate use them (e.g. the cultist loin
  cloth above). This contradicts the 2026-10-17 research scan ("only 3 cape-shader materials, only 3 cloth resources of
  type d7014a50477953e0"): re-check that scan (did it cover every archive incl. Illuminate content? other parent shaders
  that draw cloth? other cloth resource types?). Could give a second cloth-capable shader with different looks/limits.
- Cultist loin cloth material 10299839715840092488 (archive 9230ae99f0ee6c03): parent 17265463703140804126 (Illuminate
  character shader, itself in 18235e0c9ec0e636). Slots: AlbedoEmissive (real colour map), WoundNormal, DetailNormal
  Leather/Porcelain, SclarFieldOpacity, WeatheringSpecial, Wound data, BloodTiler, IlluminateData. Vars include
  subsurface, clearcoat, emissive, glitch, wound painting and IgnoreSkinning0/1/2. Its units (7ea558204d0ffc29,
  9c7ef47a463d5327, da40bb347c7447f2, f1610ac48cdc5240) have NO cloth files (only bones/physics/state machine types):
  the loin cloth is physics-bone driven, not Havok cloth. Test: material copied as 7200101010101010101 on the skirt rig.
- USER NOTE: the dress was never shiny before the full-coverage decal worked, so the glints are tied to our decal use (stock capes' small decals look matte). Next: decal with a FLAT single-colour sheet (content vs decal mode), BC3 vs RGBA8 sheet, column 7 B/A like stock (gradient values).
- SHADERS FOUND: engine shaders (886 shader_library) live in archive ee6b1ba7e22d71ed; MATERIAL shader code lives in the
  PARENT material's GPU data (DXBC blobs). tools/dxbc_info.py lists shader types/inputs/resources.
  Vertex shader inputs: cape (15780315333863701079) = POSITION NORMAL(xyz) TEXCOORD0-2 [TANGENT BINORMAL] [POSITION1]
  SV_VertexID, NO skinning inputs. Armour (11388000050917332691) and Illuminate (17265463703140804126) = POSITION
  NORMAL(xyzw) TEXCOORD0 TEXCOORD1 **TEXCOORD15** [BLENDINDICES/WEIGHTS ...] SV_VertexID SV_InstanceID; both have a
  no-skinning variant. Our cloth render copy has no TEXCOORD15 -> likely why armour/Illuminate materials draw nothing.
  Generator option cloth.texcoord15 adds the element (half2 zero, stride 64; Havok display buffer stride 64 too).
  Test: loin material (IgnoreSkinning=1) + tc15 cloth.
- RESULT: with cloth.texcoord15 the Illuminate/loin material (parent 17265463703140804126) DRAWS the engine cloth (its own
  AlbedoEmissive texture shows) but it "lags behind / acts weird": the character shader skins the already-moved cloth
  vertices again (blend weights in the render copy; IgnoreSkinning vars did not pick the no-skin variant).
  Dropping the blend elements (no_skin_elements) = INVISIBLE: the engine still selects a skinned variant (needs the
  blend inputs). To make character shaders usable: the cloth's display output must be in the space the skinning
  expects (e.g. local to the skinned bone so skinning restores world space), or the skinning must be an identity.
- Measured live: the render copy holds positions in the unit's OBJECT space (relative to root; root world (0,2.51,20.01), render verts ~(0.03,0.07,0.67)). Character shaders skin them again with the vertex's bones (hips) = double move. Fix: render_root_skin (every render-copy vertex 100% root) + rig puts root in the palette (one 0.001 root weight, TESTRIG_ROOT=1).
- SUCCESS: character shader (Illuminate loin material) draws the engine cloth AND follows the physics with texcoord15 + render_root_skin + root in the palette. Dark blotches = the loin cloth's own textures on our UVs (testing tartan in AlbedoEmissive).
- Dark view-dependent patches with the character shader: armour/Illuminate NORMAL is HD2's packed octahedral normal (HD2SDK 'unk_normal', 2x10 bits); our render copy gave plain xyz1. Test: oct_normals (rest normals pre-packed, cloth writes positions only).
- oct_normals CONFIRMED: packed rest normals remove the dark view-dependent patches (character shader). Limit: frozen
  normals (lighting does not follow folds; shows in heavy bunching like the push-up emote).
- Havok output converter in HD2 (hclOutputConvertOperator vtable rva 0x14eaa50, conversion fn 0xf64970) supports ONLY:
  0 float4, 1 float3, 2 byte4 (-1..1 -> 0..255), 3 short3, 4 half3, 5 sbyte4; anything else skipped. No octahedral or
  custom hook, so moving normals for character shaders are not possible through Havok output.
- Character-shader route summary: material on a character shader (armour/Illuminate parent), cloth options texcoord15 +
  render_root_skin (+ root in the mesh palette) + oct_normals. Plain colour map works, matte, no glints.
- BUILD TOOL character route WORKS and looks 'perfect' (user): tartan colour map + tartan normal map in 'Nar' (RG normal, B AO 255, A roughness 0.7). Likely why it improved so much: before, 'Nar' was the template's 1x1 WHITE placeholder = normal xy (1,1) (a strongly tilted fake normal) and roughness 1 everywhere, which darkened/flattened the lighting. 'Nar' confirmed as the normal/AO/roughness slot.
- CORRECTION: no fabric weave is visible (user). The tartan normal map was shrunk to 256x512 per tile (8x4 repeats), so the threads average out to flat. The improvement came from replacing the 1x1 WHITE 'Nar' placeholder (tilted fake normal, roughness 1) with a near-flat normal + roughness 0.7. Weave plan: the Illuminate shader's detail normal slots (DetailNormalLeather / DetailNormalPorcelain) with tiling + intensity vars (DetailNormTilerLeather, DetailNormIntensityLeather, ...): expose as look.weave / weave_tiling / weave_strength.
- tools/hd2dress_prep.py (Blender, on the author's .blend, saves a COPY): adds missing cloth collision bones with the diver skeleton's exact rest pose (verified identical to the rig's, diff 0), 3 UV sets, root in the palette (0.001 root weight), checks double layer / inward faces / single-dot UVs / LODs using the cloth material.
- Size: BC1/BC3 material textures via texconv.bin (44.7 -> 8.4 MB); cloth.strip_scene empties the template hkxScene (cloth 7.1 MB -> 0.68 MB); whole test-rig build 334 MB -> 40 MB. Both untested in game (install_lite.sh ready).
- tools/hd2dress_preview.py: Blender/Cycles preview of a [look] (colour, normal, roughness, weave) on the mesh UVs; images in docs/img/preview (tartan_front/side, weave_dimples_front = what the in-game weave test should look like).
- WEAVE WORKS: bold dimple detail normal in DetailNormalLeather/Porcelain (tiling 4, strength 1) shows in game. Now the real fabric normal as weave (weave_aspect 2 to match the 2:1 UV span).
- Weave dark splotches: HD2 detail normals are packed RG normal / B AO / A 105 (the game's own default detail texture is 4x4 (126,126,255,105)); a plain normal map's B reads as AO. Fixed in the build tool (B 255, A 105).
- Weave verdict: detail normals work but clash with the frozen (rest-pose) base normals: folded cloth gets dark patches (strength 1: very dark overall + black folds; 0.3: same, subtler). Keep look.weave OPTIONAL, off by default, documented as 'subtle only, can darken folded cloth'.
- LITE build verified in game: strip_scene + BC1/BC3 textures work (dress looks the same). strip_scene is now the DEFAULT. Test-rig mod: 40 MB (was 334 MB).
- Which archive does the game read? Linux atime after a fresh install: of the 23 cloth patch_0, ONLY 562a45e9bc984eb9 (B-01 Tactical Variation 2 = the equipped armour) was read. The game loads cloth from the EQUIPPED armour item's archive. The 23 archives = 23 armour items sharing the hip unit; since the mesh patch changes all of them, ship cloth for all (or limit with archives = [...] and accept broken skirts on the others). Lite size: 23 x 2 x 0.68 MB ~ 31 MB.
- Other body type: dress works (user, 2026-10-18). Remaining before release: multiplayer check, Windows build/prep run.
- HANDOFF (2026-10-18 late): Windows tool test IN PROGRESS, not finished.
  * VM win10 (session libvirt) running, defined from ~/.cache/hd2-dress/vm/win10.smb.xml (original backed up as
    win10.orig.xml: restore with `virsh -c qemu:///session define ~/.cache/hd2-dress/vm/win10.orig.xml`). Extra NIC: e1000e
    on pcie.0 addr 0x9, user net 10.0.3.0/24, guestfwd 10.0.3.4:445 -> 127.0.0.1:4450.
  * User-level Samba on 127.0.0.1:4450 (config ~/.cache/hd2-dress/vm/smb/smb.conf; shares hd2data (game data, ro), repo
    (ro), vmshare (rw); local test credentials). Stop it: pkill -f 'smbd.*vm/smb/smb.conf'.
    QEMU's own smb= fails (SELinux: svirt cannot read data_home_t); guest logons need admin in Windows.
  * VM driven with ~/.cache/hd2-dress/vm/vm.py (shot, type, key, click, ps = open PowerShell, run, wait).
  * Last step sent: `net use G:/R:/V:` with the test credentials; not yet confirmed. Next: install Blender + HD2SDK in the VM
    (zips in vmshare), set HD2_DATA=G:\, run hd2dress_prep.py / hd2dress_cloth.py build, compare with the Linux build.
  * Multiplayer plan: /mnt/savior/hd2-lab sandbox-b (same buildid 25480438) as second client; not started.

## 2026-10-18 (part 2 chat)
- VM win10 shut down cleanly to free RAM (still defined from win10.smb.xml). Blender is already installed in the VM.
- `net use` failure (System error 64) cause: QEMU guestfwd with a tcp: target is a single chardev connection, SMB needs
  several; smbd itself works (smbclient from the host lists vmshare). Fix options: guestfwd ...-cmd:nc per connection
  (may be blocked by svirt), or copy the needed archives into the VM.
- User order: live Linux GUI test BEFORE Windows. Gap found: the Blender add-on panel is the LUA route only; the engine
  cloth route (prep/build/preview) has no GUI, only TOML + command line. Proposed: an engine-cloth panel (prep checks,
  cloth pieces list with pin groups + per-piece sliders, sim/look sliders, build/install writing the TOML). Pending user
  answer. Note: generator pins the TOP row of each piece; strands/tails need a pin vertex group.
- USER DECISION (2026-10-18): Lua is no longer used. The Blender add-on is engine cloth ONLY (v0.3.0). Removed from the
  add-on: Lua preview/physics (lupa), hand bone tools, auto-rig, Lua registration export (physics/preview/rigging/
  export/helpers.py; in git history). mod/ and sim/ (the Lua runtime and simulator) are still in the repo, untouched.
- Add-on v0.3.0 panel: 1 Cloth pieces (vertex groups cloth_<name>, list, per-piece sliders leash/stretch/bend/stiffness/
  mass + Follow legs, New piece from selection, Add/Remove/Select, Delete; Pins = vertex group "pin", a piece without
  pins hangs from its top row), 2 Check & fix (hd2dress_prep.py functions on the open scene, undo-able; the diver
  skeleton is read once in a background Blender and cached in ~/.cache/hd2-dress/diver_rest.json), 3 Physics,
  4 Look (+ Preview look render), 5 Build / Build + install (background Blender, streams output, Cancel), Save/Load
  settings (TOML beside the .blend = same file the CLI builds). The zip bundles the engine tools (hd2_dress/tools/).
- Generator: [[piece]] (group + own settings + follow_legs), cloth.pin_group, mesh_name looked up from HD2SDK's
  bonehash.txt, each unit reads only its own object (Z_ObjectID). Test rig output byte-identical to before.
- tools/test_addon.py rewritten for the engine panel: 19/19 (pieces, pins, check/fix, every slider saved + loaded, build
  with pieces and pins, preview, cancel, panel draw). Panel defaults = the in-game tuned values (leash 1.0, friction 0.3,
  radius 0.025, bend 0.24, gravity 14); gen_engine_cloth.DEFAULTS still holds older values (leash 0.55, friction 0.8,
  radius 0.02, bend 0.8, gravity 9.81, floor gap 0.07) for CLI files that omit keys: to reconcile.
- Docs not updated yet: docs/GUIDE.md / BLENDER_ADDON.md describe the old Lua panel.
- Live smoke test of add-on 0.3.0 (2026-10-18, Claude acting as an author): Blender inside Xephyr (:5, a nested X window
  on the desktop; Wayland/KWin blocks xdotool input into normal windows) driven by real xdotool clicks/keys + instant
  screenshots; a command channel (~/.cache/hd2-dress/panel/cmdchan.py + q.sh) only to read state. Steps: find pieces,
  select the slim mesh, Edit Mode, L-select the B-01 hip pouch, New piece "pouch", box-select + Pin, Check, Fix all,
  type/drag sliders, colour map via file browser, Preview look, cloth name + armour patch via file browser, Build (in
  Edit Mode), Save/Load settings, Advanced, weave, eyedropper, Delete piece + Ctrl+Z, Open output folder. Build +
  install NOT clicked (would replace the installed test skirt).
- Fixed from it (0.3.1): Check crashed in Edit Mode (UVs unreadable in Edit Mode; Check/Fix now run in Object Mode and
  return); pieces found automatically on load; counts named by body (Slim 648, Stocky 648); all text wraps / labels
  above fields; piece names without cloth_; labelled weave sliders; soft slider ranges (a 60 px drag sent gravity
  14 -> 40); progress shown under Build / Preview; Save settings warns when the .blend is unsaved (the TOML reads pieces
  from the saved .blend) and always records the output folder; Delete names the piece; status/job/last build moved to
  the window manager (Ctrl+Z rolled them back); preview window opened from a timer needed a window override.
- New checks: cloth faces on more than one material (others invisible in game), armour faces sharing the cloth material
  (they get the cloth look: TRUE for the test rig, 3006 B-01 faces use 7200101010101010101), piece missing on a body
  type, closed shapes (no open edge). Body names (Slim/Stocky) in messages.
- Still open: file browsers start in ~ (not the .blend folder); Preview look puts the cloth look on the whole object;
  closed-shape check is lenient (a pouch open where it meets the belt passes); docs/GUIDE.md still describes the Lua
  panel; Build + install untested from the panel.
- 0.4.x (2026-10-18 late): Copy pieces to the other body (nearest vertex <= 3 cm, small unconnected clumps dropped) +
  Check warns when a body type has no cloth; own browse buttons (start next to the .blend, filtered); status box fixed at
  3 lines (buttons jumped when it changed length); job copy of the scene saved from Object Mode (saved from Edit Mode
  after Fix all it had EMPTY UV data: preview rendered flat white); preview images named per view and re-pointed at the
  new render (old code reloaded the previous cloth name's file).
- RELEASE FIX: the build wrote the material as 9ba626afa44a3aa3.patch_0 = the same name as the author's armour patch.
  Now the character-look build copies the author's armour patch and adds the material to it (one base patch: armour +
  material; verified: 2 units + 1 material + 1 texture). Debug files (manifest, settings copy, cloth_*.bin) go to
  _debug/, so the output folder is exactly what to ship. NOT yet tested in game (merged base patch).
- docs/GUIDE.md rewritten for the engine panel with 12 screenshots from a real author run in Xephyr (docs/img/guide/);
  GUIDE.html via tools/build_guide_html.py; README/BLENDER_ADDON/ENGINE_CLOTH_GUIDE updated. Old Lua guide images
  (docs/img/guide_0*.png) are unused now.
- HANDOFF (2026-10-18 ~23:50): VM shut down (now defined from ~/.cache/hd2-dress/vm/win10.smb2.xml: guestfwd uses
  -cmd:/usr/bin/socat STDIO TCP:127.0.0.1:4450, one relay per connection; untested in Windows yet). Next: in Windows
  `net use G: \\HOST\hd2data` (test share) (+ repo R:, vmshare V:), install the add-on zip in the VM's Blender
  (already installed), run the panel build there. Before posting: in-game test of a panel build (merged base patch),
  Windows run, 1Password secrets review (fleet rule), licence (user).
- 2026-10-20: game update to build 25988413. It wiped every installed mod (no patch files left). Our dependencies did
  not change: cape template cloth byte-identical (md5 1fb9bc0d...), B-01 hip units same stamp at +0x2C (36cda400), same
  23 archives, loin material present.
- PANEL-BUILT MOD WORKS IN GAME (user: "looks same as always"): ~/HD2Dress-ingame/skirt.blend, panel Refresh/Check/
  Fix all/Build + install (first real use of Build + install): 23 cloth patch_0 + the MERGED base patch_0 (armour +
  material, first in-game test of the merge) installed into the clean data folder.
- Windows (2026-10-20): VM shares work after `seccomp_sandbox = 0` in ~/.config/libvirt/qemu.conf (libvirt's QEMU
  sandbox blocked the guestfwd -cmd relay: "Slirp: fork_exec: Operation not permitted"). Add-on 0.4.1 installs on
  Windows Blender 5.2.2 with its bundled tools. First Windows panel test: 17/20, the BUILD failed: HD2SDK's "Import
  materials" (default on) made export_unit import the unit's materials and convert textures, which failed on Windows
  ("Failed to convert texture ... to PNG") and aborted the build. Fixed: ImportMaterials off while reading the unit
  (Linux output unchanged: 23 cloth patches byte-identical, base patch differs only in the random texture id). The
  Windows build over the SMB share is slow (~1-2 min per archive).
- SHIP BREEZE = real wind, per world, for every cloth (not a canned cape effect): rva 0x7d3830 (wind parameters) and
  0x7d3910 (wind vector) walk every cloth object in a world's cloth pool and write each one's wind object; no engine
  callers (script side). Havok: hclSimpleWindAction; mass warnings "Forces (like wind) may cause large accelerations /
  may have almost no effect" => MASS sets the wind response (gravity is mass-independent, which is why mass looked
  inert before). Our skirt ~2.6 kg total (648 x 0.004) vs the cape ~3 kg (984 x 0.003): expected to flutter similarly.
  To confirm in game on the ship (cape + skirt by the fan); if too strong/weak, tune per-piece Mass.
- WINDOWS PANEL TEST PASSES 20/20 (2026-10-20, Windows 10 VM, Blender 5.2.2, add-on zip 0.4.1 installed with Blender's
  own installer, game data over SMB). Cloth patches built on Windows are byte-identical to the Linux build. Two Windows
  problems found and fixed on the way: (1) HD2SDK material import during unit reading (texture conversion abort);
  (2) MemoryError on 8 GB: HD2SDK's LoadArchive loads every state machine and CreatePatchFromActive deep-copies the
  whole archive; the build now reads only the template entries and each archive's TOC header (peak 12.2 -> 3.3 GB,
  45 -> 22 s, output identical). Texture compression fails in the clean VM: texconv.exe exit 0xC0000135 = DLL not
  found (no Visual C++ Redistributable; gaming PCs have it): textures stay uncompressed (54 MB instead of 35 MB, still
  works); the build log, a panel popup and the guide now say what to install. Add-on 0.4.2. VM shut down;
  ~/.config/libvirt/qemu.conf has seccomp_sandbox = 0 for the SMB relay (remove to undo).
- WIND, read live (2026-10-20): every cloth instance gets a 0x90 aero object (fn 0x7d51d0: air density 1.225 at +0x50,
  100, 100, 2, 10); the wind VECTOR sits at +0x30 (written by rva 0x7d3910, no engine callers = game script). On the
  ship only the worn cape's aero had wind (-19.4, 2.4, 26.0 ~ 32 m/s); our skirt, the cape's LOD/preview copies: zero.
  Jungle planet: cape flat (user). So the breeze is a scripted ship effect aimed at the cape only (maybe also weather
  like blizzards: unknown). Our cloth has the same aero machinery; it is never targeted. Data-only cannot change the
  target; a loader addon could. Known limit: "no ship fan on the skirt". Write test (copy the vector) not done.
- WIND ANSWER (2026-10-20): the ship breeze on capes is NOT cloth wind. Every cloth (skirt included) has the engine's
  aero action attached (instance +0x68 list, rva 0xf0cd00), all in field mode (grid 1024 at +0x20/+0x28, strength +0x1c
  = 64); writes to the skirt's aero (field strength x15, simple-mode 40 m/s vector) changed NOTHING. The cape cloth is
  skinned to chest, cape1..cape8, neck with a leash median 1.7 cm (max 10 cm): it rides on the cape BONES, which the
  game simulates (jiggle/ragdoll entries in the avatar state machine) and which feel the ship breeze (flat on planets).
  Data-only route for authors: add cape1..8 to the armour (prep tool) and let a piece's sim-skin target blend toward
  the nearest cape bone ("wind follow" per piece, stronger toward the hem), with a tighter leash on those parts
  (tradeoff vs knee clipping). Untested: whether cape bones move with no cape equipped.
- WIND via copied cape bones FAILED (2026-10-20): cape1..8 added to the hip armour unit only follow the animation
  (strips curled with body motion "like tendons" and hung static in the ship breeze while the cape flapped). The flap
  is simulated on the cape unit's own bones and does not reach same-named bones in other units. Generator option
  piece 'wind' (+ wind_leash, wind_back_only) stays in the code but is NOT exposed in the panel. Test builds:
  ~/HD2Dress-wind (back-half skirt), ~/HD2Dress-streamers (12 strips, installed at the moment).
  Remaining routes: own jiggle bones on the armour (state machine ragdoll entries, like the ponytail mod; does the
  breeze reach jiggle bones?) or a loader addon. Suggested: ship v1 to Discord pros without wind.
- 2026-10-21: game CRASHED (SEGV in the engine, rva ~0x122520, no GPU error) a few minutes after a live test that wrote
  aero field strength 6400 (100x) into our cloth (restored afterwards). Rule: no extreme live writes; test via builds.
- Measured (live particle meter /tmp/clothmeter2.py, read-only): ship flutter cape 1.3-3.9 cm (gusty), our 12 streamers
  0.8-2.1 cm; planet cape 0.2-0.3, streamers 0.1. Our cloth gets the ship breeze proportionally (~11x like the cape).
  Aero field 0 vs 100x on our cloth: no clear change in the streamers/cape ratio => aero objects are not the breeze.
  A background agent researches the mechanism (notes: docs/research/BREEZE_AGENT.md).
- Flow variants (each on its own B-01 variation archive, switch in the armory without restart): V1 58e4 base (cape
  settings), V2 562a bend 0.1 + stretch 1.5, V3 6cd3 gravity 5 + mass 0.001, V4 519c damping 0.2 + stretch/leash 10.
  Installed, untested.
- WIND PINNED (2026-10-21, user: "pin this for later"). Flow variants measured (streamers/cape flutter ratio, ship):
  V1 base 0.26, V2 soft (bend 0.1, stretch 1.5) 0.33, V3 light (gravity 5, mass 0.001) 0.21, V4 free (damping 0.2,
  stretch/leash 10) 0.20. Settings change the response little; lower damping and lower gravity make it CALMER, which
  hints the breeze couples through the damping/air-velocity term or is pendulum motion from the ship idle, not a force.
  Not yet tested: length (85 cm skirt, 1 m strips). Background agent notes: docs/research/BREEZE_AGENT.md.
  Installed in the game right now: flow variants on B-01 V1-V4 + cape-settings streamers on the other 19 archives.
- BREEZE MECHANISM (agent report 2026-10-21, docs/research/BREEZE_AGENT.md, read-only, unverified by a build yet): real
  engine wind. Aero object in field mode reads a 1024x1024 grid (2 m cells, world -1024..1024): ship grid uniform
  (101,12) = ~8.4 m/s toward -167 deg; planet once all zero. Engine BUG at 0x8a2890: in the normals branch the loop
  reads particle 0's mass for every particle (pointer never advanced): accel_i = A_i * mass[0] / (totalMass * mass_i).
  Our generator puts a FIXED particle (mass 0) at index 0 => our cloth gets exactly zero wind. The cape's particle 0 is
  free. Fix (data only): reorder so particle 0 is free; totalMass (+0x108, apparently used only by the wind) becomes a
  wind-response knob (~2.5 like the cape). Damping has no air velocity term; the flow-variant ratios were body motion.
  Next test: streamers with a free particle 0 and totalMass ~2.5; expect a lean toward -167 deg on the ship.
- Wind fix test 1 (2026-10-21): variations 1-3 got wind 1/0/2 -> user saw no difference. Live read: the streamers in
  memory still had a FIXED particle 0 and totalMass 0.864: the game loads the shared hip unit's cloth ONCE (from the
  variation equipped at launch); switching variations does not reload it. The earlier V1-V4 flow comparison was
  therefore probably one and the same cloth (differences = noise). Also: the engine RECOMPUTES totalMass at load
  (0.864 = 288 x 0.003), so totalMass is not a wind knob. Next: free-first build on all 23 archives.
- WIND WORKS (2026-10-21): generator puts a free particle first (engine wind bug workaround); [sim] wind sets
  hclSimClothData.totalMass = 2.562 / wind (0 => totalMass 0 => engine skips the wind). In game on the ship (streamers on
  all 23 archives, live values confirmed): wind 1 flaps like the cape, wind 2 whips around (live totalMass 1.281),
  wind 0 hangs still. The engine does NOT recompute totalMass (the earlier 0.864 was the old cloth, loaded once per
  session from the variation equipped at launch). Panel: Wind slider (Physics, default 1). Experimental piece option
  renamed cape_follow (not in the panel). Add-on 0.5.0; author package dist/HD2-Dress-0.5.0-for-authors.zip (add-on
  zip, GUIDE.html + pictures, reference docs, README). Button test 20/20 (Linux). Windows last verified on 0.4.1
  (20/20); the 0.5.0 changes are platform-neutral. Guide picture 08_physics predates the Wind slider.
  Installed in the game now: streamers wind 0 on all 23 archives (user: skip restoring the skirt).
- MOTION PREVIEW (add-on 0.6.0, 2026-10-21): panel section 3b. tools/viewer_assets.py (background Blender, once) caches
  the Helldiver skeleton + 8 animations (JOG RUN CROUCH STAND DIVE CRAWL GETUP HIT) and the stock cape's 17 body capsules
  (bone, offset, start/end, radius; HD2SDK bones = game node matrices, so placement is exact) in ~/.cache/hd2-dress/viewer.
  blender/hd2_dress/viewer.py: skins the armour from the Helldiver's pose itself (author's rig untouched), builds the
  cloth like the generator (particles by position, pins/top rows, links, bending pairs, stretch to nearest pin, leash to
  the skinned shape, capsules + kneecaps, floor, friction, gravity, damping, gusty ship breeze scaled by Wind), numpy
  Verlet with Jacobi links (bincount scatter), 2 substeps; preview copy object, original hidden; ~35 ms/frame for 648
  points. Approximation of Havok, not exact. Breeze test (stand, wind from the side): hem +0.18 m at wind 1, +0.40 at 2,
  0 at 0. Guide step 5b with two pictures; package dist/HD2-Dress-0.6.0-for-authors.zip. Button test 20/20.
- HANDOFF (2026-10-21, paused by user): motion preview 0.6.0 works (body mesh, loops, transfer-motion carry, thigh
  follow) but uses my own simplified formulas. User wants it "pretty darn close to Havok". Plan in progress:
  (1) generator preview mode: stash the exact arrays it builds (std links a/b/rest/kA/kB ~line 395, stretch ~413, leash
  ~436, hinges ~473, colliders keep_c/keep_ti/keep_off ~514-540 incl. kneecaps, bone planes ~575, sim skin p_skin
  ~639-646 + inv_bind per transform, constraintExecution ~656, particle data, gravity/damping, transfer motion) and dump
  them (npz) from a background job; viewer simulates THAT data. (2) A background agent extracts the exact Havok solver
  formulas from the engine -> docs/research/HAVOK_SOLVER.md (read-only). Not started: (1). Package
  dist/HD2-Dress-0.6.0-for-authors.zip is current (motion preview included). Game has wind-0 streamers installed.
- 0.6.1 (2026-10-22), from a user's failed build (10100 cloth points, 2431 pins; their log not seen yet): the panel's
  failure line hid the cause (HD2SDK's colour-coded lines were not filtered; Blender swallows a script's SystemExit
  text). Now every build error prints "ERROR: ..." and the panel shows it plus the log path; a killed build says "most
  likely out of memory". Generator no longer stops when cloth is weighted to a bone outside the 20 collision bones:
  the bone is added to the transform set (skinning only, no collider). Missing armour patch is a clear error. Panel
  warns when HD2SDK is not 3.11.0 (the tested version). Link batching measured fine at 10k points (5 s).
- 0.6.2 (2026-10-22): user's log showed the real crash: TypeError in Garment reading vertex weights; their mesh stores
  ONE influence per vertex (HD2SDK keeps a vertex's weight as a scalar then; its own importer does `if type(weights) !=
  list: weights = [weights]`), likely from parts hidden with the blank material. Generator now accepts scalar, list or
  missing weights/indices (padded to 4; no weights = fully on the first index). Normal builds byte-identical; 20/20.
- 0.6.3 (2026-10-22, on aero): the same user's next build passed the weight fix and stopped at "cloth faces use material
  None": no material section of their unit mesh holds the cloth triangles (or the id is not a number), likely from
  their blank-material setup. The error now lists every material section (id, triangle range, cloth triangles in it),
  and 4 Look has an optional "Cloth material ID" (look.material_id). Waiting for their next log / files. aero dev setup
  verified: add-on symlinked to the repo, tests/run_tests.sh 20/20.
- 0.6.4 (2026-10-22): user's logs: "0 cloth vertices" against a 2306-triangle mesh (their .blend skirt = 10100 verts):
  the patch's mesh does not contain the skirt (likely an older export, or the skirt is in another mesh of the unit).
  The build now (a) picks the LOD0 mesh that holds the cloth when a unit has several (prints a MESH line with each
  mesh's matching vertex count), (b) stops with a plain "your .blend matches NO vertex of the mesh in the armour patch:
  export again" instead of crashing in min() (manual material id path). Asked the user for the .blend + patch files.
- 0.6.5 (2026-10-22): motion preview removed from the guide, README and panel (user: unfinished/broken); viewer.py and tools/viewer_assets.py stay in the repo for later.
- 0.6.6 (2026-10-22): user's cloth works in game (RS-100 Cirrus, hip unit 1b5ea8db146989b2, bones = default diver) but the skirt sank inside the model's wider hips/buttocks: engine cloth collides with the stock cape's default-diver capsules, not the mesh. New Physics > Body fit sliders (hips, thighs, knees, lower back: collider radius change, collision.grow); verified in the built cloth (hips 0.146 -> 0.186 at +0.04). Guide rows added. Tests 20/20.
- 0.6.7 (2026-10-22): Body fit for every body part (hips, lower back, thighs, knees+shins, feet, head, shoulders, upper arms, forearms, hands): thickness, length scale, move forward/up/outward in body directions (pairs mirrored; collision.grow/length/offset). Chest: two added mirrored capsules in front of the chest (collision.chest; the stock chest is a convex hull), off until changed; verified placement (x +-0.075, 11 cm in front, z 1.30). Tests 20/20 incl. the new values. Not tested in game yet.
- 0.6.8 (2026-10-22): moved mesh nodes. User report (RS-100 skirt): drawn at the right height but hanging into the hips. Cause: the unit keeps the mesh on a node at (0.126, -0.02, 0.733) (stock RS-100; B-01 is at the origin). The game draws cloth through that node (character shader skins the render copy again with the unit's bind matrices, which HD2SDK makes relative to the node) while pins/colliders run in unit space. No cloth-side compensation is exact (constant root-frame offset after rigid motion), so: Check flags it, Fix all bakes the node into the mesh, moves the node's armature edit bone to the origin (HD2SDK writes edit bones back into the unit nodes on export) and resets the node in HD2SDK's in-memory unit bytes (export rebuilds from the ARCHIVE copy). Build refuses a moved node with the instructions. Verified headless on the user's patch: after HD2SDK export node = identity on both bodies, drawn bbox identical, cloth builds; the old patch is refused. Tests 20/20. Not tested in game yet.
- 0.6.9 (2026-10-22): Blender 4.0/4.1 (Python 3.10, no tomllib): user could not enable the add-on. tomli 2.0.1 (MIT, the library tomllib came from) bundled in tools/_vendor as the fallback. All add-on code compiles under Python 3.10; full test 20/20 on Blender 4.0.2 with the zip installed as users do, and 20/20 on 5.2.2. tests/run_tests.sh uses fixtures/skirt_test_b4.blend (re-saved by Blender 4.5) on Blender 4.x.
- 0.6.10 (2026-10-22): back side. User video: a half skirt vanishes seen from the front. The guide said cloth draws both sides: true only for the cape shader; the character (colour map) look is evidently one-sided. New 4 Look > Add back side (reversed exact copy of the cloth faces: shares particles, so no drift and no flicker with one-sided drawing); settings write cloth.allow_double_layer with the colour-map look; Check accepts a back side with that look (still PROBLEM with the cape look), Fix all leaves it facing inward. New Check: two separate layers a few mm apart (Solidify-style walls) = two cloths that drift apart. Their .blend (B-01 Stocky) had exactly that (3 mm walls, 2453 faces) plus 179 cloth faces on a second material (invisible in game). Tests 21/21 on Blender 5.2.2 and 4.0.2. Not tested in game: whether the character look is one-sided is inferred from their video.
- 0.6.11 (2026-10-22): HD2SDK export with cloth groups. Found while rebuilding a user's half skirt: HD2SDK's unit export treats every vertex group as a bone and stops on cloth_*/pin ('not a valid vertex group'); its PrepareMesh also runs normalize_all + limit_total(4) over all groups, so ours can push real bone weights out. Reproduced on our own test scene (always failed: the tests never exported through HD2SDK). Fix: the add-on wraps HD2SDK's stingray.unit.duplicate (only used by PrepareMesh for the throwaway export copy) and drops our groups from the copy; re-hooked every 5 s if HD2SDK reloads, restored on unregister. New test: HD2SDK export of the test scene with cloth + pin groups (22/22 on Blender 5.2.2 and 4.0.2). User half skirt rebuilt (inner wall and 2nd-material faces removed, back side, Fix all, HD2SDK export, build): dist/test-halfskirt-0.6.11 (built with tartan test colours; not tested in game).
- 0.6.24 (2026-10-24): FLYING VERTICES found in live memory (tools ~/hd2-memtools/clothscan.py: live particle array matched by head-rigid pinned probes): a tester (SA-7 cloak)'s cloak had exactly two particles 174 m and 273 m away, a mirror pair at the neck (free, interior, next to three pinned points). Their bend hinge had stiffness -303408 (median -0.0009): free weight 0.000056, thebf333's guard skipped only below 1e-10. Now: skip a hinge when its free part carries < ~0.1 of a free vertex (effective < 1% of max inverse mass), and clamp every hinge to 20x the cloth's median stiffness. Cloak rebuilt: max 0.0188, median 0.0009. Likely also a tester (RS-100 skirt)'s 'one single part explodes'. 27/27 on 5.2.2.
- 0.6.23 (2026-10-24): a tester (SA-7 cloak)'s cloak, tested in game on bongo step by step:
  - ALIGNMENT: their build showed the vanilla armour (the whole 9ba626 patch ignored). HD2SDK writes TOC data back to back; an odd-sized entry (type 0x18dead01056b72e9) put the cloth at an odd offset. tools/align_patch.py re-lays every entry on 16 bytes (data byte-identical); aligned = model loads, cloak moves. The build aligns every patch; new test.
  - ONE MATERIAL PER CLOTH MESH: the cloak showed body-texture patches with any cloak material (template, their own, colour map); swapping the unit's two material slots made the cloak right. The game draws a mesh carrying cloth with its FIRST material only (the stock cloths all have one). New Check PROBLEM (mesh with more than one material); guide rule 5: cloth on a unit of its own.
  - WIND MASS: totalMass was a fixed 2.562; the cape's 2.562 is the sum of its free particle masses (854 x 0.003). Now totalMass = real free mass / wind. The cloak (2333 free x 0.004 = 9.3) had acted 3.6x lighter; live tests with tools/havok/re/livewind.py (finds the cloth by name; livetune's vtable anchor broke after a game update): wind 0.15 calmer, 0 = no wind but single vertices still spiking.
  - COLLIDER START OVERLAP: 2054 of the cloak's 8322 free vertices started inside colliders (spine 1530, arms). The build now shrinks a capsule when >= 50 points and >= 3% of the free points start truly inside it (radius - 5 mm), to clear them, never below 70% (collision.auto_fit = false: off); the B-01 skirt (~25 points resting inside the thighs) is untouched. Check WARNING with the same rule.
  - Not the cause: the 56-byte vertex layout (a tester (RS-100 skirt)'s 64-byte unit does not match the cloth layout either), the double layer (removed: no change), the material (original material: same).
  Tests 27/27 on 5.2.2.
- 0.6.22 (2026-10-24): the cloth also goes into the author's armour patch (the archive of the modded unit). In-game on bongo with a tester (RS-100 skirt)'s RS-100: cloth only in the unit's original archive 1e2ba... = the Superstore preview froze (game threads idle, no GPU error); without the cloth no freeze; a 525-point cloth froze too (not size); cloth inside the armour patch (9ba626...) = the store loads (static there), the skirt moves in the ship. a tester (SA-7 cloak)'s crashing torso had the same split (cloth d895..., unit in 9ba626...). Still open: shards in the loadout/armour screen (LOD1-3 on the cloth material; test with LODs on a non-cloth copy is installed), one small part of the skirt exploding in the ship. 26/26 on 5.2.2.
- 0.6.21 (2026-10-24): a tester (RS-100 skirt): the Colour map look works now; Keep my material still glitched (most likely tested with 0.6.18, whose Keep could not switch IgnoreSkinning on for an HD2SDK-made material: fixed in 0.6.20). Also: UV tangents (thebf333) now also with Keep my material (the author's material has its own normal map), not only with a colour-map normal map. 26/26 on 5.2.2.
- 0.6.20 (2026-10-24): a tester (SA-7 cloak)'s torso cloth crashed the game. The cloth render copy had the cape layout (stride 60, no TEXCOORD15): 4 Look was 'My own cloth material' (cape shader) while the torso uses a normal armour material (parent 17265463703140804126 = the character family). The build now refuses that (cloth material of the character family + cape look). Keep my material reworked: HD2SDK-made armour materials carry 42 of the shader's 77 values and no IgnoreSkinning, so Keep now puts the author's textures (by slot name) and values (by name) on the full character template and switches IgnoreSkinning on; other shader families are copied as they are. Verified on a tester (SA-7 cloak)'s material 9300104334702531523: 11 textures kept, 77 values, IgnoreSkinning 1/1/1; cape-mode build of their torso refused for both materials.
- 0.6.19 (2026-10-24): a tester (SA-7 cloak) built from a patch exported before the cape was marked: the build said 'moved node' (the origin check ran first) instead of 'the cloth matches no vertex ... export the patch again'. The origin check now only runs when cloth vertices were found. 26/26 on 5.2.2.
- 0.6.18 (2026-10-24): Keep my material (4 Look). a tester (RS-100 skirt)'s 0.6.16 build: the colour map in it is right (their full atlas), the cloth section uses our fixed material, but their original skirt material (same Illuminate character parent 17265463703140804126) has its own Nar, IlluminateData and tuned values, which a colour map + roughness cannot reproduce; the top band of their skirt is still on that old material (8076 tris). New look.keep_material: the build copies the author's material (armour patch, else the game) under its own id, textures and values untouched, only IgnoreSkinning0-2 = 1; warns when the shader has no IgnoreSkinning. Verified: source vs built material = identical TexIDs, only the 3 IgnoreSkinning values changed; missing material = clear error. Tests 26/26 on 5.2.2 and 4.0.2 (Keep settings round trip, panel draws all three looks).
- 0.6.17 (2026-10-24): a tester (SA-7 cloak) (Discord) wants cloth on Brawny only and got 'Slim has no cloth pieces' / 'Stocky ...' three times each. The sibling rule counted every mesh of the same SLOT (armour, undergarment, accessory) of any body. Now: the same piece (slot + piece type) on another body type (not 'Any'); one note: 'the cloth is only on Brawny: Slim and Stocky get no cloth. Fine if that is what you want; ...'. Copy pieces to the other body used the same loose rule and would also have copied the cloth groups onto undergarments by position: same fix. Test: an extra undergarment mesh in the slot is neither noted nor copied onto, the note comes once. 25/25 on Blender 5.2.2 and 4.0.2.
- 0.6.16 (2026-10-24): a tester (RS-100 skirt) in game: skirt drapes right now, but the surface looked shiny/odd ('roughness or metallic messed up'). Cause: without a normal map the character material kept the TEMPLATE's Nar texture (Illuminate loin cloth: normal, AO, roughness laid out for its UVs) and ignored the Roughness value. Our in-game tests always had a normal map, so this path was never seen. Fix: Nar is always built (flat normal without a normal map, AO map or 255, roughness map or the Roughness value); roughness map field shown without a normal map too. Remaining template texture: SclarFieldOpacity (untouched, as in every tested build). New test: the built material's Nar is ours and stored in the patch (fails with the old code). 25/25 on Blender 5.2.2 and 4.0.2.
- 0.6.15 (2026-10-24): Show colliders (Body fit), asked for by a tester (RS-100 skirt): blender/hd2_dress/colliders_view.py draws the stock capsules on the author's rig with Body fit (thickness, length on the body capsule only, move in body directions, pairs mirrored), kneecaps (collision.extra) and the chest capsules (collision.chest) applied exactly as gen_engine_cloth does; hands skipped (opt-in in the settings file only), attach_* skipped. GPU line drawing in a POST_VIEW handler (no scene objects, nothing saved), picked part green, live via update callbacks on every fit slider, kneecaps and the part list. Collider cache read once from the game (shared ensure_colliders with Fit to my model). Test: hips +0.05 thick -> radius +0.05, -0.03 forward -> moved 3 cm back; 24/24 on Blender 5.2.2 and 4.0.2 (bongo). Guide picture 08c_colliders.
- 0.6.14 (2026-10-23): ALL guide screenshots retaken (1 pieces, pins, copy, preview too) from a real Blender window (XWayland, tools/guide_shots_engine.py draws one panel section per picture; tools/guide_crop_engine.py cuts the sidebar down to the panel): 05/07 Check, 08 Physics, new 08b Body fit (after Fit to my model), new 09 Look (Add back side), 11/12 Build. The pictures showed the Fit row truncated ('Fit to ...') and the fit summary cut off in the default sidebar width: Fit button on its own row, Cover/Extra gap below, summary lines wrap; the roughness-map field only shows with a normal map. Body fit is its own draw method (draw_body_fit). Tests 23/23 on 5.2.2 and 4.0.2.
- 0.6.13 (2026-10-23): Fit to my model (3 Physics > Body fit). Stock cape capsules dumped once from the game (hd2dress_cloth.py colliders -> ~/.cache/hd2-dress/colliders.json, 19 capsules), placed on the author's rig (world = p @ off @ W_bone, W = bone.matrix_local transposed as HD2SDK exports). Per capsule: body vertices of that body type weighted mostly to the bone (cloth vertices left out) within stock radius + 12 cm; capsule moved to their centre (perpendicular mean), radius = the 'Cover' quantile of their distances (default 0.85) + Extra gap. Hips/lower back use the whole body slice at their height (+-6 cm, the waist is weighted to several bones) and never move up/down (torso above pulled them 11-17 cm up); clavicles/head slice their own bone. Pairs averaged, the build mirrors. a tester (RS-100 skirt)'s RS-100 VRChat model (Slim): stock colliders are larger than the body everywhere (hips 7 cm gap at waist height, head 8 cm); fitted hips -2.3, lower back -4.7, thighs -2.2, shins -2.6, head -8.0 cm; renders in ~/.cache/hd2-dress/scratch/fit/*_compare.png. B-01 test scene (diver-shaped) moves only ~1 cm. New test 23/23 on 5.2.2 and 4.0.2. Their skirt built with the fit (dist/test-rs100-fit) and installed on aero with the origin-fixed RS-100 patch for an in-game test.
- 0.6.12 (2026-10-23): released. Everything below marked unreleased, plus the last of thebf333's fixes that the first merge left out: author-pinned points keep their bone weights under thigh-follow (pins lower than the waistband no longer ride the thigh). Roughness map labelled 'needs a normal map'. Tests 22/22 on 5.2.2 and 4.0.2.
- unreleased (2026-10-23): merged thebf333's fixes (bend near-singular hinge guard: two hinges with 3 pinned points exported ~-3.4e10 stiffness = ribbons in game; HD2SDK 3.10.4 texture-slot fallback; roughness map + AO/roughness resized to the normal map; UV tangents, used only with a normal map). render_backfaces build option (his render-only back side, reimplemented) for an A/B test against Add back side: dist/abtest-A-backside, dist/abtest-B-renderonly (B-01 half skirt). Body fit Thickness now down to -0.25 m (was -0.10), collider radius clamped at 5 mm: a tester (RS-100 skirt)'s slim VRChat model still stood off the hips at -0.10 (hip capsule 0.146 m). Tests 22/22 on 5.2.2 and 4.0.2.
- 2026-10-23 jiggle ball (tools/experiments): ball on the B-01 HIP unit weighted 100% chest flattened when leaning forward even with leash 0 and no arm colliders. Bones Fix all adds to a unit (chest, spines, knees...) are not animated by the game (hip unit has only skeleton/root/boss/hips/thighs natively, no BonesRef, no connecting-bone data): they ride along from the hips. OPEN QUESTION for skirts: knee/shin/torso colliders on hip units may not follow shin bend / torso lean; waiting on thebf333's build before acting. HD2SDK per-bone 'Animated' / 'Jiggle' props untested. Also: opt-in hand colliders (collision.hands). Next: ball on the B-01 torso unit (native chest).
- 2026-10-23 TOOL GAP: when the author's armour patch archive is also one of the cloth archives (torso ball: both 08e906980c632592), the build writes a cloth-only patch_0 with the same name as the armour patch; it only merges the armour patch for the material's archive. Test installed the armour as patch_1 by hand. Fix later: merge the armour entries into that archive's cloth patch (or install as the next patch number).
- 2026-10-23 jiggle ball on the B-01 TORSO unit: exploded until the ball unit was in EVERY cloth archive's patch (game loads the torso from another archive than 08e9: unit/cloth mismatch = explosion; tools/experiments/spread_units_to_cloth_patches.py). Then flattening when leaning (Shotgun Show) bisected with collision.skip: no colliders = round; no spine2 = flat; chest+hips only = round => the CLAVICLE capsules (they swing forward with the arms, 10-11 cm behind the ball at rest). Chest pieces: skip l_clavicle/r_clavicle. Next build: leash 0.10, damping 0.03, motion carry off, bend 1.0, inward 0 ('obscene jiggle').

## 2026-10-24 (part 3): multi-material cloth meshes, engine read (no code change yet)

Read with Ghidra (rva in helldivers2.exe build of 2026-10-24, ~/hd2-re/dec.sh):
- fn 0x8a11a0 (render object for one type-4 cloth display buffer) builds its own vertex/index buffers from the tail
  and sets EXACTLY ONE draw batch, hardcoded: {start 0, triangles = numIndices / 3, vertices = numVertices, count 1}
  via the render interface (+0x38)(handle, 1, &batch). So one cloth mesh can never draw two materials; no data fixes it.
- fn 0x7eec20 = the tail loader (resource +0x90 -> tail; fills resource +0x98..+0x100). Tail offset table T[0..5]:
  * T[0] (0x20): unknown list {count, entries_off, ...}, entries 0x50 bytes with byte indices into the data table
    (count 0 in every stock cloth).
  * T[1] (0x30): DISPLAY MESHES {u32 count, u32 entries_off (from the section start), u32 hashes[count]}, entries
    0xf8 bytes each. Entry: +0x00 8 x u64 = data-table indices of the vertex streams (0 = none), +0x40 8 x u32 strides,
    +0x60 numVertices, +0x64 16 x (format, type|index<<16), +0xe4 numComponents, +0xe8 u64 data-table index of the
    index data, +0xf0 index type (2 = u16), +0xf4 numIndices. 0x8a11a0 picks the entry whose hash = murmur32(buffer name).
  * T[2] (0x140): transform sets {count, entries}; T[3] (0x160): DATA TABLE {u32 count, entries of 0x18:
    u32 stride, u32 count, u32 offset from the bulk base, pad, u64 ptr filled at load}; entry 0 is the null entry
    (cape: 1 vertices, 2 indices, 3/4 bind matrices). T[4] (0x1e0): bone list; T[5]: bulk base.
- So the engine supports SEVERAL display meshes per cloth (one sim, one batch and one material each): N tail entries +
  N type-4 buffers, each with its own Display Skin, MeshDeform and Convert Output operator (+ shadow buffer).
- The blocker is the unit: every extra mesh needs its own LOD0 mesh slot. Units seen (a tester (SA-7 cloak)'s patch) have exactly one
  LOD0 mesh, and HD2SDK cannot add mesh slots (MeshInfoIndex must exist).
- Also: the render copy holds the WHOLE mesh, so armour faces sharing a cloth mesh are drawn with the first material too.
Routes (waiting for the authors to choose, the user does not want to decide for them):
  1. build-time texture atlas of every material on the mesh, UVs remapped in our render copy only (no author change;
     limits: no UV tiling outside 0..1, one set of shader values, shared texture resolution);
  2. several meshes driven by one sim, the extra parts on another unit (full materials; authors split their model);
  3. our own unit editing to add a LOD0 mesh slot (invisible to authors; riskiest, HD2SDK overwrites it on export).
