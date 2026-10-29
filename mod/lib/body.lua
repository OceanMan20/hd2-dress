-- Body colliders (step 3): capsules for the whole Helldiver, not just the legs. Pure math, no engine
-- calls: the game, the Blender preview and the tests all build them here from joint positions.
--
--   local caps = Body.capsules(J, P)        -- J[name] = {x,y,z} world joint positions (missing = skipped)
--   local floor = Body.floor(J, P)          -- height cloth may not sink below (prone, dive)
--   local fit = Body.fit(caps, anchors, P)  -- once per part: thinner colliders where its top sits on the body
--   local mine = Body.apply(caps, fit)      -- each frame: the colliders that part uses
-- Capsules: { a = {x,y,z}, b = {x,y,z}, r = metres, name = 'l_thigh' ... }. Sizes are a little inside
-- the armour surface (MARGIN, the cloth thickness, is added on top by the solvers).
-- Why "ignore": a part hangs from a body bone, so its top sits ON that body part (a skirt's waist on
-- the pelvis, a cape on the back, hair on the head). Without this, the collider would push the top
-- of the cloth outward and puff it up. A collider counts as the part's own when any of the part's
-- anchors (fixed tops) is inside it; that relation does not change with the pose because the anchors
-- move with their bone. Every other collider still applies (the cape still hits the legs and arms).
-- Only inside the collider itself counts, not inside its clearance (MARGIN): a cape pinned to the
-- back of the chest must keep the torso collider, or it falls into the back.
local Body = {}

Body.DEFAULTS = { THIGH_R = 0.085, SHIN_R = 0.06, THIGH_START = 0.1,
                  PELVIS_R = 0.11, TORSO_R = 0.13, UPPERARM_R = 0.055, FOREARM_R = 0.045, HEAD_R = 0.11, HEAD_UP = 0.09,
                  BODY_COLLIDE = 1,   -- 0 = legs only (the 0.6 behaviour)
                  BODY_FIT = 0,       -- 1 = thinner colliders instead of dropping them (Body.fit)
                  ARM_COLLIDE = 0,    -- 1 = the arms push the cloth too. Off (2026-10-17): holstering a
                                      -- weapon swings a hand fast through the skirt and the arm tubes
                                      -- threw the cloth around; arms passing through cloth is the lesser evil
                  FLOOR = 0.01,       -- the floor sits this far below the body's lowest surface (see SURFACE)
                  FLOOR_RISE = 0.5 }  -- m/s: how fast the floor may follow the body UP (see Body.ground)

-- the joints a Helldiver skeleton needs for the colliders (the runtime looks these up by name)
Body.JOINTS = { 'hips', 'spine1', 'neck', 'head', 'l_shoulder', 'l_elbow', 'l_hand', 'r_shoulder', 'r_elbow', 'r_hand',
                'l_thigh', 'l_knee', 'l_foot', 'r_thigh', 'r_knee', 'r_foot' }

local function g(P, k) local v = P and P[k]; if v == nil then v = Body.DEFAULTS[k] end; return v end
local function lerp(a, b, t) return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t } end

function Body.capsules(J, P)
  local caps = {}
  local function cap(name, a, b, r) if a and b and r > 0 then caps[#caps + 1] = { a = a, b = b, r = r, name = name } end end
  local s = g(P, 'THIGH_START')
  for _, side in ipairs({ 'l', 'r' }) do
    local t, k, f = J[side .. '_thigh'], J[side .. '_knee'], J[side .. '_foot']
    if t and k then cap(side .. '_thigh', lerp(t, k, s), k, g(P, 'THIGH_R')) end
    cap(side .. '_shin', k, f, g(P, 'SHIN_R'))
  end
  if (g(P, 'BODY_COLLIDE') or 1) > 0 then
    cap('pelvis', J.l_thigh, J.r_thigh, g(P, 'PELVIS_R'))
    cap('torso', J.spine1 or J.hips, J.neck, g(P, 'TORSO_R'))
    if (g(P, 'ARM_COLLIDE') or 0) ~= 0 then
      for _, side in ipairs({ 'l', 'r' }) do
        cap(side .. '_upperarm', J[side .. '_shoulder'], J[side .. '_elbow'], g(P, 'UPPERARM_R'))
        cap(side .. '_forearm', J[side .. '_elbow'], J[side .. '_hand'], g(P, 'FOREARM_R'))
      end
    end
    local h, n = J.head, J.neck
    if h and n then   -- a sphere a little above the head joint (the joint is the top of the neck)
      local d = { h[1] - n[1], h[2] - n[2], h[3] - n[3] }
      local l = math.sqrt(d[1] ^ 2 + d[2] ^ 2 + d[3] ^ 2)
      local up = l > 1e-6 and { d[1] / l, d[2] / l, d[3] / l } or { 0, 0, 1 }
      local c = { h[1] + up[1] * g(P, 'HEAD_UP'), h[2] + up[2] * g(P, 'HEAD_UP'), h[3] + up[3] * g(P, 'HEAD_UP') }
      cap('head', c, c, g(P, 'HEAD_R'))
    end
  end
  return caps
end

-- how far below each joint the body's surface is when lying on that part (the ankle stands ~9 cm
-- up, a lying chest ~12 cm): the floor follows the lowest SURFACE, so it is right standing and prone
Body.SURFACE = { l_foot = 0.09, r_foot = 0.09, l_knee = 0.06, r_knee = 0.06, l_thigh = 0.09, r_thigh = 0.09, hips = 0.12,
                 spine1 = 0.12, neck = 0.08, head = 0.1, l_shoulder = 0.06, r_shoulder = 0.06, l_elbow = 0.05, r_elbow = 0.05,
                 l_hand = 0.04, r_hand = 0.04 }
