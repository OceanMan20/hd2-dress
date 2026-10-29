-- Offline tests for step 3: body colliders (mod/lib/body.lua), open sheets, layers and the safeties
-- (DEEP, MAX_SPEED, floor) in chain.lua / skirt.lua. Run from the repo root: luajit tools/test_body.lua
local Chain = assert(loadfile('mod/lib/chain.lua'))()
local Skirt = assert(loadfile('mod/lib/skirt.lua'))()(Chain)
local Body = assert(loadfile('mod/lib/body.lua'))()
local out = {}

-- the Helldiver's rest skeleton (from sim/anims/full_run.json, stocky body)
local J = { hips = { 0, -0.021, 0.973 }, spine1 = { 0, -0.021, 0.973 }, neck = { 0, -0.041, 1.55 }, head = { 0, -0.025, 1.691 },
            l_shoulder = { -0.21, -0.069, 1.474 }, l_elbow = { -0.472, -0.054, 1.324 }, l_hand = { -0.657, 0.14, 1.219 },
            r_shoulder = { 0.21, -0.069, 1.474 }, r_elbow = { 0.472, -0.054, 1.324 }, r_hand = { 0.657, 0.14, 1.219 },
            l_thigh = { -0.087, -0.019, 0.942 }, l_knee = { -0.144, -0.034, 0.516 }, l_foot = { -0.191, -0.118, 0.104 },
            r_thigh = { 0.087, -0.019, 0.942 }, r_knee = { 0.144, -0.034, 0.516 }, r_foot = { 0.191, -0.118, 0.104 } }

