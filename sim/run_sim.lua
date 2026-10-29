-- Offline dress simulator: the same mod/lib/chain.lua the game runs, on the game's own animations.
--   luajit sim/run_sim.lua INPUT.lua OUT.csv [KEY=value ...]
-- INPUT from sim/prepare.py. Builds a skirt: N_CHAINS chains of SEGS joints hanging from a waist
-- ring that moves rigidly with the hips; each chain is a spring chain colliding with capsules on
-- both thighs and shins. Writes one CSV row per frame: the skeleton joints and every skirt joint,
-- for the physics skirt and for a rigid skirt (no physics, what plain skinning does) to compare.
-- Every value below can be overridden on the command line (KEY=value), like the game's settings file.
local LIB = (arg[0]:match('^(.*)/') or '.') .. '/../mod/lib/'
local Chain = assert(loadfile(LIB .. 'chain.lua'))()
local Skirt = assert(loadfile(LIB .. 'skirt.lua'))()(Chain)
local P = {
  -- skirt shape (Helldiver rest pose; +Y forward, +Z up)
  N_CHAINS = 10, SEGS = 3, SEG_LEN = 0.14,
  WAIST_Z = 0.93, WAIST_RX = 0.20, WAIST_RY = 0.16, WAIST_DY = -0.02,  -- ring height, half widths, centre offset
  FLARE_DEG = 18,                     -- how far the panels angle outward from vertical at rest
  -- physics (same keys as the game's settings file)
  GRAVITY = 9.81, STIFFNESS = 0, BOUNCE = 0, FOLLOW = 0.0, SUBSTEP_HZ = 60,   -- DAMPING, SHAPE, MAX_ANGLE...: skirt.lua defaults
  TELEPORT = 1.5, MARGIN = 0.03, SAMPLES = 4, ITER = 3,   -- STRETCH, TIE, DAMPING_HEM, WEIGHT_TOP, LEG_FOLLOW: skirt.lua defaults
  -- leg colliders
  THIGH_R = 0.085, SHIN_R = 0.06, COLLIDE = 1,
  THIGH_START = 0.1,                  -- the thigh collider starts this far down the thigh (the top is inside the hips/waistband)
}
local input, outpath = arg[1], arg[2]
for i = 3, #arg do
  local k, v = arg[i]:match('^([%w_]+)=(.+)$')
  if k == 'DRESS' then DRESS_FILE = v elseif k then P[k] = tonumber(v) end   -- TAIL_<key>=v sets the tail's own value
end
local D = assert(loadfile(input))()
local dt = 1 / D.fps

-- quaternion helpers ({w,x,y,z} as exported)
local function qmul(a, b)
  return { a[1] * b[1] - a[2] * b[2] - a[3] * b[3] - a[4] * b[4], a[1] * b[2] + a[2] * b[1] + a[3] * b[4] - a[4] * b[3],
           a[1] * b[3] - a[2] * b[4] + a[3] * b[1] + a[4] * b[2], a[1] * b[4] + a[2] * b[3] - a[3] * b[2] + a[4] * b[1] }
end
local function qconj(q) return { q[1], -q[2], -q[3], -q[4] } end
local function qrot(q, v)
  local r = qmul(qmul(q, { 0, v[1], v[2], v[3] }), qconj(q)); return { r[2], r[3], r[4] }
end
local function pos(b) return { b[1], b[2], b[3] } end
local function rot(b) return { b[4], b[5], b[6], b[7] } end

-- the skirt in the rest pose: anchors on the waist ring, joints hanging down and out
local hips_rest = D.rest.hips
local ring = {}
for c = 1, P.N_CHAINS do
  local a = 2 * math.pi * (c - 1) / P.N_CHAINS
  local dx, dy = math.sin(a), math.cos(a)              -- c = 1 at the front (+Y)
  local anchor = { P.WAIST_RX * dx, P.WAIST_DY + P.WAIST_RY * dy, P.WAIST_Z }
  local fl = math.rad(P.FLARE_DEG)
  local dir = { dx * math.sin(fl), dy * math.sin(fl), -math.cos(fl) }
  local js = {}
  for j = 1, P.SEGS do js[j] = { anchor[1] + dir[1] * P.SEG_LEN * j, anchor[2] + dir[2] * P.SEG_LEN * j, anchor[3] + dir[3] * P.SEG_LEN * j } end
  ring[c] = { anchor = anchor, joints = js }
end
-- a real dress instead of the test ring: DRESS=<rest file> (sim/dress_rest.py turns an autorig
-- hd2dress_register.json into it: return { { {x,y,z} anchor, {x,y,z} joint1, ... }, ... })
local TAILS = {}
if DRESS_FILE then
  local chains = assert(loadfile(DRESS_FILE))()
  for _, pts in ipairs(chains.tails or {}) do
    local L, js = {}, {}
    for j = 2, #pts do
      local a, b = pts[j - 1], pts[j]
      L[j - 1] = math.sqrt((a[1] - b[1]) ^ 2 + (a[2] - b[2]) ^ 2 + (a[3] - b[3]) ^ 2); js[j - 1] = pts[j]
    end
    TAILS[#TAILS + 1] = { anchor = pts[1], joints = js, chain = Chain.new(L), n = #pts - 1 }
  end
  chains.tails = nil
  P.N_CHAINS, P.SEGS = #chains, #chains[1] - 1
  ring = {}
  for c, pts in ipairs(chains) do
    local js = {}; for j = 2, #pts do js[j - 1] = pts[j] end
    ring[c] = { anchor = pts[1], joints = js }
  end
end
local SEGL = {}
for j = 1, P.SEGS do
  local a, b = j == 1 and ring[1].anchor or ring[1].joints[j - 1], ring[1].joints[j]
  SEGL[j] = math.sqrt((a[1] - b[1]) ^ 2 + (a[2] - b[2]) ^ 2 + (a[3] - b[3]) ^ 2)
end
local skirt = Skirt.new(P.N_CHAINS, SEGL)
for c = 1, P.N_CHAINS do
  local L = {}
  for j = 1, P.SEGS do
    local a, b = j == 1 and ring[c].anchor or ring[c].joints[j - 1], ring[c].joints[j]
    L[j] = math.sqrt((a[1] - b[1]) ^ 2 + (a[2] - b[2]) ^ 2 + (a[3] - b[3]) ^ 2)
  end
  skirt.chains[c].L = L
end

-- rest-pose point -> this frame (rigid with the hips)
local function follow_hips(f, p)
  local hr, hn = rot(hips_rest), rot(f.hips)
  local R = qmul(hn, qconj(hr))
  local d = qrot(R, { p[1] - hips_rest[1], p[2] - hips_rest[2], p[3] - hips_rest[3] })
  return { f.hips[1] + d[1], f.hips[2] + d[2], f.hips[3] + d[3] }
end
local function capsules(f)
  if P.COLLIDE == 0 then return nil end
  local function along(a, b, t) return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t } end
  return {
    { a = along(pos(f.l_thigh), pos(f.l_knee), P.THIGH_START), b = pos(f.l_knee), r = P.THIGH_R }, { a = pos(f.l_knee), b = pos(f.l_foot), r = P.SHIN_R },
    { a = along(pos(f.r_thigh), pos(f.r_knee), P.THIGH_START), b = pos(f.r_knee), r = P.THIGH_R }, { a = pos(f.r_knee), b = pos(f.r_foot), r = P.SHIN_R },
  }
end
-- what you SEE: the drawn surface (bilinear panels between chains/levels), sampled finely, against
-- the drawn legs (the capsule radii, no margin). Returns the deepest penetration (m), 0 = clean.
local VIS = 6
local function surface_depth(A, Pj, caps, band)
  local worst = 0
  local function at(c, j) if j == 0 then return A[c] end return Pj[c][j] end
  for c = 1, P.N_CHAINS do
    local c2 = c % P.N_CHAINS + 1
    for j = 1, P.SEGS do
      local q = { at(c, j - 1), at(c2, j - 1), at(c, j), at(c2, j) }
      -- the waistband row (top of level 1) is fixed to the body: measured only when band = true
      for si = 0, VIS do for sj = (band and 0 or (j == 1 and 1 or 0)), (band and 0 or VIS) do
        if band and j > 1 then break end
        local u, v = si / VIS, sj / VIS
        local w = { (1 - u) * (1 - v), u * (1 - v), (1 - u) * v, u * v }
        local x = { 0, 0, 0 }
        for k = 1, 4 do x[1] = x[1] + q[k][1] * w[k]; x[2] = x[2] + q[k][2] * w[k]; x[3] = x[3] + q[k][3] * w[k] end
        for _, cp in ipairs(caps) do
          local ab = { cp.b[1] - cp.a[1], cp.b[2] - cp.a[2], cp.b[3] - cp.a[3] }
          local ll = ab[1] ^ 2 + ab[2] ^ 2 + ab[3] ^ 2
          local t = math.max(0, math.min(1, ((x[1] - cp.a[1]) * ab[1] + (x[2] - cp.a[2]) * ab[2] + (x[3] - cp.a[3]) * ab[3]) / ll))
          local d = math.sqrt((x[1] - cp.a[1] - ab[1] * t) ^ 2 + (x[2] - cp.a[2] - ab[2] * t) ^ 2 + (x[3] - cp.a[3] - ab[3] * t) ^ 2)
          worst = math.max(worst, cp.r - d)
        end
      end end
    end
  end
  return worst
end
local function inside(p, caps, extra)   -- deepest penetration of p into any capsule (m), 0 = outside
  local worst = 0
  for _, cp in ipairs(caps) do
    local ab = { cp.b[1] - cp.a[1], cp.b[2] - cp.a[2], cp.b[3] - cp.a[3] }
    local ll = ab[1] ^ 2 + ab[2] ^ 2 + ab[3] ^ 2
    local t = math.max(0, math.min(1, ((p[1] - cp.a[1]) * ab[1] + (p[2] - cp.a[2]) * ab[2] + (p[3] - cp.a[3]) * ab[3]) / ll))
    local q = { cp.a[1] + ab[1] * t, cp.a[2] + ab[2] * t, cp.a[3] + ab[3] * t }
    local d = math.sqrt((p[1] - q[1]) ^ 2 + (p[2] - q[2]) ^ 2 + (p[3] - q[3]) ^ 2)
    worst = math.max(worst, cp.r - d - (extra or 0))
  end
  return worst
end

local SK = { 'hips', 'spine1', 'head', 'l_thigh', 'l_knee', 'l_foot', 'l_toe', 'r_thigh', 'r_knee', 'r_foot', 'r_toe' }
local out = assert(io.open(outpath, 'w'))
local hdr = { 'frame' }
for _, b in ipairs(SK) do for _, ax in ipairs({ 'x', 'y', 'z' }) do hdr[#hdr + 1] = b .. '_' .. ax end end
for _, kind in ipairs({ 'phys', 'rigid' }) do
  for c = 1, P.N_CHAINS do for j = 0, P.SEGS do for _, ax in ipairs({ 'x', 'y', 'z' }) do hdr[#hdr + 1] = string.format('%s_c%d_j%d_%s', kind, c, j, ax) end end end
end
for t, T_ in ipairs(TAILS) do for j = 0, T_.n do for _, ax in ipairs({ 'x', 'y', 'z' }) do hdr[#hdr + 1] = string.format('tail%d_j%d_%s', t, j, ax) end end end
local TP = Chain.group_params(P, 'TAIL', Chain.TAIL_DEFAULTS)
local prev_hips, body_speed, sim_t = nil, 0, 0
out:write(table.concat(hdr, ','), '\n')
out:write(string.format('# N_CHAINS=%d SEGS=%d fps=%g TAILS=%d TAIL_SEGS=%d\n', P.N_CHAINS, P.SEGS, D.fps, #TAILS, TAILS[1] and TAILS[1].n or 0))

local stats = { frames = 0, rigid_in = 0, phys_in = 0, rigid_depth = 0, phys_depth = 0, swing = 0 }
-- feel metrics: how fast the cloth moves relative to its own rest position ("spasm" = big spikes),
-- and after the body stops (the last HOLD frames): how often the hem swings back and forth
local prev_rel, speeds, hold_from = nil, {}, #D.frames - math.floor(1.4 * D.fps)
local hold_dir, crossings, last_sign, settle_amp = {}, 0, {}, 0
local t0 = os.clock()
for fi, f in ipairs(D.frames) do
  local caps = capsules(f)
  local row = { tostring(fi - 1) }
  for _, b in ipairs(SK) do local p = f[b]; row[#row + 1] = string.format('%.4f,%.4f,%.4f', p[1], p[2], p[3]) end
  local phys, rigid = {}, {}
  local test_caps = {
    { a = pos(f.l_thigh), b = pos(f.l_knee), r = P.THIGH_R }, { a = pos(f.l_knee), b = pos(f.l_foot), r = P.SHIN_R },
    { a = pos(f.r_thigh), b = pos(f.r_knee), r = P.THIGH_R }, { a = pos(f.r_knee), b = pos(f.r_foot), r = P.SHIN_R } }
  local A, T = {}, {}
  for c, R in ipairs(ring) do
    A[c] = follow_hips(f, R.anchor)
    T[c] = {}; for j = 1, P.SEGS do T[c][j] = follow_hips(f, R.joints[j]) end
  end
  local hq = rot(f.hips)
  local legs = { { hip = pos(f.l_thigh), knee = pos(f.l_knee) }, { hip = pos(f.r_thigh), knee = pos(f.r_knee) } }
  local TF = Skirt.leg_follow(skirt, A, T, legs, { hq[2], hq[3], hq[4], hq[1] }, dt, P)
  Skirt.step(skirt, A, TF, dt, P, caps)
  for c = 1, P.N_CHAINS do
    phys[#phys + 1] = string.format('%.4f,%.4f,%.4f', A[c][1], A[c][2], A[c][3])
    rigid[#rigid + 1] = string.format('%.4f,%.4f,%.4f', A[c][1], A[c][2], A[c][3])
    for j = 1, P.SEGS do
      local p, r = skirt.out[c][j], T[c][j]
      phys[#phys + 1] = string.format('%.4f,%.4f,%.4f', p[1], p[2], p[3])
      rigid[#rigid + 1] = string.format('%.4f,%.4f,%.4f', r[1], r[2], r[3])
      stats.swing = math.max(stats.swing, math.sqrt((p[1] - r[1]) ^ 2 + (p[2] - r[2]) ^ 2 + (p[3] - r[3]) ^ 2))
    end
  end
  local rel = {}
  for c = 1, P.N_CHAINS do for j = 1, P.SEGS do
    local o, t = skirt.out[c][j], T[c][j]
    rel[#rel + 1] = { o[1] - t[1], o[2] - t[2], o[3] - t[3] }
  end end
  if prev_rel then
    for i, r in ipairs(rel) do
      local q = prev_rel[i]
      speeds[#speeds + 1] = math.sqrt((r[1] - q[1]) ^ 2 + (r[2] - q[2]) ^ 2 + (r[3] - q[3]) ^ 2) * D.fps
    end
  end
  prev_rel = rel
  if fi >= hold_from then   -- hem joints only: count sign changes of their offset along its start direction
    for c = 1, P.N_CHAINS do
      local r = rel[(c - 1) * P.SEGS + P.SEGS]
      if not hold_dir[c] then
        local n = math.sqrt(r[1] ^ 2 + r[2] ^ 2 + r[3] ^ 2)
        hold_dir[c] = n > 0.01 and { r[1] / n, r[2] / n, r[3] / n } or false
      end
      if hold_dir[c] then
        local d = r[1] * hold_dir[c][1] + r[2] * hold_dir[c][2] + r[3] * hold_dir[c][3]
        local sgn = d > 0.005 and 1 or (d < -0.005 and -1 or 0)
        if sgn ~= 0 and last_sign[c] and sgn ~= last_sign[c] then crossings = crossings + 1 end
        if sgn ~= 0 then last_sign[c] = sgn end
        if fi > #D.frames - 10 then settle_amp = math.max(settle_amp, math.abs(d)) end
      end
    end
  end
  -- hoop measure: at the hem, how much does each strip move on its own vs the ring moving as one?
  do
    local mean = { 0, 0, 0 }
    local ds = {}
    for c = 1, P.N_CHAINS do
      local o, t = skirt.out[c][P.SEGS], T[c][P.SEGS]
      ds[c] = { o[1] - t[1], o[2] - t[2], o[3] - t[3] }
      for k = 1, 3 do mean[k] = mean[k] + ds[c][k] / P.N_CHAINS end
    end
    local own, tot = 0, 0
    for c = 1, P.N_CHAINS do
      own = own + math.sqrt((ds[c][1] - mean[1]) ^ 2 + (ds[c][2] - mean[2]) ^ 2 + (ds[c][3] - mean[3]) ^ 2)
      tot = tot + math.sqrt(ds[c][1] ^ 2 + ds[c][2] ^ 2 + ds[c][3] ^ 2)
    end
    if tot > 0.02 * P.N_CHAINS then stats.own = (stats.own or 0) + own / tot; stats.own_n = (stats.own_n or 0) + 1 end
  end
  -- streaming: how far the hem trails behind its rest place, averaged over the strips
  do
    local tot = 0
    for c = 1, P.N_CHAINS do local o, t = skirt.out[c][P.SEGS], T[c][P.SEGS]; tot = tot + math.sqrt((o[1] - t[1]) ^ 2 + (o[2] - t[2]) ^ 2 + (o[3] - t[3]) ^ 2) end
    stats.trail = math.max(stats.trail or 0, tot / P.N_CHAINS)
    if fi > #D.frames * 0.35 and fi < #D.frames * 0.6 then stats.steady = (stats.steady or 0) + tot / P.N_CHAINS; stats.steady_n = (stats.steady_n or 0) + 1 end
  end
  local dr, dp = surface_depth(A, T, test_caps), surface_depth(A, skirt.out, test_caps)
  stats.frames = stats.frames + 1
  -- a frame counts when the leg is more than 5 mm inside the visible cloth
  if dr > 0.005 then stats.rigid_in = stats.rigid_in + 1 end
  if dp > 0.005 then stats.phys_in = stats.phys_in + 1 end
  stats.rigid_depth = math.max(stats.rigid_depth, dr); stats.phys_depth = math.max(stats.phys_depth, dp)
  stats.depth_sum = (stats.depth_sum or 0) + dp
  stats.band = math.max(stats.band or 0, surface_depth(A, T, test_caps, true))
  local tails_out = {}
  if #TAILS > 0 then
    sim_t = sim_t + dt
    local hp = f.hips
    if prev_hips then
      local sp = math.sqrt((hp[1] - prev_hips[1]) ^ 2 + (hp[2] - prev_hips[2]) ^ 2) / dt
      body_speed = body_speed + (sp - body_speed) * math.min(1, dt * 4)     -- smoothed
    end
    prev_hips = hp
    local R = qmul(rot(f.hips), qconj(rot(hips_rest)))
    local side = qrot(R, { 1, 0, 0 })
    for _, T_ in ipairs(TAILS) do
      local a = follow_hips(f, T_.anchor)
      local tg = {}; for j = 1, T_.n do tg[j] = follow_hips(f, T_.joints[j]) end
      Chain.step(T_.chain, a, Chain.wave(tg, side, sim_t, body_speed, TP), dt, TP, caps)
      tails_out[#tails_out + 1] = string.format('%.4f,%.4f,%.4f', a[1], a[2], a[3])
      for j = 1, T_.n do local p = T_.chain.out[j]; tails_out[#tails_out + 1] = string.format('%.4f,%.4f,%.4f', p[1], p[2], p[3]) end
      local tip, tt = T_.chain.out[T_.n], tg[T_.n]
      stats.tail_max = math.max(stats.tail_max or 0, math.sqrt((tip[1] - tt[1]) ^ 2 + (tip[2] - tt[2]) ^ 2 + (tip[3] - tt[3]) ^ 2))
      stats.tail_sum = (stats.tail_sum or 0) + math.sqrt((tip[1] - tt[1]) ^ 2 + (tip[2] - tt[2]) ^ 2 + (tip[3] - tt[3]) ^ 2)
    end
  end
  out:write(table.concat(row, ','), ',', table.concat(phys, ','), ',', table.concat(rigid, ','), #tails_out > 0 and (',' .. table.concat(tails_out, ',')) or '', '\n')
end
out:close()
print(string.format('sim: %d frames (%.1f s), %d chains x %d joints, %.1f ms per frame for the whole skirt',
  stats.frames, stats.frames / D.fps, P.N_CHAINS, P.SEGS, 1000 * (os.clock() - t0) / stats.frames))
print(string.format('sim: legs through the VISIBLE cloth (> 5 mm): rigid (plain skinning) %d of %d frames (deepest %.1f cm); physics %d frames (deepest %.1f cm); largest swing %.1f cm',
  stats.rigid_in, stats.frames, stats.rigid_depth * 100, stats.phys_in, stats.phys_depth * 100, stats.swing * 100))
print(string.format('sim: waistband (fixed to the body, not simulated): the thigh reaches %.1f cm into it at worst', (stats.band or 0) * 100))
table.sort(speeds)
print(string.format('sim: feel: cloth speed vs its rest place: median %.2f, 99%% %.2f, max %.2f m/s; after the stop: %d back-and-forth swings at the hem, still %.1f cm off at the end',
  speeds[math.floor(#speeds * 0.5) + 1] or 0, speeds[math.floor(#speeds * 0.99) + 1] or 0, speeds[#speeds] or 0, crossings, settle_amp * 100))
if #TAILS > 0 then print(string.format('sim: tail tip off its rest place: average %.1f cm, at most %.1f cm', 100 * stats.tail_sum / stats.frames, 100 * stats.tail_max)) end
print(string.format('sim: hoop: strips move on their own %.0f %% of the time-averaged hem movement (0 %% = the whole ring moves as one hoop)', 100 * (stats.own or 0) / math.max(1, stats.own_n or 0)))
print(string.format('sim: streaming: the hem trails its rest place by up to %.1f cm, %.1f cm on average mid-run (averaged over the strips)', 100 * (stats.trail or 0), 100 * (stats.steady or 0) / math.max(1, stats.steady_n or 0)))
