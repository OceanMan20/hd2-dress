-- Step 3 stress run: the real solvers (mod/lib) + whole-body colliders on the game's most extreme
-- moves (sim/stress_prepare.py: dive, prone, crawl, get up, a violent hit, a knock-down).
--   luajit sim/stress.lua SEQ.lua [KEY=value ...]        e.g. SAFE=0 (no DEEP, no speed cap, no floor)
-- The outfit: the Arknight skirt (ring, 12x6, from the hips), a cape (open sheet, 5x5, from the
-- chest) and three hair strands (single chains, from the head). Prints, per move and overall: how
-- deep cloth got inside the body (colliders it does not ignore), how far below the floor, the
-- fastest cloth speed against the body, NaNs, and the cost per frame.
local LIB = 'mod/lib/'
local Chain = assert(loadfile(LIB .. 'chain.lua'))()
local Skirt = assert(loadfile(LIB .. 'skirt.lua'))()(Chain)
local Body = assert(loadfile(LIB .. 'body.lua'))()
local SEQ = assert(loadfile(arg[1]))()
local P = { MARGIN = 0.03 }
local SAFE = 1
FIT = 0   -- FIT=1: thinner colliders (BODY_FIT); 0 = the 0.8 rule (drop a collider the part's top starts inside) for comparison
function OLD_IGNORE(caps, anchors)
  local f = {}
  for _, cp in ipairs(caps) do for _, a in ipairs(anchors) do if Body.dist_to(cp, a) < cp.r then f[cp.name] = false; break end end end
  return f
end
PROBE = os.getenv('PROBE')
for i = 2, #arg do
  local k, v = arg[i]:match('^([%w_]+)=(.+)$')
  if k == 'SAFE' then SAFE = tonumber(v) elseif k == 'FIT' then FIT = tonumber(v) elseif k then P[k] = tonumber(v) end
end
if SAFE == 0 then P.DEEP = 0; P.MAX_SPEED = 1e9 end
local TP = Chain.group_params(P, 'TAIL', Chain.TAIL_DEFAULTS)

-- quaternions as exported: {w, x, y, z} at [4..7]
local function rot(b) return { b[4], b[5], b[6], b[7] } end
local function qmul(a, b)
  return { a[1] * b[1] - a[2] * b[2] - a[3] * b[3] - a[4] * b[4], a[1] * b[2] + a[2] * b[1] + a[3] * b[4] - a[4] * b[3],
           a[1] * b[3] - a[2] * b[4] + a[3] * b[1] + a[4] * b[2], a[1] * b[4] + a[2] * b[3] - a[3] * b[2] + a[4] * b[1] }
end
local function qconj(q) return { q[1], -q[2], -q[3], -q[4] } end
local function qrot(q, v)
  local r = qmul(qmul(q, { 0, v[1], v[2], v[3] }), qconj(q)); return { r[2], r[3], r[4] }
end
local R0 = SEQ.rest
-- a rest-pose point carried rigidly by bone bn this frame
local function carry(f, bn, p)
  local R = qmul(rot(f[bn]), qconj(rot(R0[bn])))
  local d = qrot(R, { p[1] - R0[bn][1], p[2] - R0[bn][2], p[3] - R0[bn][3] })
  return { f[bn][1] + d[1], f[bn][2] + d[2], f[bn][3] + d[3] }
end
local function xyzw(f, bn) local q = qmul(rot(f[bn]), qconj(rot(R0[bn]))); return { q[2], q[3], q[4], q[1] } end   -- for leg_follow

-- the outfit at rest: { parent, rest points per strip / chain }
local skirt_rest = assert(loadfile('sim/work/ark_stocky.lua'))()
local function sheet(nc, nb, x0, x1, y, z, seg, bend)
  local out = {}
  for c = 1, nc do
    local x = x0 + (x1 - x0) * (c - 1) / math.max(1, nc - 1)
    out[c] = {}
    for k = 0, nb do out[c][k + 1] = { x, y - bend * k * k, z - seg * k } end
  end
  return out
end
local chest = R0.chest
local cape_rest = sheet(5, 5, -0.17, 0.17, chest[2] - 0.17, chest[3] + 0.08, 0.17, 0.004)
local head = R0.head
local hair_rest = sheet(3, 5, -0.06, 0.06, head[2] - 0.11, head[3] + 0.06, 0.1, 0.003)

local function lengths(pts) local L = {}; for k = 2, #pts do L[k - 1] = Chain.len(Chain.sub(pts[k], pts[k - 1])) end; return L end
local parts = {
  { name = 'skirt', bone = 'hips', rest = skirt_rest, open = false, legs = true },
  { name = 'cape', bone = 'chest', rest = cape_rest, open = true },
}
for _, pt in ipairs(parts) do
  pt.S = Skirt.new(#pt.rest, lengths(pt.rest[1])); pt.S.open = pt.open
  for c = 1, #pt.rest do pt.S.chains[c].L = lengths(pt.rest[c]) end
end
local hairs = {}
for c = 1, #hair_rest do hairs[c] = { rest = hair_rest[c], ch = Chain.new(lengths(hair_rest[c])) } end

local function joints(f) local J = {}; for k, v in pairs(f) do J[k] = { v[1], v[2], v[3] } end; return J end
local marks, mi = SEQ.marks, 1
local stats, cur = {}, nil
local function newstat(name) return { name = name, inside = 0, inside_n = 0, below = 0, speed = 0, nan = 0, frames = 0, worst_at = '' } end
local all = newstat('all')
local prev_rel = {}
local t_cost = 0
local dt = 1 / 60
local GROUND = {}
local CONTACT = {}
for fi, f in ipairs(SEQ.frames) do
  if marks[mi] and marks[mi][1] == fi then cur = newstat(marks[mi][2]); stats[#stats + 1] = cur; mi = mi + 1 end
  local J = joints(f)
  local caps = Body.capsules(J, P)
  -- the ground: z = 0, or lower where the move itself goes lower (the knock-down reaches 55 cm down a slope)
  local GJ = {}; for _, nm in ipairs(Body.JOINTS) do GJ[nm] = J[nm] end    -- the game's joints (no toes) for the floor
  local ground = Body.floor(GJ, { FLOOR = 0 })    -- the body's lowest surface this frame: the ground can't be higher
  local full = Body.capsules(J, { MARGIN = P.MARGIN })   -- scored against the WHOLE body, whatever this run collides with
  local floor = SAFE ~= 0 and Body.ground(GROUND, GJ, P, dt) or nil
  local legs = { { hip = J.l_thigh, knee = J.l_knee }, { hip = J.r_thigh, knee = J.r_knee } }
  local t0 = os.clock()
  local outs = {}
  for _, pt in ipairs(parts) do
    local A, T = {}, {}
    for c, pts in ipairs(pt.rest) do
      A[c] = carry(f, pt.bone, pts[1]); T[c] = {}
      for k = 2, #pts do T[c][k - 1] = carry(f, pt.bone, pts[k]) end
    end
    if not pt.score then pt.score = Body.fit(Body.capsules(J, { MARGIN = 0 }), A, { MARGIN = 0 }) end
    if not pt.ignore then pt.ignore = Body.fit(caps, A, setmetatable({ BODY_FIT = FIT }, { __index = P })) end
    local mine = Body.apply(caps, pt.ignore)
    local TF = pt.legs and Skirt.leg_follow(pt.S, A, T, legs, xyzw(f, 'hips'), dt, P) or T
    Skirt.step(pt.S, A, TF, dt, P, mine, floor)
    if PROBE and fi == 505 and pt.name == 'skirt' then
      for _, k in ipairs(mine) do if k.name == 'l_thigh' then
        print(string.format('PROBE2 hem 10/6: out %.1f cm, sim state %.1f cm from the thigh surface; caps in step %d', 100 * (Body.dist_to(k, pt.S.out[10][6]) - k.r),
          100 * (Body.dist_to(k, pt.S.chains[10].p[6]) - k.r), #mine))
      end end
      for _, k in ipairs(caps) do if k.name == 'l_thigh' then print('PROBE2 frame thigh', k.a[1], k.a[2], k.a[3], k.b[1], k.b[2], k.b[3], k.r) end end
    end
    for c = 1, #pt.rest do outs[#outs + 1] = { pts = pt.S.out[c], caps = Body.apply(full, pt.score), key = pt.name .. c, rest = T[c] } end
  end
  for c, h in ipairs(hairs) do
    local a = carry(f, 'head', h.rest[1]); local tg = {}
    for k = 2, #h.rest do tg[k - 1] = carry(f, 'head', h.rest[k]) end
    if not h.score then h.score = Body.fit(Body.capsules(J, { MARGIN = 0 }), { a }, { MARGIN = 0 }) end
    if not h.ignore then h.ignore = Body.fit(caps, { a }, setmetatable({ BODY_FIT = FIT }, { __index = TP })) end
    local mine = Body.apply(caps, h.ignore)
    Chain.step(h.ch, a, tg, dt, TP, mine, floor)
    outs[#outs + 1] = { pts = h.ch.out, caps = Body.apply(full, h.score), key = 'hair' .. c, rest = tg }
  end
  t_cost = t_cost + (os.clock() - t0)
  -- score this frame
  for _, o in ipairs(outs) do
    for j, p in ipairs(o.pts) do
      local s = cur
      if p[1] ~= p[1] or p[2] ~= p[2] or p[3] ~= p[3] then s.nan = s.nan + 1; all.nan = all.nan + 1
      else
        for _, k in ipairs(o.caps) do
          local d = k.r - Body.dist_to(k, p)
          if d > 0.005 then s.inside_n = s.inside_n + 1; all.inside_n = all.inside_n + 1 end
          if d > -P.MARGIN - 0.002 then CONTACT[k.name] = (CONTACT[k.name] or 0) + 1 end
          if d > s.inside then s.inside = d; s.worst_at = o.key .. '/' .. j .. ' in ' .. k.name end
          if d > all.inside then all.inside = d; all.worst_at = cur.name .. ' ' .. o.key .. '/' .. j .. ' in ' .. k.name end
          if PROBE and d > 0.05 and not PROBED then
            PROBED = true
            local ds = {}
            for _, k2 in ipairs(o.caps) do ds[#ds + 1] = string.format('%s %.1f', k2.name, 100 * (Body.dist_to(k2, p) - k2.r)) end
            local lt, rt = J.l_thigh, J.r_thigh
            local lk, rk = J.l_knee, J.r_knee
            print(string.format('PROBE frame %d %s %s/%d: clearance to every collider (cm): %s', fi, cur.name, o.key, j, table.concat(ds, ', ')))
            print(string.format('PROBE knees %.2f m apart, thighs %.2f m apart; hips z %.2f; hips speed %.1f m/s', Chain.len(Chain.sub(lk, rk)), Chain.len(Chain.sub(lt, rt)), f.hips[3],
              fi > 1 and Chain.len(Chain.sub(f.hips, SEQ.frames[fi - 1].hips)) * 60 or 0))
          end
        end
        local b = ground - p[3]
        if b > s.below then s.below = b end; if b > all.below then all.below = b end
        local base = o.rest[j]                        -- against its own rest place (the body's motion taken out)
        local rel = { p[1] - base[1], p[2] - base[2], p[3] - base[3] }
        local key = o.key .. j
        if prev_rel[key] then
          local v = Chain.len(Chain.sub(rel, prev_rel[key])) / dt
          if v > s.speed then s.speed = v; s.fast_at = o.key .. '/' .. j .. ' frame ' .. fi end; if v > all.speed then all.speed = v end
        end
        prev_rel[key] = rel
      end
    end
  end
  cur.frames = cur.frames + 1; all.frames = all.frames + 1
end
local function line(s)
  return string.format('%-11s deepest inside %4.1f cm (%s), %4d joint-frames >0.5 cm in, below the body\'s lowest surface %4.1f cm, fastest %5.1f m/s vs its rest place%s',
    s.name, 100 * s.inside, s.worst_at ~= '' and s.worst_at or '-', s.inside_n, 100 * math.max(0, s.below), s.speed, (s.fast_at and (' [' .. s.fast_at .. ']') or '') .. (s.nan > 0 and (' NaN ' .. s.nan) or ''))
end
for _, s in ipairs(stats) do print('stress: ' .. line(s)) end
print('stress: ' .. line(all))
print(string.format('stress: SAFE=%d, %d frames, %.2f ms per frame (skirt 12x6 + cape 5x5 + 3 hair strands, %d colliders)',
  SAFE, all.frames, 1000 * t_cost / all.frames, #Body.capsules(joints(SEQ.frames[1]), P)))
local cn = {}; for k, v in pairs(CONTACT) do cn[#cn + 1] = string.format('%s %d', k, v) end; table.sort(cn)
print('stress: cloth touching (joint-frames within the clearance): ' .. (#cn > 0 and table.concat(cn, ', ') or 'none'))
