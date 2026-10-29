# Ship breeze on capes: research notes (agent, 2026-10-21)

Read-only work. RVAs are for the dumped build (~/.cache/hd2-dress/re/helldivers2.exe.fixed.exe, Ghidra base
0x6ffff9990000) unless marked live. Decompiles: /tmp/breeze_mgr.c, /tmp/breeze_upd.c, /tmp/breeze_step2.c,
/tmp/breeze_step3.c, /tmp/breeze_simop.c, /tmp/breeze_simop2.c, /tmp/breeze_int.c.

## 1. Everything the engine feeds a cloth each frame (static, verified in code)

Per world update rva 0x7d4f30 -> 0x7d4d80 -> 0x7d3f50 (per cloth slot) -> Havok step 0xf0aff0.

- 0x7d3f50, per cloth slot: asks the unit for the world matrices of the cloth's bones (API slot +0xa0) and writes them
  into the cloth instance's transform sets (0xf0bd10). If the slot was flagged (teleport), it also rebases the particles.
  If the instance has a pending state (+0x58 != 0x7fffffff) it calls 0xf11200 (state change). Nothing wind-like here.
- 0x7d4f30: per frame sets every sim instance to mode 2 with +0x144 = 1.0 and +0x148 = clamp((1/dt)/60, 1, 8)
  (0xf058a0; a frame-rate dependent time factor), then steps the world (0xf0aff0).
- 0xf0aff0: per cloth instance, runs the operators of the current state (vtable +0x20). The simulate operator
  (hclSimulateOperator vtable rva 0x14eab00, execute 0x1017fe0 -> 0x1018000) runs the substep loop; each substep calls
  the Verlet integrator 0x101fa40.
- Integrator 0x101fa40 (verified): it zeroes a per-particle force buffer, calls every action in the sim instance's
  action list (+0xe8, count +0xf0) as `action->vt[+0x18](action, simInstance, dt, forces)`, then
  `x_new = x + (x - x_prev) * damp + (F_i + m_i * gravity) * invMass_i * dt^2` (damp = sim instance +0x54).
  So the ONLY external inputs to a particle are: gravity (data), the action forces, and (through constraints) the
  bone-driven transform sets and collidables.

The only action on every cloth is the HD2 aero object (created in 0x7d51d0, vtable rva 0x16a18d8, apply 0x8a2400).
No hclSimpleWindAction (vtable rva 0x14eaf88, apply 0xf6b9c0) is attached, and the cape data has no actions.

## 2. The aero object and the wind vector field

- Setters (verified): 0x7d3830(world, grid_ptr, N, strength) writes +0x28 grid ptr, +0x20 N, +0x1c strength into the
  aero of EVERY cloth in the world; 0x7d3910(world, vec3) writes +0x30..+0x38 into every cloth's aero. No direct
  callers, no pointers to them in the image, and the code that uses the strings wind_vector_field,
  WindVectorField, wind_vector_field_readback, wind_vectorfield.cpp has no plain lea/abs references either (probably
  reached through a runtime-built table or obfuscated code); not resolved.
- Field mode (+0x20 = N != 0, live N = 1024): the cloth's bounding-box centre (sim instance +0x60/+0x70, x and y,
  Stingray is Z-up) indexes an N x N grid covering world -1024..+1024 m (cell = 2048/N = 2 m), 2 bytes per cell:
  byte0 = speed, byte1 = direction. Wind = (byte0/255)^2 * strength(+0x1c = 64 m/s max), horizontal only, times +0x3c.
  Outside the grid, or a zero cell, gives no wind. This grid is almost certainly the CPU readback of the engine's
  WindVectorField (the same wind texture vegetation uses; strings sit together in wind_vectorfield.cpp). Inferred,
  not proven by a code xref.
- Vector mode (+0x20 == 0): wind = +0x30 vector * +0x3c. Not used live (all aeros are in field mode), so the +0x30
  values seen earlier are ignored by the apply function.
