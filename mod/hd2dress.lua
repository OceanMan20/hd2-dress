-- HD2-Addon: mods/oceanman/hd2dress
-- HD2 Dress v0.6.0: generic dress physics (any registered dress) + gating test (passed 2026-10-15: the engine leaves armour-only bones alone) and
-- milestone 2, one spring chain: the back-left test flap swings and settles under physics.
--
-- Needs the gate armour patch (tools/build_gate_patch.py): B-01 Tactical hip armour with three
-- added bones and flaps behind the hips:
--   dress_test_a (back-left flap, upper half; we rotate it), dress_test_b (lower half, child of a,
--   never written), dress_ctrl (back-right flap, never written: the control).
-- Wear any B-01 Tactical variation. Solo / private lobby (it picks the B-01 hip piece nearest to
-- the Helldiver it finds; other players in B-01 would make that a guess).
--
-- HOME cycles the test:
--   off -> 1 hold @render (write before the draw, every frame, then update the unit)
--       -> 2 hold @update (write in the update, every frame)
--       -> 3 once (write once, then only read: does it stay?)
--       -> 4 swing @render (back and forth, so it is obvious our write drives it)
--       -> 5 SPRING CHAIN (milestone 2: the two test bones become a 2-joint spring chain) -> off
-- Spring tuning is live: edit HD2Dress_settings.txt beside the log (KEY=value lines; written with
-- the defaults on first start), saved changes apply within 2 s, no restart.
-- Freeze diagnosis: HD2Dress_heartbeat.txt beside the log is rewritten at every stage of every frame
-- (tools/freeze_watch.py reads it from outside: if the game hangs, it names the last stage).
-- Every 2 s the log says, for the frames since: kept (the bone still had our rotation when we came
-- back), reset (back at its rest rotation), other (something else wrote it), the measured flap
-- angle from vertical, and whether the control stayed on the pelvis.
-- Log: %LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\HD2Dress.log, and every frame in
-- HD2Dress_trace.csv beside it (bone positions in the pelvis frame, angle vs the control flap).
--
-- Engine safety (hd2-vr lessons): units only from World.units_by_resource (never a world scan),
-- every engine call in pcall, units from an old world are dropped without calling into them.

local sr = rawget(_G, 'stingray')
if not sr or rawget(_G, 'OceanHD2DressLoaded') then return end
OceanHD2DressLoaded = true

---------------------------------------------------------------- settings (tune freely)
local CFG = {
  KEY = 'home',                 -- cycles the test (falls back to KEY_ALT if the name is unknown)
  KEY_ALT = nil,
  KEY_DRESS = 'end',            -- dress physics on/off
  ANGLE_DEG = 45,               -- hold modes: how far the flap is turned
  AXIS = { 1, 0, 0 },           -- turn axis in the bone's own frame (x first; try {0,0,1} if it only twists)
  SWING_DEG = 50,               -- swing mode: amplitude
  SWING_HZ = 0.5,               -- swing mode: cycles per second
  LOG_EVERY = 2,                -- seconds between log lines
  HIP_UNITS = { '0387a158d04848f4', '2f66b9373cb58485' },   -- B-01 Hip_Armor_Stocky, Hip_Armor_Slim
  AVATAR = '4d1c334d294dfa97',  -- the Helldiver model (every Helldiver)
  BONE_TEST = 'dress_test_a', BONE_CHILD = 'dress_test_b', BONE_CTRL = 'dress_ctrl', BONE_HIPS = 'hips',
}
local VERSION = '0.8.4'
-- spring chain (milestone 2); every value is live-tunable through HD2Dress_settings.txt
local PHYS = { GRAVITY = 9.81, DAMPING = 0.4, STIFFNESS = 0, SHAPE = 0.12, SHAPE_HEM = 0.07, BOUNCE = 0, FOLLOW = 0.0, MAX_ANGLE = 60,
               REL_DAMP = 1, AIR = 0.01,
               SUBSTEP_HZ = 60, TELEPORT = 1.5, TIP_LEN = 0.2 }
local Chain = (function()
--@include lib/chain.lua
end)()
local Skirt = (function()
--@include lib/skirt.lua
end)()(Chain)
local Body = (function()
--@include lib/body.lua
end)()
local Blast = (function()
--@include lib/blast.lua
end)()
-- dress physics (generic): armour units listed in HD2DRESS_REGISTRY (filled by each dress mod's
-- registration addon, made by tools/dress_autorig.py) with bones dress_cNN_bK; legs from the avatar
for k, v in pairs({ STRETCH = 0.3, TIE = 0.3, DAMPING_HEM = 0.25, WEIGHT_TOP = 3, LEG_FOLLOW = 0.6, LEG_EMA = 1.5,
                    SAMPLES = 4, ITER = 3, MARGIN = 0.03, THIGH_R = 0.085, SHIN_R = 0.06, THIGH_START = 0.1, DRESS = 1,
                    DEEP = 1, MAX_SPEED = 12, MAX_ANGLE_PUSHED = 120, LAYER_GAP = 0.02 }) do PHYS[k] = v end
for k, v in pairs(Body.DEFAULTS) do if PHYS[k] == nil then PHYS[k] = v end end   -- the body colliders (step 3)
for k, v in pairs(Blast.DEFAULTS) do if PHYS[k] == nil then PHYS[k] = v end end  -- shock waves from explosions
PHYS.MAX_DRESSES = 4                                                             -- Helldivers simulated at once, newest first
PHYS.SLEEP = 1                                                                   -- a dress whose Helldiver lies still sleeps (no cost)
for k, v in pairs(Chain.TAIL_DEFAULTS) do PHYS['TAIL_' .. k] = v end   -- the tail's own feel
PHYS.MUL_DAMPING, PHYS.MUL_SHAPE, PHYS.MUL_WEIGHT = 1, 1, 1           -- player multipliers on the author's values
local A, W, U, KB = sr.Application, sr.World, sr.Unit, sr.Keyboard
local Q, V3 = sr.Quaternion, sr.Vector3
local clock = 0

---------------------------------------------------------------- log
local log_path
do
  local dir = os.getenv('LOCALAPPDATA')
  if dir then
    log_path = dir .. '\\CowboyBingus\\Helldivers2\\Logs\\HD2Dress.log'
    local f = io.open(log_path, 'w')
    if f then f:write('HD2 Dress ' .. VERSION .. '\n'); f:close() end
  end
