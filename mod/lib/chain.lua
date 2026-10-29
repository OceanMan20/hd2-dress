-- Spring chain (milestone 2): pure math, no engine calls, so it runs the same in the game, in the
-- offline tests and in a future Blender preview.
--
-- A chain is a fixed root (the anchor, e.g. the top of a skirt bone) and n joints below it, each
-- at a fixed distance from the one above. Each joint is a verlet particle in world space:
--   * it keeps its own velocity (damped), so the chain lags behind the body and swings;
--   * gravity pulls it down;
--   * a spring pulls it toward where the body's pose alone would put it (the "rest target"),
--     so it settles back into shape;
--   * the segment lengths are restored exactly after every step (no stretching);
--   * a cone limit keeps each segment within MAX_ANGLE of its rest direction (no flipping).
-- Fixed physics timestep with the anchor and targets interpolated, so the feel does not change
-- with the frame rate (aero runs ~17 fps, bongo far more).
--
--   local C = Chain.new({ 0.2, 0.2 })                       -- segment lengths, metres
--   Chain.step(C, anchor, targets, dt, P)                    -- anchor {x,y,z}; targets[i] {x,y,z}
--   C.out[i]                                                 -- joint i to draw this frame (world)
-- P (all tunable): GRAVITY (m/s^2), DAMPING (velocity lost per 1/60 s, 0..1), STIFFNESS (share of
-- the way to the rest target per 1/60 s, 0..1), FOLLOW (0..1: share of the anchor's own movement
-- the joints take along directly; 1 = rigid), MAX_ANGLE (deg), SUBSTEP_HZ, TELEPORT (m: a jump
-- larger than this resets the chain to its targets), COLLIDE_ITER (passes of length + collision
-- per substep), MARGIN (m, cloth thickness added to every collider).
-- Colliders (optional, milestone 4): caps = { {a = {x,y,z}, b = {x,y,z}, r = metres}, ... } capsules
-- (e.g. thighs and shins) at this frame's pose; they are interpolated across substeps like the anchor.
-- A joint inside one is pushed out to its surface. Only directions are turned into bone rotations,
-- so the small length error collision can leave does not show.
local Chain = {}

local function sub(a, b) return { a[1] - b[1], a[2] - b[2], a[3] - b[3] } end
local function add(a, b) return { a[1] + b[1], a[2] + b[2], a[3] + b[3] } end
local function mul(a, s) return { a[1] * s, a[2] * s, a[3] * s } end
local function len(a) return math.sqrt(a[1] * a[1] + a[2] * a[2] + a[3] * a[3]) end
local function lerp(a, b, t) return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t } end
local function dot(a, b) return a[1] * b[1] + a[2] * b[2] + a[3] * b[3] end
local function copy(a) return { a[1], a[2], a[3] } end
Chain.sub, Chain.add, Chain.mul, Chain.len, Chain.dot, Chain.lerp, Chain.copy = sub, add, mul, len, dot, lerp, copy