- Extra term (+0x48 = 1, +0x4c = 0.01): adds (x_prev - x)/dt * 0.01 to the air velocity, so moving cloth feels a small
  self-induced drag even with no wind. The decompile accumulates it across the particle loop (not reset per particle).
  This term was NOT touched by the earlier field-strength A/B test.
- Per particle force = w * m_i / totalMass (simClothData +0x108, the stored `totalMass` field). The integrator then
  multiplies by invMass_i, so the wind ACCELERATION of a particle is w / totalMass: the per-particle masses cancel,
  only the stored totalMass scales it. Havok's own hclSimpleWindAction (0xf6b9c0) uses the same m_i/totalMass
  weighting, which matches its warnings "(... kg) total mass for cloth. Forces (like wind) may cause large
  accelarations" / "may have almost no effect".

## 3. THE KEY BUG: the aero force is scaled by particle 0's mass (verified in assembly)

In the normals path of the aero apply (taken when the sim instance's normal count +0x48 == particle count +0x28,
which is true for the cape and for our cloth), the mass pointer r9 = simClothData+0x40 (particleDatas) is loaded once
and never advanced: `mulss xmm1, [r9]` at rva 0x8a2890, with only r11/rdx/rdi/r8 incremented in the loop
(0x8a26d0..0x8a28ae). The decompile shows the same (pfVar14 never incremented in that loop; it IS incremented in the
no-normals path). So every particle's force is `A_i * mass[0] / totalMass`, and after the integrator's invMass_i:

    accel_i = A_i(air, normal_i) * mass[0] / (totalMass * mass_i)

If particle 0 is a FIXED particle (mass 0), the whole cloth gets ZERO wind force.

Live (ship, read-only, /tmp/breeze_sim.py, /tmp/breeze_force.py):

| active sim instance | particles | particle 0 mass | totalMass | wind weight m0/M |
|---|---|---|---|---|
| player's cape (984) | 984 | 0.003 (free) | 2.562 | 0.00117 |
| our 12 streamers (324) | 324 | 0.0 (fixed) | 0.864 | 0 |
| other cape copies (943) | 943 | 0.003 (free) | 2.409 | 0.00125 |

Second loop quirk (assembly): when |air| < 0.001 the loop skips the pointer increments, so later forces land on the wrong
particles. Only matters when the air velocity is near zero.

## 4. Live state on the ship (2026-10-21, read-only)

- All live aeros are in field mode: N 1024, the same grid pointer, strength 64, +0x3c 1.0, +0x40 0, +0x48 1, +0x4c 0.01.
  The ship grid is UNIFORM: every one of the 1024 x 1024 cells = (speed 101, direction 12), and it did not change over
  2 s. Decoded: (101/255)^2 * 64 = 10.0, direction (-0.81, -0.19) => wind (-8.15, -1.89, 0) m/s, 8.4 m/s toward
  -167 deg. Earlier the same session read an all-zero grid while the aero +0x30 held a planet-like position (the
  game was on or leaving a planet; not certain). Planet = zero field is the likely reason capes hang still there,
  but only that one planet read exists (unverified for windy/storm planets).
- Re-evaluating the apply on live data (cape, normals path, particle 0 free): median wind acceleration about
  8.5 m/s^2 per free particle (gravity 9.81). For our streamers the code gives exactly 0 because particle 0 is fixed.
  (If particle 0 were free, the same code would give about 27 m/s^2 for them, because their totalMass is only 0.864.)
- Observed geometry agrees: our 12 streamers hang straight (per-strip hem minus top horizontal offset averages
  (-0.002, -0.006) m; no lean toward the wind). The player's cape hem sits 0.73 m behind the top (meter: lean 0.51 m on
  the ship vs 0.38 m on the planet); the player happened to face into the wind, so this one is consistent with the wind
  but does not prove it on its own.
- Motion correlation (/tmp/breeze_disc.py, 12 s at 30 Hz): our streamers' particle speed correlates 0.84-0.90 with the
  chest speed, and their flutter (0.83-0.86 cm) is about the chest's own motion (0.77-1.42 cm std, 0.6-1.8 deg).
  The cape (3.1-3.2 cm) correlates only about 0.49-0.50 with chest speed: it has a large component of its own.
