-- Skirt solver (milestones 3 + 4): a ring of spring chains that behaves as ONE cloth surface.
-- Pure math, no engine calls (runs in the game, the tests and sim/run_sim.lua alike).
--
-- chain.lua alone only kept the JOINTS out of the legs; a leg still passed through the cloth between
-- them (2026-10-15 sim video: the thigh came out through the front panel). Here:
--   * every chain is integrated like chain.lua (verlet, gravity, damping, spring to rest shape);
--   * neighbouring chains are tied at each level: they may bunch up but not spread further apart
--     than the rest spacing x (1 + STRETCH), so no gap opens for a leg to slip into;
--   * collision tests the SURFACE, not just joints: per panel (between two chains and two levels)
--     a grid of SAMPLES x SAMPLES points; a point inside a leg capsule is pushed out by moving the
--     4 joints that span it (weighted, the standard position-based way); anchors never move;
--   * all of it is iterated ITER times per substep, collision last.
--
--   local S = Skirt.new(n_chains, seg_lengths)       -- seg_lengths: { l1, l2, ... } (same for all)
--   Skirt.step(S, anchors, targets, dt, P, caps)     -- anchors[c] {x,y,z}; targets[c][j]; caps as chain.lua
--   S.out[c][j]                                      -- joint j of chain c to draw (world)
-- P adds to chain.lua's keys: STRETCH (0.. share the hem may widen), SAMPLES (per panel side),
-- ITER (solver passes per substep).
-- Step 3: S.open = true makes an open SHEET (cape, hair curtain, coat tail, front panel): the
-- strips are a row, the last one is not joined back to the first. Safeties for dive / prone /
-- ragdoll: DEEP (1 = on: cloth a body part passed through in one step, e.g. a ragdoll or a snap
-- into prone, goes back out on the side it came from instead of being shoved through), MAX_SPEED (m/s,
-- relative to the body: a ragdoll whip cannot fling the cloth), and an optional floor height
-- (Skirt.step's last argument): no joint sinks below it.
-- Loading: this file returns function(Chain) -> Skirt (no globals, works embedded in the addon).
return function(Chain)
local sub, add, mul, len, dot, lerp, copy = Chain.sub, Chain.add, Chain.mul, Chain.len, Chain.dot, Chain.lerp, Chain.copy
local Skirt = {}
-- cloth defaults (override chain.lua's): heavy and calm, shape held without spring, legs push it
-- aside without flinging it (BOUNCE 0)
-- Anti-hula-hoop (2026-10-15 user: "it acts like a hula hoop, hoops of bones instead of vertical
-- lines; it should flex and compress to swish with the legs"):
--   TIE (0..1): how hard neighbouring strips are held together (1 = old rigid hoop; the surface
--     collision already stops legs slipping through gaps, so it can be loose);
--   DAMPING_HEM: damping at the hem (DAMPING is the waist), WEIGHT_TOP: how much heavier the waist
--     is than the hem (a push moves the hem WEIGHT_TOP times further than the waist);
--   LEG_FOLLOW (0..1): strips near a leg swing with that thigh (Skirt.leg_follow), LEG_EMA (s): how
--     fast the follow forgets a held pose (a sustained crouch is left to collision).
-- 0.5.3 (first in-game tuning, bongo): heavier, body-relative damping, firmer shape, 60 deg limit
Skirt.DEFAULTS = { STRETCH = 0.3, TIE = 0.3, SAMPLES = 4, ITER = 3, DAMPING = 0.4, DAMPING_HEM = 0.25, STIFFNESS = 0,
                   SHAPE = 0.12, SHAPE_HEM = 0.07, BOUNCE = 0, WEIGHT_TOP = 3, LEG_FOLLOW = 0.6, LEG_EMA = 1.5,
                   MAX_ANGLE = 60, REL_DAMP = 1, AIR = 0.01, DEEP = 1, MAX_SPEED = 12, MAX_ANGLE_PUSHED = 120 }

function Skirt.new(nc, lengths)
  local S = { nc = nc, ns = #lengths, L = lengths, chains = {}, acc = 0, resets = 0 }
  for c = 1, nc do S.chains[c] = Chain.new(lengths) end
  return S
end

local function getter(P)
  local D1, D2 = Chain.DEFAULTS, Skirt.DEFAULTS
  return function(k) local v = P and P[k]; if v == nil then v = D2[k] end; if v == nil then v = D1[k] end; return v end
end

-- neighbour pairs: a ring joins the last strip back to the first, an open sheet does not
local function npairs(S) if S.open then return S.nc - 1 end return S.nc end

-- joint position, level 0 = the anchor (fixed)
local function J(S, A, c, j) if j == 0 then return A[c] end return S.chains[c].p[j] end

-- neighbours may not spread wider than at rest (x 1 + stretch); they may bunch freely
local function ring_limit(S, A, T, stretch, tie)
  tie = tie or 1
  if tie <= 0 then return end
  for j = 1, S.ns do
    for c = 1, npairs(S) do
      local c2 = c % S.nc + 1
      local p, q = S.chains[c].p[j], S.chains[c2].p[j]
      local rest = len(sub(T[c2][j], T[c][j])) * (1 + stretch)
      local d = sub(q, p); local l = len(d)
      if l > rest and l > 1e-9 then
        local corr = mul(d, (l - rest) / l * 0.5 * tie)
        S.chains[c].p[j] = add(p, corr); S.chains[c2].p[j] = sub(q, corr)
      end
    end
  end
end

-- push the cloth surface out of every capsule; returns the number of sample points that were inside.
-- Scalar maths (no tables in the inner loop: the game's GC), and a cheap bounds test per
-- panel/capsule pair first, so panels nowhere near a leg cost almost nothing.
local function collide_surface(S, A, caps, pcaps, margin, samples, bounce, deep)
  local hits = 0
  local im = S.invm or {}                 -- [strip][level]: 1 / weight (the waist is heavier, moves less)
  local keepv = (not S.no_pp) and (1 - (bounce or 0)) or 0   -- share of a push also applied to the previous position
  local ns = math.max(1, samples)
  local ch = S.chains
  deep = deep or 0
  if pcaps and #pcaps ~= #caps then pcaps = nil end
  for c = 1, npairs(S) do
    local c2 = c % S.nc + 1
    for j = 1, S.ns do
      local p00 = j == 1 and A[c] or ch[c].p[j - 1]
      local p10 = j == 1 and A[c2] or ch[c2].p[j - 1]
      local p01, p11 = ch[c].p[j], ch[c2].p[j]
      local q00 = j > 1 and ch[c].pp[j - 1] or nil
      local q10 = j > 1 and ch[c2].pp[j - 1] or nil
      local q01, q11 = ch[c].pp[j], ch[c2].pp[j]
      local m00, m10 = j > 1, j > 1                    -- the anchors (level 0) never move
      local function iw(cc, jj) local r = im[cc]; return (r and r[jj]) or 1 end
      local i00, i10, i01, i11 = iw(c, j - 1), iw(c2, j - 1), iw(c, j), iw(c2, j)   -- inverse weights of the 4 corners
      for ci, cp in ipairs(caps) do
        local pcp = pcaps and pcaps[ci]                  -- the same collider one substep ago (DEEP)
        local r = cp.r + margin
        local ax, ay, az, bx, by, bz = cp.a[1], cp.a[2], cp.a[3], cp.b[1], cp.b[2], cp.b[3]
        -- bounds: panel box vs capsule box, both padded by r
        local lox = math.min(p00[1], p10[1], p01[1], p11[1]); local hix = math.max(p00[1], p10[1], p01[1], p11[1])
        local loy = math.min(p00[2], p10[2], p01[2], p11[2]); local hiy = math.max(p00[2], p10[2], p01[2], p11[2])
        local loz = math.min(p00[3], p10[3], p01[3], p11[3]); local hiz = math.max(p00[3], p10[3], p01[3], p11[3])
        if not (math.max(ax, bx) + r < lox or math.min(ax, bx) - r > hix or math.max(ay, by) + r < loy
                or math.min(ay, by) - r > hiy or math.max(az, bz) + r < loz or math.min(az, bz) - r > hiz) then
          local abx, aby, abz = bx - ax, by - ay, bz - az
          local ll = abx * abx + aby * aby + abz * abz
          for si = 0, ns do
            for sj = 1, ns do
              local u, v = si / ns, sj / ns
              local w00, w10, w01, w11 = (1 - u) * (1 - v), u * (1 - v), (1 - u) * v, u * v
              local x = p00[1] * w00 + p10[1] * w10 + p01[1] * w01 + p11[1] * w11
              local y = p00[2] * w00 + p10[2] * w10 + p01[2] * w01 + p11[2] * w11
              local z = p00[3] * w00 + p10[3] * w10 + p01[3] * w01 + p11[3] * w11
              local t = ll > 1e-12 and ((x - ax) * abx + (y - ay) * aby + (z - az) * abz) / ll or 0
              if t < 0 then t = 0 elseif t > 1 then t = 1 end
              local dx, dy, dz = x - (ax + abx * t), y - (ay + aby * t), z - (az + abz * t)
              local dl = math.sqrt(dx * dx + dy * dy + dz * dz)
              if dl < r then
                hits = hits + 1
                local nx, ny, nz
                if dl > 1e-9 then nx, ny, nz = dx / dl, dy / dl, dz / dl else nx, ny, nz = 0, -1, 0 end
                if deep > 0 and pcp and keepv > 0 then
                  -- passed through in one step (ragdoll, a snap into prone or a dive): back out on the
                  -- side it came from, i.e. where this sample was against this collider a moment ago
                  local o00 = q00 or p00; local o10 = q10 or p10; local o01 = q01 or p01; local o11 = q11 or p11
                  local X = o00[1] * w00 + o10[1] * w10 + o01[1] * w01 + o11[1] * w11
                  local Y = o00[2] * w00 + o10[2] * w10 + o01[2] * w01 + o11[2] * w11
                  local Z = o00[3] * w00 + o10[3] * w10 + o01[3] * w01 + o11[3] * w11
                  local pax, pay, paz = pcp.a[1], pcp.a[2], pcp.a[3]
                  local pbx, pby, pbz = pcp.b[1] - pax, pcp.b[2] - pay, pcp.b[3] - paz
                  local pl = pbx * pbx + pby * pby + pbz * pbz
                  local tt = pl > 1e-12 and ((X - pax) * pbx + (Y - pay) * pby + (Z - paz) * pbz) / pl or 0
                  if tt < 0 then tt = 0 elseif tt > 1 then tt = 1 end
                  local ex, ey, ez = X - (pax + pbx * tt), Y - (pay + pby * tt), Z - (paz + pbz * tt)
                  local el = math.sqrt(ex * ex + ey * ey + ez * ez)
                  if el > r and (ex * dx + ey * dy + ez * dz) < 0 then   -- was outside, is now past the middle
                    nx, ny, nz = ex / el, ey / el, ez / el
                    dl = dx * nx + dy * ny + dz * nz                     -- push = r - dl reaches that side's surface
                  end
                end
                local push = r - dl
                local ww = w01 * w01 * i01 + w11 * w11 * i11 + (m00 and w00 * w00 * i00 or 0) + (m10 and w10 * w10 * i10 or 0)
                if ww > 1e-9 then
                  -- inelastic contact: the joint loses the part of its speed going INTO the leg,
                  -- keeps its sliding part, and the push itself adds speed only by BOUNCE
                  -- (keeping the inward speed made cloth tunnel through the knee, 2026-10-15)
                  local function mv(pt, qt, wk, iw)
                    local f = push * wk * iw / ww
                    local vx, vy, vz = 0, 0, 0
                    if qt then vx, vy, vz = pt[1] - qt[1], pt[2] - qt[2], pt[3] - qt[3] end
                    pt[1] = pt[1] + nx * f; pt[2] = pt[2] + ny * f; pt[3] = pt[3] + nz * f
                    if keepv > 0 and qt then
                      local vn = vx * nx + vy * ny + vz * nz
                      if vn < 0 then vx, vy, vz = vx - nx * vn, vy - ny * vn, vz - nz * vn end
                      local b = 1 - keepv                                   -- = BOUNCE
                      qt[1] = pt[1] - vx - nx * f * b; qt[2] = pt[2] - vy - ny * f * b; qt[3] = pt[3] - vz - nz * f * b
                    end
                  end
                  -- these joints are being pushed: their swing limit opens (Chain.constrain, MAX_ANGLE_PUSHED)
                  if not S.no_pp then
                    local t1, t2 = ch[c].touch, ch[c2].touch
                    if not t1 then t1 = {}; ch[c].touch = t1 end
                    if not t2 then t2 = {}; ch[c2].touch = t2 end
                    t1[j] = 20; t2[j] = 20
                    if j > 1 then t1[j - 1] = 20; t2[j - 1] = 20 end
                  end
                  if m00 and w00 > 0 then mv(p00, q00, w00, i00) end
                  if m10 and w10 > 0 then mv(p10, q10, w10, i10) end
                  if w01 > 0 then mv(p01, q01, w01, i01) end
                  if w11 > 0 then mv(p11, q11, w11, i11) end
                end
              end
            end
          end
        end
      end
    end
  end
  return hits
end

local function floor_limit(S, fl)
  if not fl then return end
  for c = 1, S.nc do
    local ch = S.chains[c]
    for j = 1, S.ns do
      local p = ch.p[j]
      if p[3] < fl then
        p[3] = fl
        local q = ch.pp[j]
        if q and not S.no_pp then q[3] = fl; q[1] = (q[1] + p[1]) * 0.5; q[2] = (q[2] + p[2]) * 0.5 end   -- lands, with friction
      end
    end
  end
end

local function solve(S, A, T, caps, g, pcaps)
  local hits = 0
  for _ = 1, math.max(1, g('ITER')) do
    for c = 1, S.nc do Chain.constrain(S.chains[c], A[c], T[c], g('MAX_ANGLE'), g('MAX_ANGLE_PUSHED')) end
    ring_limit(S, A, T, g('STRETCH'), g('TIE'))
    if caps then
      if npairs(S) >= 1 then
        hits = collide_surface(S, A, caps, pcaps, g('MARGIN'), g('SAMPLES'), g('BOUNCE'), g('DEEP'))
      else   -- a sheet of one strip has no panels: collide its joints like a single chain
        S.chains[1].no_pp = S.no_pp
        hits = Chain.collide(S.chains[1], caps, g('MARGIN'), g('BOUNCE'), pcaps, g('DEEP'))
        S.chains[1].no_pp = false
      end
    end
    floor_limit(S, S.floor)
  end
  return hits
end

local function reset(S, A, T)
  for c = 1, S.nc do Chain.reset(S.chains[c], A[c], T[c]) end
  S.A, S.T, S.fA, S.fT = {}, {}, {}, {}
  for c = 1, S.nc do
    S.A[c], S.fA[c] = copy(A[c]), copy(A[c])
    S.T[c], S.fT[c] = {}, {}
    for j = 1, S.ns do S.T[c][j] = copy(T[c][j]); S.fT[c][j] = copy(T[c][j]) end
  end
  S.acc = 0; S.resets = S.resets + 1; S.pcaps = nil
end

local function snapshot(S)
  S.out = {}
  for c = 1, S.nc do S.out[c] = {}; for j = 1, S.ns do S.out[c][j] = copy(S.chains[c].p[j]) end end
end

function Skirt.step(S, A, T, dt, P, caps, floor_z)
  local g = getter(P)
  S.floor = floor_z
  local jump = 0
  if S.A then for c = 1, S.nc do jump = math.max(jump, len(sub(A[c], S.A[c]))) end end
  if not S.A or jump > g('TELEPORT') then
    reset(S, A, T); S.fcaps = caps
    for c = 1, S.nc do S.chains[c].h = 1 / g('SUBSTEP_HZ') end
    if caps then solve(S, A, T, caps, g) else floor_limit(S, S.floor) end
    for c = 1, S.nc do local ch = S.chains[c]; for j = 1, S.ns do ch.pp[j] = copy(ch.p[j]) end end
    snapshot(S); return
  end
  dt = math.max(0, math.min(dt or 0, 0.25))
  local h = 1 / g('SUBSTEP_HZ')
  for c = 1, S.nc do Chain.rate(S.chains[c], h) end
  -- per strip and level: the waist->hem blend of the settings, then the author's per-bone values
  -- (S.over[c][j] = { DAMPING, SHAPE, WEIGHT, GRAVITY }: absolute values for that one bone), then the
  -- player's multipliers (P.MUL_DAMPING etc., 1 = as the author made it)
  local over = S.over or {}
  local mul_d, mul_s, mul_w = g('MUL_DAMPING') or 1, g('MUL_SHAPE') or 1, g('MUL_WEIGHT') or 1
  local keepcj, shapecj, gravcj = {}, {}, {}
  S.invm = {}
  for c = 1, S.nc do
    keepcj[c], shapecj[c], gravcj[c], S.invm[c] = {}, {}, {}, {}
    for j = 1, S.ns do
      local t = S.ns > 1 and (j - 1) / (S.ns - 1) or 0
      local o = over[c] and over[c][j] or {}
      local dmp = (o.DAMPING or (g('DAMPING') * (1 - t) + (g('DAMPING_HEM') or g('DAMPING')) * t)) * mul_d
      keepcj[c][j] = (1 - math.min(1, math.max(0, dmp))) ^ (h * 60)
      local sv = (o.SHAPE or (g('SHAPE') * (1 - t) + (g('SHAPE_HEM') or g('SHAPE')) * t)) * mul_s
      shapecj[c][j] = 1 - (1 - math.min(1, math.max(0, sv))) ^ (h * 60)
      local wt = (o.WEIGHT or ((g('WEIGHT_TOP') or 1) * (1 - t) + 1 * t)) * mul_w
      S.invm[c][j] = 1 / math.max(0.05, wt)
      gravcj[c][j] = { 0, 0, -(o.GRAVITY or g('GRAVITY')) * h * h }
    end
  end
  local pull = 1 - (1 - math.min(1, math.max(0, g('STIFFNESS')))) ^ (h * 60)
  local follow = math.min(1, math.max(0, g('FOLLOW')))
  local rel = math.min(1, math.max(0, g('REL_DAMP') or 1))
  local airkeep = (1 - math.min(1, math.max(0, g('AIR') or 0))) ^ (h * 60)
  local vmax = (g('MAX_SPEED') or 12) * h
  local acc0, k = S.acc, 1
  local a0 = S.A
  while dt > 0 and acc0 + dt >= k * h - 1e-12 do
    local frac = math.min(1, (k * h - acc0) / dt)
    local As, Ts = {}, {}
    for c = 1, S.nc do
      As[c] = lerp(S.fA[c], A[c], frac)
      Ts[c] = {}; for j = 1, S.ns do Ts[c][j] = lerp(S.fT[c][j], T[c][j], frac) end
      local ch = S.chains[c]
      local carry = mul(sub(As[c], a0[c]), follow)
      local vb = mul(sub(As[c], a0[c]), rel * (1 - follow))   -- the body's own speed, minus what FOLLOW carries rigidly
      for j = 1, S.ns do
        local p, pp = ch.p[j], ch.pp[j]
        local v = mul(add(vb, mul(sub(sub(p, pp), vb), keepcj[c][j])), airkeep)   -- damp relative to the body; AIR over the ground
        local vr = sub(v, vb); local vl = len(vr)
        if vl > vmax then v = add(vb, mul(vr, vmax / vl)) end                       -- MAX_SPEED safety
        local np = add(add(add(p, v), gravcj[c][j]), carry)
        np = add(np, mul(sub(Ts[c][j], np), pull))
        local sd = mul(sub(Ts[c][j], np), shapecj[c][j])    -- shape memory: no speed, no bounce
        np = add(np, sd)
        ch.pp[j] = add(add(p, carry), sd); ch.p[j] = np
      end
    end
    local cnow = Chain.lerp_caps(S.fcaps, caps, frac)
    for c = 1, S.nc do                                    -- the pushed-joint marks fade (20 substeps = 1/3 s)
      local t_ = S.chains[c].touch
      if t_ then for j = 1, S.ns do if (t_[j] or 0) > 0 then t_[j] = t_[j] - 1 end end end
    end
    S.hits = solve(S, As, Ts, cnow, g, S.pcaps)
    S.pcaps = cnow
    a0 = As
    k = k + 1
  end
  S.acc = (acc0 + dt) - (k - 1) * h
  S.A = {}; for c = 1, S.nc do S.A[c] = copy(a0[c]) end
  S.fA, S.fT = {}, {}
  for c = 1, S.nc do S.fA[c] = copy(A[c]); S.fT[c] = {}; for j = 1, S.ns do S.fT[c][j] = copy(T[c][j]) end end
  S.fcaps = caps
  -- what to draw: re-attached to this frame's anchors, without touching the simulation state
  local save = {}
  for c = 1, S.nc do save[c] = {}; for j = 1, S.ns do save[c][j] = copy(S.chains[c].p[j]) end end
  S.no_pp = true; solve(S, A, T, caps, g); S.no_pp = false
  snapshot(S)
  for c = 1, S.nc do for j = 1, S.ns do S.chains[c].p[j] = save[c][j] end end
end

-- Strips near a leg swing with that thigh: the rest targets are turned about the hip joint by the
-- thigh's swing away from its recent average direction (no rest pose needed, works the same in the
-- game and the simulator). legs = { {hip = {x,y,z}, knee = {x,y,z}}, ... } (world), Rh = hips world
-- rotation {x,y,z,w}. Returns new targets; S remembers each leg's average and each strip's weights.
local function qmulq(a, b)
  return { a[4] * b[1] + a[1] * b[4] + a[2] * b[3] - a[3] * b[2], a[4] * b[2] - a[1] * b[3] + a[2] * b[4] + a[3] * b[1],
           a[4] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[4], a[4] * b[4] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3] }
end
local function qconjq(q) return { -q[1], -q[2], -q[3], q[4] } end
local function qrotq(q, v)
  local x, y, z, w = q[1], q[2], q[3], q[4]
  local tx, ty, tz = 2 * (y * v[3] - z * v[2]), 2 * (z * v[1] - x * v[3]), 2 * (x * v[2] - y * v[1])
  return { v[1] + w * tx + (y * tz - z * ty), v[2] + w * ty + (z * tx - x * tz), v[3] + w * tz + (x * ty - y * tx) }
end
local function nrm(v) local l = len(v); if l < 1e-9 then return nil end return mul(v, 1 / l) end
local function between(u, v, frac)   -- rotation from u to v, scaled to frac of its angle
  local d = math.max(-1, math.min(1, dot(u, v)))
  local ax = { u[2] * v[3] - u[3] * v[2], u[3] * v[1] - u[1] * v[3], u[1] * v[2] - u[2] * v[1] }
  local al = len(ax)
  if al < 1e-9 then return { 0, 0, 0, 1 } end
  local ang = math.atan2(al, d) * frac
  local s = math.sin(ang / 2) / al
  return { ax[1] * s, ax[2] * s, ax[3] * s, math.cos(ang / 2) }
end
function Skirt.leg_follow(S, A, T, legs, Rh, dt, P)
  local g = getter(P)
  local amount = g('LEG_FOLLOW') or 0
  if amount <= 0 or not legs or #legs == 0 or not Rh then return T end
  S.leg_avg = S.leg_avg or {}
  if not S.leg_w then   -- each strip's share of each leg, from how near its anchor is to that hip
    S.leg_w = {}
    for c = 1, S.nc do
      local d2 = {}
      local tot = 0
      for l, L in ipairs(legs) do local dd = sub(A[c], L.hip); d2[l] = 1 / math.max(1e-4, dot(dd, dd)) ^ 1; tot = tot + d2[l] end
      S.leg_w[c] = {}
      for l = 1, #legs do S.leg_w[c][l] = d2[l] / tot end
    end
  end
  local a = 1 - math.exp(-(dt or 0) / math.max(0.05, g('LEG_EMA') or 1.5))
  local rots = {}
  for l, L in ipairs(legs) do
    local now = nrm(qrotq(qconjq(Rh), sub(L.knee, L.hip)))     -- thigh direction in the hips' own frame
    if now then
      local avg = S.leg_avg[l] or now
      avg = nrm(add(mul(avg, 1 - a), mul(now, a))) or now
      S.leg_avg[l] = avg
      rots[l] = { avg = avg, now = now }
    end
  end
  local out = {}
  for c = 1, S.nc do
    out[c] = {}
    for j = 1, S.ns do out[c][j] = T[c][j] end
    for l, L in ipairs(legs) do
      local r = rots[l]
      local w = amount * (S.leg_w[c][l] or 0)
      if r and w > 0.001 then
        local ql = between(r.avg, r.now, w)
        local qw = qmulq(qmulq(Rh, ql), qconjq(Rh))               -- the swing, in the world
        for j = 1, S.ns do out[c][j] = add(L.hip, qrotq(qw, sub(out[c][j], L.hip))) end
      end
    end
  end
  return out
end

return Skirt
end