-- SHAPE (0..1 per 1/60 s): pull toward the rest shape that adds NO speed (cloth holds its cut but
-- never springs back and bounces; 2026-10-15 user: "it's cloth, it has no spring, it just drapes").
-- SHAPE_HEM: the same at the last joint (blended down the chain; nil = SHAPE). STIFFNESS is the old
-- springy pull (adds speed). BOUNCE (0..1): share of a collision push that becomes speed; 0 = the leg
-- just moves the cloth aside (no flinging). The chain defaults keep the original behaviour.
-- DAMPING acts on the speed RELATIVE TO THE BODY (the chain's anchor), AIR on the speed over the
-- ground. Damping over the ground (as before 0.5.3) is a gale at running speed: in game the skirt
-- streamed out horizontally behind a running Helldiver and the front panels were pressed back
-- into the legs while walking (2026-10-16). REL_DAMP 1 = relative (default), 0 = the old way.
-- Safeties (step 3, see skirt.lua): DEEP, MAX_SPEED (m/s relative to the anchor) and an optional
-- floor height (Chain.step's last argument).
Chain.DEFAULTS = { GRAVITY = 9.81, DAMPING = 0.08, STIFFNESS = 0.03, SHAPE = 0, BOUNCE = 1, FOLLOW = 0.0, MAX_ANGLE = 110,
                   REL_DAMP = 1, AIR = 0.01, DEEP = 1, MAX_SPEED = 12, MAX_ANGLE_PUSHED = 120,
                   SUBSTEP_HZ = 60, TELEPORT = 1.5, COLLIDE_ITER = 3, MARGIN = 0.01 }

function Chain.new(lengths)
  return { L = lengths, n = #lengths, p = nil, pp = nil, out = nil, anchor = nil, targets = nil, acc = 0, resets = 0 }
end

function Chain.reset(c, anchor, targets)
  c.p, c.pp = {}, {}
  for i = 1, c.n do c.p[i] = copy(targets[i]); c.pp[i] = copy(targets[i]) end
  c.anchor, c.frame_anchor = copy(anchor), copy(anchor)
  c.targets, c.frame_targets = {}, {}
  for i = 1, c.n do c.targets[i] = copy(targets[i]); c.frame_targets[i] = copy(targets[i]) end
  c.resets = c.resets + 1; c.pcaps = nil
end

-- keep segment i inside a cone of max_deg around its rest direction, then at its exact length
-- c.touch[i] > 0 (a body part pushed joint i lately): the cone opens to max_push degrees, so cloth
-- can fold over a raised knee or a sitting thigh (2026-10-16 stress run: at 60 deg the limit pulled
-- the hem back into the thigh of a sitting Helldiver)
local function constrain(c, anchor, targets, max_deg, max_push)
  local cosfree = math.cos(math.rad(max_deg))
  local cospush = math.cos(math.rad(math.max(max_deg, max_push or max_deg)))
  local touch = c.touch
  local prev, prev_t = anchor, anchor
  for i = 1, c.n do
    local cosmax = (touch and (touch[i] or 0) > 0) and cospush or cosfree
    local d = sub(c.p[i], prev)
    local l = len(d)
    local rest = sub(targets[i], prev_t)
    local rl = len(rest)
    local rdir = rl > 1e-9 and mul(rest, 1 / rl) or { 0, 0, -1 }
    local dir = l > 1e-9 and mul(d, 1 / l) or rdir
    local cs = dot(dir, rdir)
    if cs < cosmax then
      -- rotate dir toward rdir until it sits on the cone
      local perp = sub(dir, mul(rdir, cs))
      local pl = len(perp)
      if pl > 1e-9 then
        perp = mul(perp, 1 / pl)
        local s = math.sqrt(math.max(0, 1 - cosmax * cosmax))
        dir = add(mul(rdir, cosmax), mul(perp, s))
      else
        dir = rdir
      end
    end
    c.p[i] = add(prev, mul(dir, c.L[i]))
    prev, prev_t = c.p[i], targets[i]
  end
end

-- push every joint out of every capsule (closest point on the segment, out to radius + margin)
local function collide(c, caps, margin, bounce, pcaps, deep)
  if not caps then return 0 end
  local hits = 0
  bounce = bounce or 1
  deep = deep or 0
  if c.hit then for i = 1, c.n do c.hit[i] = false end end
  if pcaps and #pcaps ~= #caps then pcaps = nil end
  for i = 1, c.n do
    local p = c.p[i]
    for ci, cp in ipairs(caps) do
      local pcp = pcaps and pcaps[ci]
      local ab = sub(cp.b, cp.a)
      local ll = dot(ab, ab)
      local t = ll > 1e-12 and math.max(0, math.min(1, dot(sub(p, cp.a), ab) / ll)) or 0
      local q = add(cp.a, mul(ab, t))
      local d = sub(p, q)
      local dl = len(d)
      local r = cp.r + margin
      if dl < r then
        local n = dl > 1e-9 and mul(d, 1 / dl) or { 0, -1, 0 }
        if pcp and deep > 0 and c.pp and not c.no_pp then   -- passed through in one step: out where it came from (skirt.lua)
          local o = c.pp[i]
          local pab = sub(pcp.b, pcp.a); local pl = dot(pab, pab)
          local oq = add(pcp.a, mul(pab, pl > 1e-12 and math.max(0, math.min(1, dot(sub(o, pcp.a), pab) / pl)) or 0))
          local e = sub(o, oq); local el = len(e)
          if el > r and dot(e, d) < 0 then n = mul(e, 1 / el) end
        end
        local np = add(q, mul(n, r)); hits = hits + 1
        c.hit = c.hit or {}; c.hit[i] = true
        if bounce < 1 and c.pp and not c.no_pp then   -- inelastic: drop the inward speed, the push adds BOUNCE of itself
          local v = sub(p, c.pp[i]); local vn = dot(v, n)
          if vn < 0 then v = sub(v, mul(n, vn)) end
          c.pp[i] = sub(sub(np, v), mul(sub(np, p), bounce))
        end
        p = np
      end
    end
    c.p[i] = p
  end
  return hits
end
local function lerp_caps(c0, c1, t)
  if not c1 then return nil end
  if not c0 or #c0 ~= #c1 then return c1 end
  local out = {}
  for i = 1, #c1 do out[i] = { a = lerp(c0[i].a, c1[i].a, t), b = lerp(c0[i].b, c1[i].b, t), r = c1[i].r } end
  return out
end
local function floor_limit(c, fl)
  if not fl then return end
  for i = 1, c.n do
    local p = c.p[i]
    if p[3] < fl then
      p[3] = fl
      local q = c.pp and c.pp[i]
      if q and not c.no_pp then q[3] = fl; q[1] = (q[1] + p[1]) * 0.5; q[2] = (q[2] + p[2]) * 0.5 end
    end
  end
end
local function solve(c, a, tg, caps, g, pcaps)
  if not caps then constrain(c, a, tg, g('MAX_ANGLE')); floor_limit(c, c.floor); return 0 end
  local hits = 0
  for _ = 1, math.max(1, g('COLLIDE_ITER')) do
    constrain(c, a, tg, g('MAX_ANGLE'), g('MAX_ANGLE_PUSHED'))
    hits = collide(c, caps, g('MARGIN'), g('BOUNCE'), pcaps, g('DEEP'))
    if hits > 0 then c.touch = c.touch or {}; for i = 1, c.n do if c.hit and c.hit[i] then c.touch[i] = 20 end end end
    floor_limit(c, c.floor)
    if hits == 0 then break end
  end
  return hits
end

-- Fixed timestep (1/SUBSTEP_HZ, accumulated across frames): the same motion gives the same sway at
-- 17 fps and at 144 fps. Each substep sees the anchor and targets interpolated to its own time.
-- c.out = the joints to draw this frame: the simulated ones, re-attached to this frame's anchor
-- (so a frame without a substep still follows the body, without touching the simulation state).
-- The step size may change (fast steps while a shock wave passes, blast.lua): velocity is stored as
-- p - pp per step, so it is rescaled to the new step, or the cloth would slow down / speed up.
function Chain.rate(c, h)
  if c.h and c.h ~= h and c.p and c.pp then
    local r = h / c.h
    for i = 1, c.n do
      local p, q = c.p[i], c.pp[i]
      c.pp[i] = { p[1] - (p[1] - q[1]) * r, p[2] - (p[2] - q[2]) * r, p[3] - (p[3] - q[3]) * r }
    end
  end
  c.h = h
end

function Chain.step(c, anchor, targets, dt, P, caps, floor_z)
  P = P or Chain.DEFAULTS
  c.floor = floor_z
  local D = Chain.DEFAULTS
  local function g(k) local v = P[k]; if v == nil then v = D[k] end; return v end
  if not c.p or len(sub(anchor, c.anchor)) > g('TELEPORT') then
    Chain.reset(c, anchor, targets); c.acc = 0; c.frame_caps = caps
    c.h = 1 / g('SUBSTEP_HZ')
    solve(c, anchor, targets, caps, g)
    c.pp = {}; for i = 1, c.n do c.pp[i] = copy(c.p[i]) end
    c.out = {}; for i = 1, c.n do c.out[i] = copy(c.p[i]) end
    return
  end
  dt = math.max(0, math.min(dt or 0, 0.25))
  local h = 1 / g('SUBSTEP_HZ')
  Chain.rate(c, h)
  local pull = 1 - (1 - math.min(1, math.max(0, g('STIFFNESS')))) ^ (h * 60)
  -- per joint: the chain settings, then the author's per-bone values (c.over[i] = { DAMPING, SHAPE,
  -- GRAVITY }: absolute values for bone i), then the player's multipliers (MUL_*, 1 = as made)
  local over = c.over or {}
  local mul_d, mul_s = g('MUL_DAMPING') or 1, g('MUL_SHAPE') or 1
  local keep, shape, gravj = {}, {}, {}
  for i = 1, c.n do
    local t = c.n > 1 and (i - 1) / (c.n - 1) or 0
    local o = over[i] or {}
    keep[i] = (1 - math.min(1, math.max(0, (o.DAMPING or g('DAMPING')) * mul_d))) ^ (h * 60)
    local sv = (o.SHAPE or (g('SHAPE') * (1 - t) + (g('SHAPE_HEM') or g('SHAPE')) * t)) * mul_s
    shape[i] = 1 - (1 - math.min(1, math.max(0, sv))) ^ (h * 60)
    gravj[i] = { 0, 0, -(o.GRAVITY or g('GRAVITY')) * h * h }
  end
  local follow = math.min(1, math.max(0, g('FOLLOW')))
  local rel = math.min(1, math.max(0, g('REL_DAMP') or 1))
  local airkeep = (1 - math.min(1, math.max(0, g('AIR') or 0))) ^ (h * 60)
  local vmax = (g('MAX_SPEED') or 12) * h
  local acc0 = c.acc or 0
  local a0, t0 = c.anchor, c.targets      -- where the last substep left them
  local k = 1
  while dt > 0 and acc0 + dt >= k * h - 1e-12 do
    -- time of this substep inside the frame, as a fraction of the frame
    local frac = math.min(1, (k * h - acc0) / dt)
    local a = lerp(c.frame_anchor or a0, anchor, frac)
    local tg = {}
    for i = 1, c.n do tg[i] = lerp((c.frame_targets or t0)[i], targets[i], frac) end
    local carry = mul(sub(a, a0), follow)
    local vb = mul(sub(a, a0), rel * (1 - follow))   -- the body's own motion this step not already carried rigidly (not damped away)
    for i = 1, c.n do
      local p, pp = c.p[i], c.pp[i]
      local v = add(vb, mul(sub(sub(p, pp), vb), keep[i]))
      v = mul(v, airkeep)
      local vr = sub(v, vb); local vl = len(vr)
      if vl > vmax then v = add(vb, mul(vr, vmax / vl)) end   -- MAX_SPEED safety
      local np = add(add(add(p, v), gravj[i]), carry)
      np = add(np, mul(sub(tg[i], np), pull))
      local sd = mul(sub(tg[i], np), shape[i])      -- shape memory: moves the joint, adds no speed
      np = add(np, sd)
      c.pp[i] = add(add(p, carry), sd)              -- carried motion is not velocity either
      c.p[i] = np
    end
    local cnow = lerp_caps(c.frame_caps, caps, frac)
    if c.touch then for i = 1, c.n do if (c.touch[i] or 0) > 0 then c.touch[i] = c.touch[i] - 1 end end end
    c.hits = solve(c, a, tg, cnow, g, c.pcaps)
    c.pcaps = cnow
    a0, t0 = a, tg
    k = k + 1
  end
  c.acc = (acc0 + dt) - (k - 1) * h
  c.anchor, c.targets = copy(a0), t0
  c.frame_anchor = copy(anchor)
  c.frame_targets = {}; for i = 1, c.n do c.frame_targets[i] = copy(targets[i]) end
  c.frame_caps = caps
  -- what to draw: the simulated joints, re-attached to this frame's anchor
  local save = c.p
  c.p = {}; for i = 1, c.n do c.p[i] = copy(save[i]) end
  c.no_pp = true; solve(c, anchor, targets, caps, g); c.no_pp = false
  c.out, c.p = c.p, save
end

-- Tail feel (2026-10-15 user: "barely moves, slithers along, barely waving, like a real reptile
-- tail"): its own settings, TAIL_<key> in the settings file overriding the cloth ones.
Chain.TAIL_DEFAULTS = { DAMPING = 0.35, SHAPE = 0.35, SHAPE_HEM = 0.15, STIFFNESS = 0, BOUNCE = 0, FOLLOW = 0.5,
                        GRAVITY = 0.5, WAVE = 0.04, WAVE_HZ = 1.2, WAVE_LAG = 0.25, WAVE_SPEED = 1.5 }
function Chain.group_params(P, prefix, defaults)
  local out = {}
  for k, v in pairs(P) do out[k] = v end
  for k, v in pairs(defaults) do out[k] = v end
  for k, v in pairs(P) do
    local base = type(k) == 'string' and k:match('^' .. prefix .. '_(.+)$')
    if base then out[base] = v end
  end
  return out
end
-- The slither: a sideways wave travelling down the tail, scaled by walking speed (none standing
-- still). side = the body's right (unit vector), t = time (s), speed = body speed (m/s).
function Chain.wave(targets, side, t, speed, P)
  local amp = (P.WAVE or 0) * math.min(1, (speed or 0) / math.max(0.01, P.WAVE_SPEED or 1.5))
  if amp <= 0 then return targets end
  local out, n = {}, #targets
  for i = 1, n do
    local s = amp * (i / n) * math.sin(2 * math.pi * ((P.WAVE_HZ or 1) * t - (P.WAVE_LAG or 0.25) * i))
    out[i] = add(targets[i], mul(side, s))
  end
  return out
end
Chain.constrain, Chain.lerp_caps, Chain.collide = constrain, lerp_caps, collide   -- used by skirt.lua
return Chain