end
local function log(...)
  if not log_path then return end
  local parts = { string.format('[%7.1f]', clock) }
  for i = 1, select('#', ...) do parts[#parts + 1] = tostring((select(i, ...))) end
  local f = io.open(log_path, 'a')
  if f then f:write(table.concat(parts, ' '), '\n'); f:close() end
end
-- per-frame trace (CSV) next to the log: positions in the pelvis frame + angles, for plotting
local trace, trace_n = nil, 0
if log_path then
  trace = io.open((log_path:gsub('HD2Dress%.log$', 'HD2Dress_trace.csv')), 'w')
  if trace then trace:write('t,mode,target_deg,vs_control_deg,vs_body_deg,a_x,a_y,a_z,b_x,b_y,b_z,ctrl_x,ctrl_y,ctrl_z,hips_wx,hips_wy,hips_wz,tip_x,tip_y,tip_z,b_vs_a_deg\n') end
end

-- heartbeat: one fixed-size line, rewritten in place at every stage of every frame. If the game
-- hangs, it holds the last stage reached (read from outside by tools/freeze_watch.py).
local beat, beat_frame = nil, 0
if log_path then beat = io.open((log_path:gsub('HD2Dress%.log$', 'HD2Dress_heartbeat.txt')), 'w') end
local MODE_NOW = 0
local function hb(stage)
  if not beat then return end
  local line = string.format('frame %d t %.2f mode %d stage %s', beat_frame, clock, MODE_NOW, stage)
  line = line .. string.rep(' ', math.max(0, 95 - #line)) .. '\n'
  beat:seek('set', 0); beat:write(line); beat:flush()
end

-- live settings: KEY=value lines; unknown keys are ignored, a bad value keeps the old one
local settings_path = log_path and (log_path:gsub('HD2Dress%.log$', 'HD2Dress_settings.txt'))
local SETTINGS_KEYS = { 'DRESS', 'GRAVITY', 'DAMPING', 'REL_DAMP', 'AIR', 'SHAPE', 'SHAPE_HEM', 'BOUNCE', 'STIFFNESS', 'FOLLOW', 'MAX_ANGLE', 'SUBSTEP_HZ', 'TELEPORT',
  'DAMPING_HEM', 'WEIGHT_TOP', 'TIE', 'STRETCH', 'LEG_FOLLOW', 'LEG_EMA', 'SAMPLES', 'ITER', 'MARGIN', 'THIGH_R', 'SHIN_R', 'THIGH_START',
  'MUL_DAMPING', 'MUL_SHAPE', 'MUL_WEIGHT', 'TAIL_DAMPING', 'TAIL_SHAPE', 'TAIL_SHAPE_HEM', 'TAIL_FOLLOW', 'TAIL_GRAVITY', 'TAIL_WAVE', 'TAIL_WAVE_HZ', 'TAIL_WAVE_LAG', 'TAIL_WAVE_SPEED', 'TIP_LEN',
  'BODY_COLLIDE', 'PELVIS_R', 'TORSO_R', 'UPPERARM_R', 'FOREARM_R', 'HEAD_R', 'HEAD_UP', 'FLOOR', 'FLOOR_RISE', 'DEEP', 'MAX_SPEED', 'MAX_ANGLE_PUSHED', 'LAYER_GAP', 'MAX_DRESSES', 'BODY_FIT', 'ARM_COLLIDE',
  'BLAST', 'BLAST_SCALE', 'BLAST_SPEED', 'BLAST_LIFT', 'BLAST_MAX_DV', 'BLAST_PUSH', 'BLAST_SUBSTEPS', 'BLAST_MAX_SPEED', 'BLAST_RESPONSE', 'SLEEP' }
local SETTINGS_HELP = {
  GRAVITY = 'm/s^2 pulling the flap down', DAMPING = 'share of speed lost per 1/60 s (0..1): higher = calmer, stops swinging sooner',
  STIFFNESS = 'share of the way back to its rest shape per 1/60 s (0..1): higher = stiffer fabric',
  FOLLOW = 'share of the body movement taken along rigidly (0..1): 1 = no sway at all',
  MAX_ANGLE = 'degrees a segment may swing away from its rest direction', SUBSTEP_HZ = 'physics steps per second (fixed)',
  TELEPORT = 'metres: a bigger jump in one frame resets the chain (respawn, mission load)', TIP_LEN = 'gate test flap: metres, length of the lower segment',
  DRESS = '1 = dress physics on, 0 = off (also the END key)', STRETCH = 'how much wider than at rest the hem may spread (0..1); it may always bunch',
  SAMPLES = 'collision points per panel side (more = fewer clips, more cost)', ITER = 'solver passes per physics step',
  MARGIN = 'metres of clearance kept between cloth and body',
  BODY_COLLIDE = '1 = cloth collides with the whole body (pelvis, torso, arms, head); 0 = legs only',
  PELVIS_R = 'pelvis collider radius (m)', TORSO_R = 'torso collider radius (m)', UPPERARM_R = 'upper arm collider radius (m)',
  FOREARM_R = 'forearm collider radius (m)', HEAD_R = 'head collider radius (m)', HEAD_UP = 'head collider: metres above the head joint',
  FLOOR = 'cloth may not sink lower than this many metres below the body\'s lowest surface (prone, dive)',
  FLOOR_RISE = 'm/s the floor may follow the body up (low = in a jump the cloth may still hang below the body)',
  DEEP = '1 = cloth a body part passes through in one frame (ragdoll, prone) goes back to its own side; 0 = off',
  MAX_SPEED = 'm/s: fastest the cloth may move against the body (calms ragdoll whips)',
  MAX_ANGLE_PUSHED = 'degrees cloth may swing while a body part pushes it (lets it fold over a raised knee; MAX_ANGLE is the free limit)',
  ARM_COLLIDE = '1 = the arms push the cloth too (off: holstering a weapon threw the skirt around; arms may pass through cloth instead)',
  BODY_FIT = '1 = a part whose top sits inside a body collider gets a thinner one instead of none (try for cloth sliding in at the hips; can jolt the waist when bending)',
  MAX_DRESSES = 'how many Helldivers wearing a dress get physics at once (newest first: you after a respawn, then teammates; corpses drop off)',
  BLAST = '1 = explosions send a shock wave through the cloth (reads the game\'s explosion queue; switches itself off on an unknown game build)',
  BLAST_SCALE = 'shock wave strength x this (0 = no waves); the reach grows with its square root',
  BLAST_SPEED = 'm/s the shock front travels (real air: 340; lower = a far blast arrives visibly later)',
  BLAST_LIFT = 'how much the push also lifts the cloth (0 = straight away from the blast)',
  BLAST_MAX_DV = 'm/s: the strongest push one blast may give a joint (in all, over BLAST_PUSH seconds)',
  BLAST_PUSH = 'seconds a shock wave keeps pushing the cloth once it arrives (longer = it billows instead of snapping)',
  BLAST_SUBSTEPS = 'while a wave passes, the cloth runs this many times more physics steps (1 = off): smaller steps, so legs still block fast cloth',
  BLAST_MAX_SPEED = 'm/s: MAX_SPEED while a wave passes (with the faster steps)',
  BLAST_RESPONSE = 'how strongly this cloth reacts to shock waves (normally set by the dress author; BLAST_SCALE is yours for all dresses)',
  SLEEP = '1 = a dress whose Helldiver has not moved for 3 s sleeps (a corpse costs nothing); a body move or a wave wakes it',
  LAYER_GAP = 'metres each outer layer is kept further out than the one inside it', THIGH_R = 'thigh collider radius (m)', SHIN_R = 'shin collider radius (m)',
  THIGH_START = 'share of the thigh (from the hip) that does not collide: its top sits inside the waistband',
  SHAPE = 'holds the cut at the waist (0..1 per 1/60 s); pulls back to shape WITHOUT spring, so no bounce',
  SHAPE_HEM = 'the same at the hem (blended down the skirt): lower = the hem drapes more freely',
  BOUNCE = 'share of a leg push that flings the cloth (0 = it is just moved aside)',
  STIFFNESS = 'old springy pull (adds bounce); keep 0 for cloth',
  DAMPING_HEM = 'damping at the hem (DAMPING is the waist): lower = the hem swishes more freely',
  REL_DAMP = '1 = damping works on the speed relative to the body (cloth moves with you); 0 = relative to the ground (a gale when running)',
  AIR = 'air drag on the speed over the ground (0..1 per 1/60 s): makes it trail a little when running',
  WEIGHT_TOP = 'how much heavier the waist is than the hem: a push moves the hem this many times further',
  TIE = 'how hard neighbouring strips are held together (1 = rigid hoop, 0 = free strips)',
  LEG_FOLLOW = 'how much strips near a leg swing with that thigh (0..1)', LEG_EMA = 'seconds: how fast leg-follow forgets a held pose',
  MUL_DAMPING = 'player multiplier on the damping (yours or the dress author\'s values), 1 = as made',
  MUL_SHAPE = 'player multiplier on shape memory, 1 = as made', MUL_WEIGHT = 'player multiplier on heaviness, 1 = as made',
  TAIL_DAMPING = 'tail: share of speed lost per 1/60 s', TAIL_SHAPE = 'tail: how firmly it keeps its shape at the root',
  TAIL_SHAPE_HEM = 'tail: the same at the tip', TAIL_FOLLOW = 'tail: share of the body movement it takes along rigidly',
  TAIL_GRAVITY = 'tail: how much it sags (m/s^2; a reptile tail carries itself)', TAIL_WAVE = 'tail: slither, sideways wave at the tip (m) at full speed',
  TAIL_WAVE_HZ = 'tail: slither waves per second', TAIL_WAVE_LAG = 'tail: how far the wave lags per bone (cycles)',
  TAIL_WAVE_SPEED = 'tail: walking speed (m/s) at which the slither is full size',
}
local settings_text = nil
local function load_settings(first)
  if not settings_path then return end
  local f = io.open(settings_path, 'r')
  if not f then
    local w = io.open(settings_path, 'w')
    if w then
      w:write('# HD2 Dress live settings: edit and save, applies within 2 s. Spring chain (HOME mode 5).\n')
      for _, k in ipairs(SETTINGS_KEYS) do w:write(string.format('%s=%s    # %s\n', k, tostring(PHYS[k]), SETTINGS_HELP[k])) end
      w:close()
    end
    return
  end
  local text = f:read('*a') or ''; f:close()
  if text == settings_text then return end
  settings_text = text
  local changed = {}
  for line in text:gmatch('[^\r\n]+') do
    local k, v = line:match('^%s*([%w_]+)%s*=%s*([-%d%.eE+]+)')
    v = tonumber(v)
    if k and v and PHYS[k] ~= nil and PHYS[k] ~= v then PHYS[k] = v; changed[#changed + 1] = k .. '=' .. v end
  end
  if #changed > 0 or first then
    local all = {}
    for _, k in ipairs(SETTINGS_KEYS) do all[#all + 1] = k .. '=' .. tostring(PHYS[k]) end
    return #changed > 0 and ('settings changed: ' .. table.concat(changed, ' ')) or ('settings: ' .. table.concat(all, ' '))
  end
end
local logged = {}
local function log_once(k, ...) if not logged[k] then logged[k] = true; log(...) end end

---------------------------------------------------------------- quaternion math (Lua side; the engine only converts)
local function qel(q) local ok, x, y, z, w = pcall(Q.to_elements, q); if ok and w then return { x, y, z, w } end end
local function qmake(t) local ok, q = pcall(Q.from_elements, t[1], t[2], t[3], t[4]); return ok and q or nil end
local function qmul(a, b)
  return { a[4] * b[1] + a[1] * b[4] + a[2] * b[3] - a[3] * b[2],
           a[4] * b[2] - a[1] * b[3] + a[2] * b[4] + a[3] * b[1],
           a[4] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[4],
           a[4] * b[4] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3] }
end
local function qaxis(ax, deg)
  local n = math.sqrt(ax[1] ^ 2 + ax[2] ^ 2 + ax[3] ^ 2); if n < 1e-9 then n = 1 end
  local h = math.rad(deg) / 2; local s = math.sin(h) / n
  return { ax[1] * s, ax[2] * s, ax[3] * s, math.cos(h) }
end
local function qclose(a, b)   -- same rotation (q and -q are equal)
  if not (a and b) then return false end
  local d = math.abs(a[1] * b[1] + a[2] * b[2] + a[3] * b[3] + a[4] * b[4])
  return d > 0.99999
end
local function qconj(q) return { -q[1], -q[2], -q[3], q[4] } end
local function qangle(a, b)   -- degrees between two rotations
  local d = math.abs(a[1] * b[1] + a[2] * b[2] + a[3] * b[3] + a[4] * b[4])
  return math.deg(2 * math.acos(math.min(1, d)))
end
local function qrotv(q, v)    -- rotate vector v {x,y,z} by q
  local x, y, z, w = q[1], q[2], q[3], q[4]
  local tx, ty, tz = 2 * (y * v[3] - z * v[2]), 2 * (z * v[1] - x * v[3]), 2 * (x * v[2] - y * v[1])
  return { v[1] + w * tx + (y * tz - z * ty), v[2] + w * ty + (z * tx - x * tz), v[3] + w * tz + (x * ty - y * tx) }
end

---------------------------------------------------------------- finding the units (never a world scan)
local Id = sr.IdString64 or rawget(_G, 'IdString64')
local function by_res(world, hex)
  if not (world and Id and Id.from_hex and type(W.units_by_resource) == 'function') then return {} end
  local okn, name = pcall(Id.from_hex, hex)
  if not okn then return {} end
  local ok, list = pcall(W.units_by_resource, world, name)
  return (ok and type(list) == 'table') and list or {}
end
local function wpos(u, i)
  local ok, p = pcall(U.world_position, u, i)
  if ok and p then return { p.x, p.y, p.z } end
end
local function dist2(a, b) return (a[1] - b[1]) ^ 2 + (a[2] - b[2]) ^ 2 + (a[3] - b[3]) ^ 2 end

local S = { mode = 0, world = nil, unit = nil, nodes = nil, rest = nil, next_find = 0 }
local MODES = { 'off', 'hold @render', 'hold @update', 'once (write one time, then only read)', 'swing @render', 'SPRING CHAIN' }

local function node(u, name)
  local okh, has = pcall(U.has_node, u, name)
  if not (okh and has) then return nil end
  local ok, n = pcall(U.node, u, name)
  return ok and n or nil
end

local function forget(why)
  if S.unit then log('[gate] armour piece forgotten (' .. why .. ')') end
  S.unit, S.nodes, S.rest, S.last_written, S.chain = nil, nil, nil, nil, nil
end

local function find(world)
  if clock < S.next_find and S.unit then return end
  S.next_find = clock + 2
  local avatars = by_res(world, CFG.AVATAR)
  local cands = {}
  for _, hex in ipairs(CFG.HIP_UNITS) do for _, u in ipairs(by_res(world, hex)) do cands[#cands + 1] = u end end
  if #cands == 0 then
    if S.unit then forget('no B-01 hip piece in this world') end
    log_once('nohip', '[gate] no B-01 Tactical hip piece in this world: wear B-01 Tactical (any variation)')
    return
  end
  local pick = cands[1]
  if #cands > 1 then
    local ap = avatars[1] and wpos(avatars[1], 1)
    local bd
    for _, u in ipairs(cands) do
      local p = ap and wpos(u, 1)
      if p then local d = dist2(p, ap); if not bd or d < bd then pick, bd = u, d end end
    end
    log_once('many' .. #cands, '[gate] ' .. #cands .. ' B-01 hip pieces here (' .. #avatars .. ' Helldivers): using the one nearest the first Helldiver; best solo')
  end
  if pick == S.unit then return end
  local n = { test = node(pick, CFG.BONE_TEST), child = node(pick, CFG.BONE_CHILD), ctrl = node(pick, CFG.BONE_CTRL), hips = node(pick, CFG.BONE_HIPS) }
  if not (n.test and n.child and n.ctrl and n.hips) then
    log_once('nonodes', '[gate] the B-01 hip piece has no dress_test bones: is the gate armour patch installed (and the Jaeger B-01 patch disabled)? nodes: '
      .. tostring(n.test) .. ' ' .. tostring(n.child) .. ' ' .. tostring(n.ctrl) .. ' ' .. tostring(n.hips))
    return
  end
  local okr, r = pcall(U.local_rotation, pick, n.test)
  local rest = okr and qel(r)
  if not rest then log_once('norest', '[gate] could not read the test bone rotation'); return end
  -- if a hold mode already turned this bone (F5-less re-find), rest would be wrong: only trust it when off
  S.unit, S.nodes, S.rest, S.last_written = pick, n, rest, nil
  local okc, rc = pcall(U.local_rotation, pick, n.ctrl)
  S.rest_ctrl = okc and qel(rc)
  -- chain geometry, measured once at rest: b's rest rotation (local to a), the direction a -> b in
  -- a's own frame (also used as b's tip direction: both bones were built pointing the same way)
  local okb, rb = pcall(U.local_rotation, pick, n.child)
  S.rest_b = okb and qel(rb)
  local oka, wa = pcall(U.world_rotation, pick, n.test)
  local pa, pb = wpos(pick, n.test), wpos(pick, n.child)
  wa = oka and qel(wa)
  if S.rest_b and wa and pa and pb then
    local d = { pb[1] - pa[1], pb[2] - pa[2], pb[3] - pa[3] }
    S.len_a = math.sqrt(d[1] ^ 2 + d[2] ^ 2 + d[3] ^ 2)
    local dl = qrotv(qconj(wa), d)
    S.dir_a = { dl[1] / S.len_a, dl[2] / S.len_a, dl[3] / S.len_a }
    S.dir_b = qrotv(qconj(S.rest_b), S.dir_a)   -- same world direction as a -> b at rest
  end
  S.chain = nil
  local h, c = wpos(pick, n.hips), wpos(pick, n.ctrl)
  S.ctrl_off = (h and c) and math.sqrt(dist2(h, c)) or nil
  log(string.format('[gate] armour piece found (%d candidates, %d Helldivers): nodes test %s child %s ctrl %s hips %s; rest rotation %.3f %.3f %.3f %.3f; ctrl %.3f m from hips',
    #cands, #avatars, tostring(n.test), tostring(n.child), tostring(n.ctrl), tostring(n.hips), rest[1], rest[2], rest[3], rest[4], S.ctrl_off or -1))
end

---------------------------------------------------------------- the test
local function new_stats(at) return { kept = 0, reset = 0, other = 0, writes = 0, fails = 0, frames = 0, angle = 0, angle_n = 0, ctrl_dev = 0,
  rel = 0, rel_n = 0, rel_min = 999, rel_max = -1, b = nil, log_at = at } end
local st = new_stats(0)
local function stats_reset() st = new_stats(clock + CFG.LOG_EVERY) end

local function target_angle()
  if S.mode == 4 then return CFG.SWING_DEG * math.sin(2 * math.pi * CFG.SWING_HZ * clock) end
  return CFG.ANGLE_DEG
end

local function write()
  local q = qmul(S.rest, qaxis(CFG.AXIS, target_angle()))
  local qq = qmake(q)
  if qq and pcall(U.set_local_rotation, S.unit, S.nodes.test, qq) then
    S.last_written = q; S.last_target = target_angle(); st.writes = st.writes + 1
    pcall(W.update_unit, S.world, S.unit)
  else
    st.fails = st.fails + 1
  end
end

-- read what the bone holds now (before this frame's write), and the measured flap angle
local function observe()
  local ok, r = pcall(U.local_rotation, S.unit, S.nodes.test)
  local now = ok and qel(r)
  if now and (S.mode == 0 or S.last_written) then   -- a writing mode's first frame has nothing to compare yet
    if S.last_written and qclose(now, S.last_written) then st.kept = st.kept + 1
    elseif qclose(now, S.rest) then st.reset = st.reset + 1
    else st.other = st.other + 1 end
  end
  -- flap angle from the piece's own up axis: direction test -> child (world), vs the root's down
  local a, b = wpos(S.unit, S.nodes.test), wpos(S.unit, S.nodes.child)
  local okr, rr = pcall(U.world_rotation, S.unit, 1)
  local root = okr and qel(rr)
  if a and b and root then
    local d = { b[1] - a[1], b[2] - a[2], b[3] - a[3] }
    local n = math.sqrt(d[1] ^ 2 + d[2] ^ 2 + d[3] ^ 2)
    local down = qrotv(root, { 0, 0, -1 })
    if n > 1e-4 then
      local c = (d[1] * down[1] + d[2] * down[2] + d[3] * down[3]) / n
      S.vs_body = math.deg(math.acos(math.max(-1, math.min(1, c))))
      st.angle = st.angle + S.vs_body; st.angle_n = st.angle_n + 1
    end
  end
  local h, c = wpos(S.unit, S.nodes.hips), wpos(S.unit, S.nodes.ctrl)
  if h and c and S.ctrl_off then st.ctrl_dev = math.max(st.ctrl_dev, math.abs(math.sqrt(dist2(h, c)) - S.ctrl_off)) end
  -- the clean angle: test bone vs the untouched control (same rest direction, same parent), in the
  -- WORLD, i.e. what the scene graph hands on to skinning
  local wa, wc, wh
  local ok1, r1 = pcall(U.world_rotation, S.unit, S.nodes.test); wa = ok1 and qel(r1)
  local ok2, r2 = pcall(U.world_rotation, S.unit, S.nodes.ctrl); wc = ok2 and qel(r2)
  local ok3, r3 = pcall(U.world_rotation, S.unit, S.nodes.hips); wh = ok3 and qel(r3)
  local rel = (wa and wc) and qangle(wa, wc) or nil
  if rel then
    st.rel = st.rel + rel; st.rel_n = st.rel_n + 1
    st.rel_min = math.min(st.rel_min, rel); st.rel_max = math.max(st.rel_max, rel)
  end
  -- positions in the pelvis frame (metres; stays put while you run unless the bone itself moves)
  local function loc(p)
    if not (p and h and wh) then return nil end
    return qrotv(qconj(wh), { p[1] - h[1], p[2] - h[2], p[3] - h[3] })
  end
  local la, lb, lc = loc(a), loc(b), loc(c)
  st.b = lb or st.b
  -- the chain tip (end of b, along b's own rest direction) and b's bend relative to a
  local tip, bend = nil, -1
  local okb, rb = pcall(U.world_rotation, S.unit, S.nodes.child)
  local wb = okb and qel(rb)
  if wb and b and S.dir_b then
    local d = qrotv(wb, S.dir_b)
    tip = loc({ b[1] + d[1] * PHYS.TIP_LEN, b[2] + d[2] * PHYS.TIP_LEN, b[3] + d[3] * PHYS.TIP_LEN })
    if wa then bend = qangle(qmul(wa, S.rest_b), wb) end
  end
  tip = tip or { 0, 0, 0 }
  st.frames = st.frames + 1
  if trace and la and lb and lc and h then
    trace:write(string.format('%.3f,%d,%.1f,%.2f,%.2f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.3f,%.3f,%.3f,%.4f,%.4f,%.4f,%.2f\n',
      clock, S.mode, (S.mode == 0 or S.mode == 5 or not S.last_target) and 0 or S.last_target, rel or -1, S.vs_body or -1,
      la[1], la[2], la[3], lb[1], lb[2], lb[3], lc[1], lc[2], lc[3], h[1], h[2], h[3], tip[1], tip[2], tip[3], bend))
    trace_n = trace_n + 1
  end
end

local function report()
  if clock < st.log_at then return end
  local okc, rc = pcall(U.local_rotation, S.unit, S.nodes.ctrl)
  local cq = okc and qel(rc)
  log(string.format('[gate] %s: %d frames, kept %d, reset %d, other %d (writes %d, fails %d); flap angle %.1f deg (target %.1f); control: %s, %.4f m max drift from the pelvis',
    MODES[S.mode + 1], st.frames, st.kept, st.reset, st.other, st.writes, st.fails,
    st.angle_n > 0 and st.angle / st.angle_n or -1, S.mode == 0 and 0 or target_angle(),
    (cq and S.rest_ctrl) and (qclose(cq, S.rest_ctrl) and 'rest rotation' or 'MOVED from rest') or '?', st.ctrl_dev))
  if st.rel_n > 0 then
    log(string.format('[gate]   vs the control flap (world): avg %.1f, min %.1f, max %.1f deg; flap tip (child bone) in the pelvis frame %s',
      st.rel / st.rel_n, st.rel_min, st.rel_max,
      st.b and string.format('%.3f %.3f %.3f', st.b[1], st.b[2], st.b[3]) or '?'))
  end
  if trace then trace:flush() end
  stats_reset()
end

---------------------------------------------------------------- milestone 2: spring chain
local function qbetween(u, v)   -- shortest rotation taking unit vector u to unit vector v
  local d = u[1] * v[1] + u[2] * v[2] + u[3] * v[3]
  if d < -0.999999 then   -- opposite: any perpendicular axis
    local ax = math.abs(u[1]) < 0.9 and { 0, -u[3], u[2] } or { -u[3], 0, u[1] }
    local n = math.sqrt(ax[1] ^ 2 + ax[2] ^ 2 + ax[3] ^ 2)
    return { ax[1] / n, ax[2] / n, ax[3] / n, 0 }
  end
  local c = { u[2] * v[3] - u[3] * v[2], u[3] * v[1] - u[1] * v[3], u[1] * v[2] - u[2] * v[1] }
  local w = 1 + d
  local n = math.sqrt(c[1] ^ 2 + c[2] ^ 2 + c[3] ^ 2 + w * w)
  return { c[1] / n, c[2] / n, c[3] / n, w / n }
end
local function vnorm(v) local n = math.sqrt(v[1] ^ 2 + v[2] ^ 2 + v[3] ^ 2); if n < 1e-9 then return nil end; return { v[1] / n, v[2] / n, v[3] / n } end

local function chain_step(dt)
  if not (S.dir_a and S.rest_b) then log_once('nochaingeo', '[chain] no chain geometry (rest pose not measured)'); return end
  hb('render: chain read')
  local okh, rh = pcall(U.world_rotation, S.unit, S.nodes.hips)
  local Rh = okh and qel(rh)
  local Pa = wpos(S.unit, S.nodes.test)          -- a's own rotation does not move its head
  if not (Rh and Pa) then return end
  local Wa_rest = qmul(Rh, S.rest)
  local Wb_rest = qmul(Wa_rest, S.rest_b)
  local da = qrotv(Wa_rest, S.dir_a)
  local db = qrotv(Wb_rest, S.dir_b)
  local L1, L2 = S.len_a, PHYS.TIP_LEN
  local t1 = { Pa[1] + da[1] * L1, Pa[2] + da[2] * L1, Pa[3] + da[3] * L1 }
  local t2 = { t1[1] + db[1] * L2, t1[2] + db[2] * L2, t1[3] + db[3] * L2 }
  if not S.chain or S.chain.L[2] ~= L2 then S.chain = Chain.new({ L1, L2 }) end
  hb('render: chain sim')
  Chain.step(S.chain, Pa, { t1, t2 }, dt, PHYS)
  local p1, p2 = S.chain.out[1], S.chain.out[2]
  local n1, n2 = vnorm({ p1[1] - Pa[1], p1[2] - Pa[2], p1[3] - Pa[3] }), vnorm({ p2[1] - p1[1], p2[2] - p1[2], p2[3] - p1[3] })
  if not (n1 and n2) then return end
  -- world rotations that point each bone at its simulated joint, then back to local
  local Wa = qmul(qbetween(da, n1), Wa_rest)
  local Wb_base = qmul(Wa, S.rest_b)
  local Wb = qmul(qbetween(qrotv(Wb_base, S.dir_b), n2), Wb_base)
  local la, lb = qmul(qconj(Rh), Wa), qmul(qconj(Wa), Wb)
  hb('render: chain write')
  local qa, qb = qmake(la), qmake(lb)
  if qa and qb and pcall(U.set_local_rotation, S.unit, S.nodes.test, qa) and pcall(U.set_local_rotation, S.unit, S.nodes.child, qb) then
    S.last_written = la; st.writes = st.writes + 1
    hb('render: chain update_unit')
    pcall(W.update_unit, S.world, S.unit)
  else
    st.fails = st.fails + 1
  end
end

local function current_world()
  local ok, w = pcall(A.main_world)
  return ok and w or nil
end

---------------------------------------------------------------- dress physics (generic)
-- An outfit = every registered piece on one Helldiver (dress in the torso, hair in the helmet,
-- sleeves in the arms ...). Each piece is an "item": its strips (a ring, Skirt) and single chains
-- (Chain), each chain hanging from its own parent bone (hips, head, forearm ...).
local frame_dt = 1 / 60
-- Several Helldivers may wear registered pieces: you, your corpse after a respawn (it keeps its
-- armour), teammates (on your screen they wear your mods too). The newest MAX_DRESSES of them are
-- simulated: after a respawn that is you (2026-10-17: the physics stayed on the corpse and the new
-- dress stood as a cone). Each "wearer" has its own body joints, colliders and floor.
local st_asleep = 0
local DR = { items = {}, wearers = {}, seen = {}, world = nil, next_find = 0, on = true,
             waves = {}, blast = nil, blast_t = nil, blast_log = { n = 0, t = 0 },
             stats = { t = 0, n = 0, hits = 0, log_at = 0, waves = 0 } }
local function dress_forget(why)
  if #DR.items > 0 then log('[dress] let go of ' .. #DR.items .. ' piece(s) (' .. why .. ')') end
  DR.items, DR.wearers, DR.seen = {}, {}, {}
end
local function item_rest(it)   -- every dress bone of one piece back to its rest rotation
  for _, pt in ipairs(it.parts) do for c = 1, pt.nc do for k = 1, pt.nb do
    local q = qmake(pt.rl[c][k]); if q then pcall(U.set_local_rotation, it.unit, pt.nodes[c][k], q) end
  end end end
  for _, T_ in ipairs(it.tails) do for k = 1, T_.n do
    local q = qmake(T_.rl[k]); if q then pcall(U.set_local_rotation, it.unit, T_.nodes[k], q) end
  end end
  pcall(W.update_unit, DR.world, it.unit)
end
local function dress_rest()
  for _, it in ipairs(DR.items) do
    local ok, alive = pcall(U.alive, it.unit)
    if ok and alive then item_rest(it) end
  end
end

-- measure one chain at rest: per bone its rest rotation, its direction (head -> next head, in its
-- own frame) and length; the last bone continues the one above
local function measure_chain(u, names, lengths)
  local ch = { nodes = {}, rl = {}, dir = {}, len = {}, n = #names }
  for k, nm in ipairs(names) do
    local n = node(u, nm)
    if not n then return nil, 'bone ' .. nm .. ' missing' end
    ch.nodes[k] = n
    local ok, r = pcall(U.local_rotation, u, n); ch.rl[k] = ok and qel(r)
    if not ch.rl[k] then return nil, 'cannot read ' .. nm end
  end
  for k = 1, ch.n do
    local okw, wr = pcall(U.world_rotation, u, ch.nodes[k]); wr = okw and qel(wr)
    ch.len[k] = lengths and lengths[k] or 0.12
    if k < ch.n then
      local a, b = wpos(u, ch.nodes[k]), wpos(u, ch.nodes[k + 1])
      if not (a and b and wr) then return nil, 'cannot measure ' .. names[k] end
      local d = { b[1] - a[1], b[2] - a[2], b[3] - a[3] }
      local l = math.sqrt(d[1] ^ 2 + d[2] ^ 2 + d[3] ^ 2)
      ch.len[k] = l
      local dl = qrotv(qconj(wr), d); ch.dir[k] = { dl[1] / l, dl[2] / l, dl[3] / l }
    else
      ch.dir[k] = qrotv(qconj(ch.rl[k]), ch.dir[k - 1] or { 0, 0, -1 })
    end
  end
  return ch
end

-- the strip parts of a registration: entry.parts (0.7: several parts, RING or SHEET, layered), or
-- the 0.6 single part in the entry itself (always a ring)
local function entry_parts(entry)
  if entry.parts then return entry.parts end
  if (entry.chains or 0) == 0 then return {} end
  return { { name = 'skirt', type = 'RING', layer = 0, chains = entry.chains, bones = entry.bones, lengths = entry.lengths,
             parents = entry.parents, format = entry.strip_format, over = entry.over } }
end

local function make_part(u, e)
  local pt = { name = e.name or 'skirt', nc = e.chains or 0, nb = e.bones or 0, nodes = {}, rl = {}, dir = {}, len = {}, parent = {},
               pnames = {}, layer = e.layer or 0, open = (e.type == 'SHEET'), over = e.over }
  local fmt = e.format or e.strip_format or 'dress_c%02d_b%d'
  for c = 1, pt.nc do
    local names = {}
    for k = 1, pt.nb do names[k] = string.format(fmt, c, k) end
    local ch, err = measure_chain(u, names, e.lengths and e.lengths[c])
    if not ch then return nil, 'part ' .. pt.name .. ': ' .. err end
    pt.nodes[c], pt.rl[c], pt.dir[c], pt.len[c] = ch.nodes, ch.rl, ch.dir, ch.len
    pt.pnames[c] = (e.parents and e.parents[c]) or 'hips'
    local pn = node(u, pt.pnames[c])
    if not pn then return nil, 'part ' .. pt.name .. ': parent bone of strip ' .. c .. ' missing' end
    pt.parent[c] = pn
  end
  pt.skirt = Skirt.new(pt.nc, pt.len[1])
  pt.skirt.open = pt.open
  for c = 1, pt.nc do pt.skirt.chains[c].L = pt.len[c] end
  -- leg-follow only makes sense for strips hanging from the hips (skirts, front panels)
  pt.leg_follow = true
  for c = 1, pt.nc do if pt.pnames[c] ~= 'hips' then pt.leg_follow = false end end
  return pt
end

local function make_item(u, entry)
  local it = { unit = u, entry = entry, parts = {}, tails = {}, speed = 0, prev_anchor = nil, nc = 0 }
  for _, e in ipairs(entry_parts(entry)) do
    local pt, err = make_part(u, e)
    if not pt then return nil, err end
    it.parts[#it.parts + 1] = pt; it.nc = it.nc + pt.nc
  end
  for ti, t in ipairs(entry.tails or {}) do
    local names = {}
    for k = 1, t.bones do names[k] = string.format('%s_b%d', t.prefix, k) end
    local ch, err = measure_chain(u, names, t.lengths)
    if ch then
      ch.parent = node(u, t.parent or 'hips')
      if ch.parent then ch.chain = Chain.new(ch.len); ch.chain.over = t.over; it.tails[#it.tails + 1] = ch end
    else
      log_once('tail' .. tostring(entry.unit) .. ti, '[dress] ' .. (entry.name or '?') .. ': ' .. err)
    end
  end
  return it
end

local function describe(it)
  local d = {}
  for _, pt in ipairs(it.parts) do d[#d + 1] = string.format('%s %s %dx%d%s', pt.name, pt.open and 'sheet' or 'ring', pt.nc, pt.nb,
                                                             pt.layer > 0 and (' layer ' .. pt.layer) or '') end
  return (#d > 0 and table.concat(d, ', ') or 'no strips') .. string.format(', %d single chain(s)', #it.tails)
end

local function dress_find(world)
  if clock < DR.next_find then return end
  DR.next_find = clock + 2
  local reg = rawget(_G, 'HD2DRESS_REGISTRY')
  if type(reg) ~= 'table' or #reg == 0 then log_once('noreg', '[dress] no dress registered (install a dress mod with its HD2 Dress registration addon)'); return end
  local avatars = by_res(world, CFG.AVATAR)
  -- every registered piece in this world, with the Helldiver it sits on (nearest root)
  local found = {}
  for _, r in ipairs(reg) do
    for _, u in ipairs(by_res(world, r.unit)) do
      local p = wpos(u, 1)
      local av, ad = nil, nil
      for _, a in ipairs(avatars) do
        local ap = wpos(a, 1)
        local d = (p and ap) and dist2(p, ap) or 1e9
        if not ad or d < ad then av, ad = a, d end
      end
      if av and ad < 1.5 * 1.5 then found[#found + 1] = { unit = u, entry = r, avatar = av } end
    end
  end
  if #found == 0 then
    if #DR.items > 0 then dress_forget('no registered pieces worn here any more') end
    log_once('nodress', '[dress] none of the registered dresses is worn here'); return
  end
  -- the Helldivers wearing something, newest first (seen = when we first saw them)
  local live_av = {}
  for _, a in ipairs(avatars) do live_av[a] = true end
  for a in pairs(DR.seen) do if not live_av[a] then DR.seen[a] = nil end end
  local order, has = {}, {}
  for _, f in ipairs(found) do
    if not has[f.avatar] then has[f.avatar] = true; DR.seen[f.avatar] = DR.seen[f.avatar] or clock; order[#order + 1] = f.avatar end
  end
  -- who moved since the last look (every 2 s)? A body ragdolls for a moment, then lies still; living
  -- players practically never stand perfectly still. Moving Helldivers first, newest first among
  -- them, so a mission's players keep their slots ahead of any corpses (user idea, 2026-10-17).
  DR.lastpos, DR.moving_until = DR.lastpos or {}, DR.moving_until or {}
  for _, a in ipairs(order) do
    local hn = node(a, 'hips')
    local p = hn and wpos(a, hn)
    local q = DR.lastpos[a]
    if p and (not q or dist2(p, q) > 0.03 ^ 2) then DR.moving_until[a] = clock + 5 end
    DR.lastpos[a] = p
  end
  for a in pairs(DR.lastpos) do if not live_av[a] then DR.lastpos[a] = nil; DR.moving_until[a] = nil end end
  local function moving(a) return (DR.moving_until[a] or 0) > clock end
  table.sort(order, function(a, b)
    if moving(a) ~= moving(b) then return moving(a) end
    return DR.seen[a] > DR.seen[b]
  end)
  local picked = {}
  for i = 1, math.min(#order, math.max(1, PHYS.MAX_DRESSES or 4)) do picked[order[i]] = true end
  local items, changed = {}, false
  local old = {}
  for _, it in ipairs(DR.items) do old[it.unit] = it end
  local listed = {}
  for _, f in ipairs(found) do
    listed[f.unit] = true
    if picked[f.avatar] then
      local it = old[f.unit]
      if not it then
        local err
        it, err = make_item(f.unit, f.entry)
        if it then
          changed = true
          log(string.format('[dress] found "%s": %s', f.entry.name or f.entry.unit, describe(it)))
        else
          log_once('bad' .. tostring(f.entry.unit), '[dress] ' .. (f.entry.name or '?') .. ': ' .. tostring(err))
        end
      end
      if it then it.av = f.avatar; items[#items + 1] = it; old[f.unit] = nil end
    end
  end
  -- pieces that dropped off the list but are still in the world (a corpse when a 5th dress appears):
  -- back to rest, so they do not freeze mid-swing (only units listed this pass: they exist)
  for u, it in pairs(old) do if listed[u] then item_rest(it) end; changed = true end
  if #items ~= #DR.items then changed = true end
  DR.items, DR.world = items, world
  local wearers = {}
  for a in pairs(picked) do
    local wr = DR.wearers[a]
    if not wr then
      local body, n = {}, 0
      for _, nm in ipairs(Body.JOINTS) do body[nm] = node(a, nm); if body[nm] then n = n + 1 end end
      wr = { av = a, body = n > 0 and body or nil, n = n, ground = {} }
      changed = true
      for _, it in ipairs(items) do if it.av == a then
        for _, pt in ipairs(it.parts) do pt.fit = nil end; for _, T_ in ipairs(it.tails) do T_.fit = nil end
      end end
    end
    wearers[a] = wr
  end
  DR.wearers = wearers
  if changed then
    local nw, joints = 0, {}
    for _, wr in pairs(wearers) do nw = nw + 1; joints[#joints + 1] = wr.n end
    log(string.format('[dress] outfit: %d piece(s) on %d Helldiver(s) (moving and newest first, of %d wearing one); body joints %s of %d each',
                      #items, nw, #order, table.concat(joints, '/'), #Body.JOINTS))
  end
end

-- the values for one piece: the player's settings, then the author's values from its registration
-- (entry.params) on top; the player's MUL_* multipliers scale the author's values
local function item_params(it)
  local params = it.entry and it.entry.params
  if not params then return PHYS end
  if it.p_cache and it.p_src == settings_text then return it.p_cache end
  local P = {}
  for k, v in pairs(PHYS) do P[k] = v end
  for k, v in pairs(params) do P[k] = v end
  it.p_cache, it.p_src = P, settings_text
  return P
end

-- pose one chain's bones toward simulated joints (pts[1..n]) from its anchor a, parent rotation Rp
local function pose_chain(u, ch_nodes, ch_rl, ch_dir, Rp, a, pts, n)
  local Wp, prev = Rp, a
  for k = 1, n do
    local pt = pts[k]
    local nv = vnorm({ pt[1] - prev[1], pt[2] - prev[2], pt[3] - prev[3] })
    local Wbase = qmul(Wp, ch_rl[k])
    local Wn = nv and qmul(qbetween(qrotv(Wbase, ch_dir[k]), nv), Wbase) or Wbase
    local q = qmake(qmul(qconj(Wp), Wn))
    if q then pcall(U.set_local_rotation, u, ch_nodes[k], q) end
    Wp, prev = Wn, pt
  end
end

-- rest targets of one chain: from its anchor, each bone at rest under its rest-posed parent
local function chain_targets(Rp, a, ch_rl, ch_dir, ch_len, n)
  local T_, W_, prev = {}, Rp, a
  for k = 1, n do
    W_ = qmul(W_, ch_rl[k])
    local d = qrotv(W_, ch_dir[k]); local L = ch_len[k]
    prev = { prev[1] + d[1] * L, prev[2] + d[2] * L, prev[3] + d[3] * L }
    T_[k] = prev
  end
  return T_
end

-- this frame's body: joint positions, colliders, the legs (for leg-follow) and the floor
local function body_now(wr, P)
  if not (wr and wr.J) then return nil end
  local J = wr.J
  local legs
  if J.l_thigh and J.l_knee and J.r_thigh and J.r_knee then
    legs = { { hip = J.l_thigh, knee = J.l_knee }, { hip = J.r_thigh, knee = J.r_knee } }
  end
  return { caps = Body.capsules(J, P), legs = legs, floor = wr.floor }
end

-- a part's values: the piece's values with its layer's extra clearance (outer layers stay outside)
local function part_params(pt, P)
  if pt.layer <= 0 then return P end
  if pt.P_src ~= P then
    pt.P = setmetatable({ MARGIN = (P.MARGIN or 0.03) + pt.layer * (P.LAYER_GAP or 0.02) }, { __index = P })
    pt.P_src = P
  end
  return pt.P
end

local function part_step(it, pt, dt, P, B)
  local u = it.unit
  if #DR.waves > 0 and pt.skirt.chains[1].p then
    DR.stats.waves = DR.stats.waves + Blast.kick_skirt(pt.skirt, DR.waves, DR.blast_t0, clock, P, 1 / (P.SUBSTEP_HZ or 60))
  end
  if pt.over then pt.skirt.over = pt.over end
  local A, T, Rps = {}, {}, {}
  for c = 1, pt.nc do
    local okp, rp = pcall(U.world_rotation, u, pt.parent[c]); Rps[c] = okp and qel(rp)
    A[c] = wpos(u, pt.nodes[c][1])
    if not (Rps[c] and A[c]) then return end
    T[c] = chain_targets(Rps[c], A[c], pt.rl[c], pt.dir[c], pt.len[c], pt.nb)
  end
  local PP = part_params(pt, P)
  local caps
  if B then
    if not pt.fit then pt.fit = Body.fit(B.caps, A, PP) end   -- thinner colliders where its top sits on the body
    caps = Body.apply(B.caps, pt.fit)
  end
  local TF = T
  if pt.leg_follow and B and B.legs then TF = Skirt.leg_follow(pt.skirt, A, T, B.legs, Rps[1], dt, PP) end
  Skirt.step(pt.skirt, A, TF, dt, PP, caps, B and B.floor)
  for c = 1, pt.nc do pose_chain(u, pt.nodes[c], pt.rl[c], pt.dir[c], Rps[c], A[c], pt.skirt.out[c], pt.nb) end
  DR.stats.hits = DR.stats.hits + (pt.skirt.hits or 0)
end

-- while a shock wave passes a Helldiver: BLAST_SUBSTEPS x more physics steps and BLAST_MAX_SPEED
local function fast_params(it, P)
  if it.fp_src ~= P then
    local F = {}
    for k, v in pairs(P) do F[k] = v end
    F.SUBSTEP_HZ = (P.SUBSTEP_HZ or 60) * math.max(1, math.floor(P.BLAST_SUBSTEPS or 4))
    F.MAX_SPEED = P.BLAST_MAX_SPEED or 30
    it.fp, it.fp_src = F, P
  end
  return it.fp
end

local function item_step(it, dt)
  local P = item_params(it)
  local wr = DR.wearers[it.av]
  if wr and (wr.fast_until or 0) > clock and (P.BLAST_SUBSTEPS or 4) > 1 then P = fast_params(it, P) end
  local u = it.unit
  local B = body_now(DR.wearers[it.av], P)
  for _, pt in ipairs(it.parts) do part_step(it, pt, dt, P, B) end
  if #it.tails > 0 then
    local TP = Chain.group_params(P, 'TAIL', Chain.TAIL_DEFAULTS)
    local okr, rr = pcall(U.world_rotation, u, 1)
    local side = okr and qrotv(qel(rr) or { 0, 0, 0, 1 }, { 1, 0, 0 }) or { 1, 0, 0 }
    for _, T_ in ipairs(it.tails) do
      local a = wpos(u, T_.nodes[1])
      local okp, rp = pcall(U.world_rotation, u, T_.parent); local Rp = okp and qel(rp)
      if a and Rp then
        if it.prev_anchor and dt > 0 then
          local sp = math.sqrt((a[1] - it.prev_anchor[1]) ^ 2 + (a[2] - it.prev_anchor[2]) ^ 2) / dt
          it.speed = it.speed + (math.min(sp, 15) - it.speed) * math.min(1, dt * 4)
        end
        it.prev_anchor = a
        local caps
        if B then
          if not T_.fit then T_.fit = Body.fit(B.caps, { a }, TP) end
          caps = Body.apply(B.caps, T_.fit)
        end
        local tg = chain_targets(Rp, a, T_.rl, T_.dir, T_.len, T_.n)
        if #DR.waves > 0 and T_.chain.p then
          DR.stats.waves = DR.stats.waves + Blast.kick_chain(T_.chain, DR.waves, DR.blast_t0, clock, TP, 1 / (TP.SUBSTEP_HZ or 60))
        end
        Chain.step(T_.chain, a, Chain.wave(tg, side, clock, it.speed, TP), dt, TP, caps, B and B.floor)
        pose_chain(u, T_.nodes, T_.rl, T_.dir, Rp, a, T_.chain.out, T_.n)
      end
    end
  end
  pcall(W.update_unit, DR.world, u)
end

-- the explosion queue reader: game.dll read through ReadProcessMemory (a bad address = a failed read,
-- never a crash), opened once; any doubt (FFI missing, unknown build) = waves off, logged once
local function blast_mem()
  local okf, ffi = pcall(require, 'ffi')
  if not (okf and ffi) then return nil, 'FFI unavailable' end
  for _, d in ipairs({ 'void *HD2D_GetCurrentProcess(void) __asm__("GetCurrentProcess");',
                       'int HD2D_ReadProcessMemory(void *, const void *, void *, size_t, size_t *) __asm__("ReadProcessMemory");',
                       'void *HD2D_GetModuleHandleA(const char *) __asm__("GetModuleHandleA");' }) do pcall(ffi.cdef, d) end
  local okk, k32 = pcall(ffi.load, 'kernel32')
  if not okk then return nil, 'kernel32 unavailable' end
  local proc = k32.HD2D_GetCurrentProcess()
  local h = k32.HD2D_GetModuleHandleA('game.dll')
  if h == nil then return nil, 'game.dll not loaded' end
  local buf, got = ffi.new('uint8_t[?]', 4096 + 1216), ffi.new('size_t[1]')
  local base = tonumber(ffi.cast('uintptr_t', h))
  return { base = base, read = function(a, n)
    if n > 4096 + 1216 or a <= 0 then return nil end
    if k32.HD2D_ReadProcessMemory(proc, ffi.cast('const void *', ffi.cast('uintptr_t', a)), buf, n, got) == 0 or got[0] ~= n then return nil end
    return ffi.string(buf, n)
  end }
end

local function blast_frame()
  if (PHYS.BLAST or 1) == 0 then DR.waves = {}; return end
  if DR.blast == nil then
    local mem, why = blast_mem()
    local B
    if mem then B, why = Blast.open(mem) end
    DR.blast = B or false
    log(B and string.format('[blast] explosion reader on (game.dll build %08X)', Blast.PIN.build) or ('[blast] explosion reader off: ' .. tostring(why)))
  end
  DR.blast_t0 = DR.blast_t or clock
  DR.blast_t = clock
  if not DR.blast then return end
  for _, e in ipairs(Blast.poll(DR.blast, clock)) do
    local w = Blast.wave(e, clock, PHYS)
    if w then
      -- only waves that can reach a dress matter (and get a log line, at most 20 per 10 s)
      local near
      for _, wr in pairs(DR.wearers) do
        local h = wr.J and wr.J.hips
        if h then
          local d = math.sqrt(dist2(h, w.c))
          if d < w.R then
            if not near or d < near then near = d end
            local till = clock + d / w.v + (PHYS.BLAST_PUSH or 0.15) + 0.8   -- fast steps + awake until it has passed
            wr.fast_until = math.max(wr.fast_until or 0, till)
            wr.wake_until = math.max(wr.wake_until or 0, till + 2)
          end
        end
      end
      if near then
        DR.waves[#DR.waves + 1] = w
        local L = DR.blast_log
        if clock - L.t > 10 then L.t, L.n = clock, 0 end
        L.n = L.n + 1
        if L.n <= 20 then log(string.format('[blast] %s (type %d) %.0f m away: shock wave %.1f m/s, arrives in %.2f s', w.name, w.type, near, w.S * (1 - near / w.R) ^ 2, near / w.v)) end
      end
    end
  end
  DR.waves = Blast.prune(DR.waves, clock)
end

local function dress_frame(world)
  if world ~= DR.world and #DR.items > 0 then dress_forget('world changed') end
  hb('render: dress find')
  dress_find(world)
  if #DR.items == 0 or not DR.on or PHYS.DRESS == 0 then return end
  -- EVERY frame, before any other call: are the pieces and the legs' Helldiver still there?
  -- (2026-10-16: the Superstore preview swapped its Helldiver; touching the deleted unit crashed
  -- the game natively inside the dress step. Unit.alive is the engine's own stale-handle check.)
  hb('render: dress alive')
  for a, wr in pairs(DR.wearers) do
    local okv, alive = pcall(U.alive, a)
    if not (okv and alive) then DR.wearers[a] = nil; DR.seen[a] = nil; DR.next_find = 0; log('[dress] a Helldiver is gone') end
  end
  local live = {}
  for _, it in ipairs(DR.items) do
    if DR.wearers[it.av] then     -- never touch a piece whose Helldiver is gone (no call into it at all)
      local oka, alive = pcall(U.alive, it.unit)
      if oka and alive then live[#live + 1] = it else log('[dress] a piece is gone: ' .. (it.entry.name or '?')) end
    end
  end
  -- this frame's body of each wearer (joints, floor), once per wearer
  for _, wr in pairs(DR.wearers) do
    if wr.body then
      local J = {}
      for nm, nd in pairs(wr.body) do J[nm] = wpos(wr.av, nd) end
      wr.J = J
      wr.floor = Body.ground(wr.ground, J, PHYS, frame_dt)
      -- still? (every joint within 2.5 cm of where it was when it last moved): asleep after 3 s
      local moved = not wr.ref
      if wr.ref then for nm, p in pairs(J) do local r = wr.ref[nm]; if not r or dist2(p, r) > 0.025 ^ 2 then moved = true; break end end end
      if moved then wr.ref = J; wr.still_since = clock end
      local was = wr.asleep
      wr.asleep = (PHYS.SLEEP or 1) ~= 0 and clock - (wr.still_since or clock) > 3 and clock > (wr.wake_until or 0)
      if wr.asleep and not was then DR.stats.slept = (DR.stats.slept or 0) + 1 end
    end
  end
  hb('render: blasts')
  local okb, errb = pcall(blast_frame)
  if not okb then log_once('blasterr:' .. tostring(errb), '[blast] error: ' .. tostring(errb)); DR.blast = false end
  DR.items = live
  if #live == 0 then dress_forget('the dress unit is gone'); return end
  hb('render: dress step')
  local t0 = os.clock()
  local awake = 0
  for _, it in ipairs(live) do
    local wr = DR.wearers[it.av]
    if not (wr and wr.asleep) then item_step(it, frame_dt); awake = awake + 1 end
  end
  st_asleep = #live - awake
  local st_ = DR.stats
  st_.asleep = st_asleep
  st_.t = st_.t + (os.clock() - t0); st_.n = st_.n + 1
  if clock >= st_.log_at then
    if st_.n > 0 then log(string.format('[dress] %d frames, %.2f ms per frame (%d piece(s)%s), %d collision pushes%s', st_.n, 1000 * st_.t / st_.n, #live,
                                         (st_.asleep or 0) > 0 and string.format(', %d asleep', st_.asleep) or '', st_.hits,
                                         st_.waves > 0 and string.format(', %d joint kicks from shock waves', st_.waves) or '')) end
    DR.stats = { t = 0, n = 0, hits = 0, log_at = clock + 10, waves = 0 }
  end
end

local function guarded_dress(world)
  local ok, err = pcall(dress_frame, world)
  if not ok then log_once('dresserr:' .. tostring(err), '[dress] error: ' .. tostring(err)) end
end

local next_settings = 0
local function step(phase)
  if clock >= next_settings then
    next_settings = clock + 2
    hb(phase .. ': settings')
    local msg = load_settings(next_settings <= 2)
    if msg then log('[chain] ' .. msg) end
  end
  hb(phase .. ': world')
  local world = current_world()
  if world ~= S.world then
    if S.world then forget('world changed') end
    S.world = world
  end
  if not world then return end
  if phase == 'render' then guarded_dress(world) end
  if phase == 'render' then hb('render: find'); find(world) end
  if not S.unit then return end
  if phase == 'render' then
    hb('render: alive')
    local okl, alive = pcall(U.alive, S.unit)
    if not (okl and alive) then forget('unit gone'); return end
    hb('render: observe')
    observe()
    hb('render: write')
    if S.mode == 1 or S.mode == 4 then write() end
    if S.mode == 3 and not S.once_done then write(); S.once_done = true end
    if S.mode == 5 then chain_step(frame_dt) end
    hb('render: report')
    report()
  elseif phase == 'update' and S.mode == 2 then
    write()
  end
end

local function cycle()
  -- back to rest before switching, so 'rest' stays meaningful
  if S.unit and S.rest then
    local q = qmake(S.rest)
    if q then pcall(U.set_local_rotation, S.unit, S.nodes.test, q) end
    local qb = S.rest_b and qmake(S.rest_b)
    if qb then pcall(U.set_local_rotation, S.unit, S.nodes.child, qb) end
    pcall(W.update_unit, S.world, S.unit)
  end
  S.mode = (S.mode + 1) % #MODES
  MODE_NOW = S.mode
  S.once_done, S.last_written, S.chain = false, nil, nil
  stats_reset()
  log('[gate] mode -> ' .. MODES[S.mode + 1] .. (S.unit and '' or ' (no test piece found yet)'))
end

---------------------------------------------------------------- keys + hooks
local key
for _, k in ipairs({ CFG.KEY, CFG.KEY_ALT }) do
  local ok, i = pcall(KB.button_index, k)
  if ok and i then key = i; log('[gate] key ' .. k .. ' cycles the test'); break end
end
if not key then log('[gate] no usable key (' .. tostring(CFG.KEY) .. ')') end
local dress_key
do local ok, i = pcall(KB.button_index, CFG.KEY_DRESS); if ok and i then dress_key = i end end

local function guarded(fn, ...)
  local ok, err = pcall(fn, ...)
  if not ok then log_once('err:' .. tostring(err), '[gate] error: ' .. tostring(err)) end
end

local previous_update = rawget(_G, 'update')
local render_hooked = false
update = function(dt, ...)
  local result
  beat_frame = beat_frame + 1
  hb('update: game update (not ours)')
  if previous_update then result = previous_update(dt, ...) end
  hb('update: ours')
  clock = clock + (tonumber(dt) or 0)
  frame_dt = tonumber(dt) or frame_dt
  if key then
    local ok, p = pcall(KB.pressed, key)
    if ok and p then guarded(cycle) end
  end
  if dress_key then
    local ok, p = pcall(KB.pressed, dress_key)
    if ok and p then
      DR.on = not DR.on
      if not DR.on then pcall(dress_rest) end
      log('[dress] physics ' .. (DR.on and 'ON' or 'OFF (bones back at rest)'))
    end
  end
  guarded(step, 'update')
  hb('update: done')
  if not render_hooked and type(rawget(_G, 'render')) == 'function' then
    render_hooked = true
    local old = rawget(_G, 'render')
    render = function(...)
      hb('render: ours')
      guarded(step, 'render')
      hb('render: game render (not ours)')
      local r = { old(...) }
      hb('render: done (between frames)')
      return unpack(r)
    end
    log('[gate] render hook ready')
  end
  return result
end
log('[gate] loaded; wear B-01 Tactical, press ' .. CFG.KEY .. ' to cycle')