- One unexplained case: the 943-particle cape copy at (1.5, 13.9) hangs straight (hem offset 0.06 m) although its
  particle 0 is free and its aero is identical. Its transform set has bones at z = 0 (a preview/mannequin unit), so
  it may not be in a normal simulated state. Not investigated further.

## 5. Conclusion

- The ship breeze IS the engine's per-world wind field (uniform 8.4 m/s on the ship), applied to every cloth through
  the aero action. It is NOT an animation effect for the cape, and it does not go through damping.
- Our generated cloth never received it: the generator puts a fixed particle at index 0, and the aero code scales the
  whole cloth's force by mass[0]. That is also why the earlier "field strength 0 vs 100x on our cloth" test changed
  nothing: our aero was already dead. The test proves nothing about the cape.
- Our streamers' ship-vs-planet flutter difference (0.8-2.1 vs 0.1 cm) is therefore body motion only (ship idle vs
  planet stance), passed through leash/links. That fits the high correlation with chest speed.

## 6. Data-only control (what an author can set in the cloth file)

1. REQUIRED: particle 0 of each simClothData must be a free particle (mass > 0). Reorder particles so a free particle
   comes first (the stock cape does this). Without this the cloth gets no wind at all.
2. Strength: accel_i = A_i * mass[0] / (totalMass * mass_i). With uniform masses this is A_i / totalMass. Levers:
   - simClothData.totalMass (the stored field at +0x108). In the integrator only per-particle mass/invMass are used, so
     totalMass looks like a pure "wind response" knob. To match the cape, use about 2.5. UNVERIFIED: whether anything
     recomputes totalMass at load (live values equal the sum of free masses for both cape and streamers, so the test
     cannot tell). Test: build with masses unchanged and totalMass changed, then read simClothData+0x108 live.
   - mass[0] relative to mass_i (a heavier particle 0 strengthens the whole cloth; lighter particles also move more).
     Gravity is unaffected by masses ((m g) * invMass = g).
   - Normals: with a normal per particle (normal count == particle count) the lift/drag path is used (above).
     Otherwise a simple drag path: F_i = ((x_prev - x)/dt + air) * mass_i/totalMass * 10 * 0.7 (+0x18 * 0.7), weight
     correctly per particle.
3. Per-world (not data): strength +0x1c, the grid itself, +0x3c, the clamps and the rho/coefficient tail all live in the
   engine-created aero object (constructor 0x7d51d0 and setter 0x7d3830); a data file cannot change them.

## 7. Damping (question from the coordinator)

The integrator (0x101fa40) applies damping as `x + (x - x_prev) * damp` with damp = sim instance +0x54 (live 0.9817 to
0.985, consistent with (1 - globalDampingPerSecond)^dt for dt near 1/70 s; that formula is NOT verified). No air or wind
velocity takes part: damping is pure world-space velocity loss. The only air velocity in the whole step is inside the
aero action. So the breeze cannot enter through damping; the variant ratios (0.20 to 0.33) of our streamers are body
motion seen through different stiffness/damping, not wind.

## 8. Suggested next tests (by the main session, via builds, no live writes)

- Rebuild the 12 streamers with a free particle at index 0 (and totalMass about 2.5). On the ship they should lean
  toward world -167 deg and flutter like the cape; on a calm planet they should hang still.
- Optional read-only check after that build: /tmp/breeze_sim.py shows particle 0 mass and totalMass of the new cloth.

## Scripts written (all read-only)

/tmp/breeze_grid.py (aero objects + grid), /tmp/breeze_sim.py (active sim instances), /tmp/breeze_force.py (re-runs the
aero formula on live data), /tmp/breeze_disc.py (bone vs cloth motion), /tmp/breeze_lean.py, /tmp/breeze_lean2.py,
/tmp/breeze_log.py, /tmp/breeze_ptr.py, /tmp/breeze_tset.py and /tmp/breeze_livevt.py (copies of tset.py/livevt2.py that
write their own output files instead of the shared /tmp/tsets.json and /tmp/engine_live.bin).