function Body.floor(J, P)
  local lo
  for nm, p in pairs(J) do
    local off = Body.SURFACE[nm]
    if off and (not lo or p[3] - off < lo) then lo = p[3] - off end
  end
  return lo and (lo - g(P, 'FLOOR')) or nil
end

-- The floor over time: it drops at once with the body (down stairs, a fall) but rises only at
-- FLOOR_RISE m/s. In a jump or a dive the body is in the air and the cloth may hang below it; a floor
-- just under the lowest joint would hold it up like an invisible shelf, so the floor stays near where
-- the feet last stood. state = a table kept between frames (one per Helldiver).
function Body.ground(state, J, P, dt)
  local now = Body.floor(J, P)
  if not now then return state.z end
  if not state.z or now < state.z then state.z = now
  else state.z = math.min(now, state.z + g(P, 'FLOOR_RISE') * (dt or 0)) end
  return state.z
end

local function dist_to(cp, p)
  local ab = { cp.b[1] - cp.a[1], cp.b[2] - cp.a[2], cp.b[3] - cp.a[3] }
  local ll = ab[1] ^ 2 + ab[2] ^ 2 + ab[3] ^ 2
  local t = ll > 1e-12 and ((p[1] - cp.a[1]) * ab[1] + (p[2] - cp.a[2]) * ab[2] + (p[3] - cp.a[3]) * ab[3]) / ll or 0
  t = math.max(0, math.min(1, t))
  local q = { cp.a[1] + ab[1] * t, cp.a[2] + ab[2] * t, cp.a[3] + ab[3] * t }
  return math.sqrt((p[1] - q[1]) ^ 2 + (p[2] - q[2]) ^ 2 + (p[3] - q[3]) ^ 2)
end
Body.dist_to = dist_to

-- Which colliders a part keeps, and how big (2026-10-17, replaces "ignore"): a part hangs from a body
-- bone, so its top sits on that body part. A collider its top (anchors) would sit inside, counting the
-- cloth clearance (MARGIN), is made THINNER for that part, just enough that every anchor is outside it
-- plus the clearance: the waistband is not pushed out, and there is still a body core inside it.
-- Ignoring the whole collider left a band with no collider at all between the waistband and the
-- top of the pelvis / thighs: when the skirt rode up, it slid in there and over the top of a leg.
-- A collider is only dropped when the thinner one would be under FIT_MIN of its size.
-- BODY_FIT 0 (the default) keeps the 0.7/0.8 rule: drop a collider a part's top starts inside. The
-- thinner torso (BODY_FIT 1) made the skirt's top joints jolt (36 m/s) when the body bent to get up
-- in the stress run, and no simulated case ever slid into the band it covers: an option to try in
-- game, not the default.
-- Returns { [name] = radius (thinner) or false (dropped) }; colliders not listed stay as they are.
Body.FIT_MIN = 0.4
function Body.fit(caps, anchors, P)
  local margin = (P and P.MARGIN) or 0.03
  local thin = (P and P.BODY_FIT or 0) ~= 0
  local fit = {}
  for _, cp in ipairs(caps or {}) do
    local near
    for _, a in ipairs(anchors) do local d = dist_to(cp, a); if not near or d < near then near = d end end
    if near and not thin then
      if near < cp.r then fit[cp.name] = false end
    elseif near and near < cp.r + margin then
      local r = near - margin - 0.005
      fit[cp.name] = (r >= Body.FIT_MIN * cp.r) and r or false
    end
  end
  return fit
end

-- the colliders one part uses this frame: thinner where fit says so, dropped where false
function Body.apply(caps, fit)
  if not caps then return nil end
  if not fit or next(fit) == nil then return caps end
  local out = {}
  for _, cp in ipairs(caps) do
    local f = fit[cp.name]
    if f == nil then out[#out + 1] = cp
    elseif f then out[#out + 1] = { a = cp.a, b = cp.b, r = f, name = cp.name } end
  end
  return out
end

return Body