-- 1. colliders: 4 leg + pelvis + torso + 4 arm + head; legs only when BODY_COLLIDE = 0; missing joints skipped
local caps = Body.capsules(J, { ARM_COLLIDE = 1 })
local names = {}; for _, c in ipairs(caps) do names[#names + 1] = c.name end
assert(#caps == 11, 'eleven colliders with the arms: ' .. table.concat(names, ' '))
assert(#Body.capsules(J) == 7, 'seven by default (arms off: holstering)')
assert(#Body.capsules(J, { BODY_COLLIDE = 0 }) == 4, 'legs only')
local J2 = {}; for k, v in pairs(J) do J2[k] = v end; J2.l_hand = nil
assert(#Body.capsules(J2, { ARM_COLLIDE = 1 }) == 10, 'a missing joint skips only its collider')
assert(math.abs(Body.floor(J) - (0.104 - 0.09 - 0.01)) < 1e-9, 'standing: the floor is at the soles')
local Jp = { hips = { 0, 0, 0.14 }, l_knee = { -0.1, 0.4, 0.07 }, l_foot = { -0.1, 0.8, 0.12 } }   -- prone
assert(math.abs(Body.floor(Jp) - (0.07 - 0.06 - 0.01)) < 1e-9, 'prone: the floor is under the knee')
out[#out + 1] = '7 colliders (11 with ARM_COLLIDE)'

-- 2. which colliders a part ignores: the one its top sits on, nothing else
local waist = {}   -- a skirt's anchors: a ring of r = 0.17 around the hips
for i = 1, 12 do local a = 2 * math.pi * i / 12; waist[i] = { 0.17 * math.cos(a), -0.021 + 0.17 * math.sin(a), 1.0 } end
local ign = Body.fit(caps, waist, { MARGIN = 0.03 })
assert(ign.pelvis == false and ign.l_thigh == nil and ign.l_upperarm == nil and ign.head == nil, 'skirt drops the pelvis only (default rule)')
local roots = { { 0, 0.05, 1.80 }, { 0.04, 0.05, 1.79 } }    -- hair rooted inside the head mesh
local ignh = Body.fit(caps, roots, { MARGIN = 0.03 })
assert(ignh.head == false and ignh.torso == nil, 'hair rooted in the head drops the head only')
assert(#Body.apply(caps, ignh) == 10, 'the hair keeps the other 10')
local scalp = { { 0, 0.07, 1.86 }, { 0.05, 0.07, 1.84 } }    -- hair pinned ON the scalp: drapes over the head
assert(Body.fit(caps, scalp, { MARGIN = 0.03 }).head == nil, 'hair on the scalp keeps the head collider')
local back = { { -0.08, 0.15, 1.42 }, { 0, 0.16, 1.43 }, { 0.08, 0.15, 1.42 } }   -- a cape pinned on the back of the chest
assert(next(Body.fit(caps, back, { MARGIN = 0.03 })) == nil, 'a cape on the back keeps the torso collider')
-- BODY_FIT 1: thinner instead of dropped, so a body core stays inside the waistband
local thin = Body.fit(caps, waist, { MARGIN = 0.03, BODY_FIT = 1 })
assert(type(thin.pelvis) == 'number' and thin.pelvis < 0.11 and thin.pelvis >= 0.4 * 0.11, 'BODY_FIT: the pelvis is thinner, not dropped: ' .. tostring(thin.pelvis))
local mine = Body.apply(caps, thin)
for _, cp in ipairs(mine) do for _, a in ipairs(waist) do
  assert(Body.dist_to(cp, a) >= cp.r + 0.03 - 1e-9 or cp.name ~= 'pelvis', 'every anchor outside the thinner pelvis + clearance')
end end
assert(Body.fit(caps, roots, { MARGIN = 0.03, BODY_FIT = 1 }).head == false, 'BODY_FIT: a collider that would be tiny is still dropped')
out[#out + 1] = string.format('skirt drops the pelvis (or keeps a %.1f cm one with BODY_FIT), cape keeps the torso', 100 * thin.pelvis)

-- 3. open sheet: a cape-like U of strips around the back. As a RING the strip-5 -> strip-1 panel
--    closes across the chest and a torso capsule in front collides; as an open SHEET nothing does.
local function cape(open)
  local nc, L = 5, { 0.1, 0.1, 0.1 }
  local S = Skirt.new(nc, L); S.open = open
  local A, T = {}, {}
  for c = 1, nc do
    local a = math.pi * (c - 1) / (nc - 1)                          -- 0..180 deg: right, back, left
    A[c] = { 0.2 * math.cos(a), 0.2 * math.sin(a), 1.4 }
    T[c] = {}; for j = 1, 3 do T[c][j] = { A[c][1], A[c][2], 1.4 - 0.1 * j } end
  end
  local front = { { a = { -0.05, -0.0, 1.3 }, b = { 0.05, 0.0, 1.3 }, r = 0.04 } }   -- inside the U, on the open side
  local P = { GRAVITY = 0, MARGIN = 0.01 }
  local hits = 0
  for _ = 1, 30 do Skirt.step(S, A, T, 1 / 60, P, front); hits = hits + (S.hits or 0) end
  return hits
end
local ring_hits, sheet_hits = cape(false), cape(true)
assert(ring_hits > 0, 'a ring closes across the open side (hits ' .. ring_hits .. ')')
assert(sheet_hits == 0, 'an open sheet leaves it open (hits ' .. sheet_hits .. ')')
out[#out + 1] = string.format('open sheet 0 hits vs ring %d', ring_hits)

-- 4. one-strip sheet still collides (no panels: joint collision)
do
  local S = Skirt.new(1, { 0.1, 0.1, 0.1 }); S.open = true
  local A = { { 0, 0, 1 } }
  local T = { { { 0, 0, 0.9 }, { 0, 0, 0.8 }, { 0, 0, 0.7 } } }
  local cap = { { a = { -0.2, 0.03, 0.8 }, b = { 0.2, 0.03, 0.8 }, r = 0.05 } }
  for _ = 1, 30 do Skirt.step(S, A, T, 1 / 60, { MARGIN = 0.01 }, cap) end
  local p = S.out[1][2]
  assert(math.sqrt((p[2] - 0.03) ^ 2 + (p[3] - 0.8) ^ 2) >= 0.06 - 1e-6, 'one-strip sheet collides')
end

-- 5. DEEP: a body part that jumps through the cloth in one frame (ragdoll, a snap into prone)
--    leaves the cloth on the side it was on, instead of shoving it through
local function deep_case(deep)
  local S = Skirt.new(2, { 0.1, 0.1, 0.1 }); S.open = true
  local A = { { 0, 0, 1 }, { 0.1, 0, 1 } }
  local T = { {}, {} }
  for c = 1, 2 do for j = 1, 3 do T[c][j] = { A[c][1], 0, 1 - 0.1 * j } end end
  local P = { GRAVITY = 0, MARGIN = 0.03, DEEP = deep }
  local behind = { { a = { -0.3, -0.3, 0.8 }, b = { 0.4, -0.3, 0.8 }, r = 0.1 } }   -- a forearm behind the cloth
  local through = { { a = { -0.3, 0.02, 0.8 }, b = { 0.4, 0.02, 0.8 }, r = 0.1 } }  -- ... snaps forward past it
  for _ = 1, 10 do Skirt.step(S, A, T, 1 / 60, P, behind) end
  Skirt.step(S, A, T, 1 / 60, P, through)
  return S.chains[1].p[2][2]
end
local y_naive, y_deep = deep_case(0), deep_case(1)
assert(y_naive < 0.02 - 0.1, 'without DEEP the arm goes through: cloth left behind it (cloth y ' .. y_naive .. ')')
assert(y_deep > 0.02 + 0.1, 'with DEEP the cloth stays in front of the arm (cloth y ' .. y_deep .. ')')
local function deep_chain(deep)
  local c = Chain.new({ 0.1, 0.1, 0.1 })
  local a = { 0, 0, 1 }
  local tg = { { 0, 0, 0.9 }, { 0, 0, 0.8 }, { 0, 0, 0.7 } }
  local P = { GRAVITY = 0, MARGIN = 0.03, DEEP = deep, BOUNCE = 0 }
  for _ = 1, 10 do Chain.step(c, a, tg, 1 / 60, P, { { a = { -0.3, -0.3, 0.8 }, b = { 0.3, -0.3, 0.8 }, r = 0.1 } }) end
  Chain.step(c, a, tg, 1 / 60, P, { { a = { -0.3, 0.02, 0.8 }, b = { 0.3, 0.02, 0.8 }, r = 0.1 } })
  return c.p[2][2]
end
assert(deep_chain(0) < 0.02 and deep_chain(1) > 0.02, 'single chain DEEP: ' .. deep_chain(0) .. ' / ' .. deep_chain(1))
out[#out + 1] = string.format('arm snapping through: cloth ends at y %+.2f without DEEP (pushed through), %+.2f with (stays in front)', y_naive, y_deep)

-- 6. MAX_SPEED: a ragdoll whip (anchor shaking 0.3 m at 8 Hz, 15 m/s) cannot fling the cloth
local function whip(maxs)
  local c = Chain.new({ 0.15, 0.15, 0.15 })
  local P = { MAX_SPEED = maxs, DAMPING = 0.05, SHAPE = 0 }
  local worst, prev = 0, nil
  for f = 0, 120 do
    local t = f / 60
    local a = { 0.3 * math.sin(2 * math.pi * 8 * t), 0, 1 }
    Chain.step(c, a, { { a[1], 0, 0.85 }, { a[1], 0, 0.7 }, { a[1], 0, 0.55 } }, 1 / 60, P)
    local tip = c.out[3]
    local rel = { tip[1] - a[1], tip[2] - a[2], tip[3] - a[3] }
    if prev then worst = math.max(worst, Chain.len(Chain.sub(rel, prev)) * 60) end
    prev = rel
  end
  return worst
end
local w_free, w_capped = whip(1e9), whip(4)
assert(w_capped < w_free * 0.8, string.format('the cap calms the whip: %.1f vs %.1f m/s', w_capped, w_free))
out[#out + 1] = string.format('whip tip %.1f m/s capped vs %.1f free', w_capped, w_free)

-- 7. floor: hanging cloth lying on the ground (prone) stays above it
do
  local c = Chain.new({ 0.2, 0.2 })
  local a = { 0, 0, 0.3 }
  for _ = 1, 120 do Chain.step(c, a, { { 0, 0, 0.1 }, { 0, 0, -0.1 } }, 1 / 60, nil, nil, 0.0) end
  assert(c.out[2][3] >= -1e-9, 'chain stays above the floor: ' .. c.out[2][3])
  local S = Skirt.new(3, { 0.2, 0.2 })
  local A = { { 0, 0, 0.3 }, { 0.1, 0, 0.3 }, { 0.2, 0, 0.3 } }
  local T = {}; for k = 1, 3 do T[k] = { { A[k][1], 0, 0.1 }, { A[k][1], 0, -0.1 } } end
  local lo = 1
  for _ = 1, 120 do Skirt.step(S, A, T, 1 / 60, nil, nil, 0.0); for k = 1, 3 do lo = math.min(lo, S.out[k][2][3]) end end
  assert(lo >= -1e-9, 'skirt stays above the floor: ' .. lo)
end
out[#out + 1] = 'floor holds'

-- 8. a whole outfit against the full body, frame by frame: arms swinging through a cape, all fine
do
  local S = Skirt.new(5, { 0.15, 0.15, 0.15, 0.15 }); S.open = true
  local anchors = {}
  for c = 1, 5 do local a = math.pi * (c - 1) / 4; anchors[c] = { 0.16 * math.cos(a), 0.12 + 0.03 * math.sin(a), 1.45 } end
  local P = { MARGIN = 0.03, ARM_COLLIDE = 1 }
  local own = Body.fit(Body.capsules(J), anchors, P)
  local worst = 0
  for f = 0, 180 do
    local t = f / 60
    local Jf = {}; for k, v in pairs(J) do Jf[k] = v end
    local sw = 0.5 * math.sin(2 * math.pi * t)                        -- arms swing back and forth
    Jf.l_hand = { -0.45, 0.14 + 0.4 * sw, 1.0 }; Jf.r_hand = { 0.45, 0.14 - 0.4 * sw, 1.0 }
    Jf.l_elbow = { -0.35, 0.05 + 0.2 * sw, 1.2 }; Jf.r_elbow = { 0.35, 0.05 - 0.2 * sw, 1.2 }
    local cp = Body.apply(Body.capsules(Jf, P), own)
    local T = {}
    for c = 1, 5 do T[c] = {}; for j = 1, 4 do T[c][j] = { anchors[c][1], anchors[c][2] + 0.02 * j, 1.45 - 0.15 * j } end end
    Skirt.step(S, anchors, T, 1 / 60, P, cp, Body.floor(Jf, P))
    for c = 1, 5 do for j = 1, 4 do
      local p = S.out[c][j]
      for _, k in ipairs(cp) do worst = math.max(worst, k.r - Body.dist_to(k, p)) end
      assert(p[1] == p[1], 'no NaN')
    end end
  end
  assert(worst < 0.01, 'cape joints stay outside the body (worst ' .. worst .. ' m inside)')
  out[#out + 1] = string.format('cape vs swinging arms: worst %.1f mm inside', worst * 1000)
end

print('test_body: ok (' .. table.concat(out, '; ') .. ')')
