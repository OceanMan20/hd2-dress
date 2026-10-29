-- Offline tests for mod/lib/blast.lua: the explosion queue reader on fake memory (right build, wrong
-- build, changed code, unreadable, garbage) and the shock wave on a real skirt.
-- Run from the repo root: luajit tools/test_blast.lua
local Chain = assert(loadfile('mod/lib/chain.lua'))()
local Skirt = assert(loadfile('mod/lib/skirt.lua'))()(Chain)
local Blast = assert(loadfile('mod/lib/blast.lua'))()
local K = Blast.PIN
local out = {}

-- fake memory: regions { [start] = string }; a read outside every region fails (like ReadProcessMemory)
local function le(n, bytes) local t = {}; for i = 1, bytes do t[i] = string.char(n % 256); n = math.floor(n / 256) end; return table.concat(t) end
local function f32b(v)    -- float -> 4 bytes (normal numbers only, enough for the test)
  if v == 0 then return le(0, 4) end
  local sign = v < 0 and 1 or 0; v = math.abs(v)
  local e = math.floor(math.log(v) / math.log(2)); local m = v / 2 ^ e - 1
  if m < 0 then e = e - 1; m = v / 2 ^ e - 1 end
  return le(sign * 2147483648 + (e + 127) * 8388608 + math.floor(m * 8388608 + 0.5), 4)
end
local BASE, Q = 0x7000000000, 0x202DEDB78
local function make_mem(opts)
  opts = opts or {}
  local hdr = { 'MZ', string.rep('\0', 58), le(128, 4), string.rep('\0', 128 - 64), 'PE\0\0', string.rep('\0', 4),
                le(opts.stamp or K.build, 4), string.rep('\0', 80 - 12), le(opts.size or K.image_size, 4) }
  local h = table.concat(hdr); h = h .. string.rep('\0', 4096 - #h)
  local regions = {
    [BASE] = h,
    [BASE + K.request_rva] = opts.code or K.request_bytes,
    [BASE + K.queue_rva] = le(opts.queue or Q, 8),
    [Q + K.count] = string.rep('\0', 8 + K.capacity * K.stride),
  }
  local mem = { base = BASE }
  function mem.read(a, n)
    if opts.dead then return nil end
    for start, s in pairs(regions) do
      if a >= start and a + n <= start + #s then return s:sub(a - start + 1, a - start + n) end
    end
    return nil
  end
  function mem.put_entry(slot, x, y, z, ty, src, own, cr)
    local e = f32b(x) .. f32b(y) .. f32b(z) .. le(ty, 4) .. le(src, 4) .. le(own, 4) .. le(cr or 0, 8)
    e = e .. string.rep('\0', K.stride - #e)
    local s = regions[Q + K.count]
    local at = 8 + slot * K.stride
    regions[Q + K.count] = s:sub(1, at) .. e .. s:sub(at + K.stride + 1)
  end
  function mem.put_header(count, kicked)
    local s = regions[Q + K.count]
    regions[Q + K.count] = le(count, 4) .. le(kicked, 4) .. s:sub(9)
  end
  return mem
end

-- 1. open: the right build opens; anything else is refused with a reason
local mem = make_mem()
local B, why = Blast.open(mem)
assert(B, 'the right build opens: ' .. tostring(why))
local _, w1 = Blast.open(make_mem({ stamp = 0x6B000000 })); assert(w1 and w1:find('waves off'), 'a patched game.dll is refused: ' .. tostring(w1))
local _, w2 = Blast.open(make_mem({ code = string.rep('\x90', #K.request_bytes) })); assert(w2 and w2:find('differs'), 'changed code is refused: ' .. tostring(w2))
local _, w3 = Blast.open(make_mem({ dead = true })); assert(w3, 'unreadable memory is refused')
assert(not Blast.open(nil) and not Blast.open({ base = 0 }), 'no game.dll is refused')
out[#out + 1] = 'open: right build yes; patch / changed code / unreadable refused'

-- 2. poll: old blasts at start are not new; each new one is seen once; garbage is ignored
mem.put_entry(0, 136.6, -97.7, 15.0, 394, 525, 525)                  -- left over from before
assert(#Blast.poll(B, 0) == 0, 'the first read only learns what is there')
assert(#Blast.poll(B, 0.016) == 0, 'nothing new')
mem.put_entry(0, 144.4, -55.8, 16.4, 125, 543, 543, 0x328D23279170E9AB) -- a Hellbomb
local l = Blast.poll(B, 0.033)
assert(#l == 1 and l[1].type == 125 and math.abs(l[1].x - 144.4) < 1e-3 and math.abs(l[1].z - 16.4) < 1e-3, 'the Hellbomb is seen')
assert(#Blast.poll(B, 0.05) == 0, 'once only')
mem.put_entry(0, 157.4, -41.4, 16.9, 193, 561, 507); mem.put_entry(1, 157.4, -41.3, 16.7, 277, 561, 507)
l = Blast.poll(B, 1.0)
assert(#l == 2 and l[1].type == 193 and l[2].type == 277, 'two in one frame (500 kg impact + blast)')
mem.put_entry(0, 0 / 0 == 0 / 0 and 1e30 or 1e30, 0, 0, 125, 1, 1)    -- absurd position
mem.put_entry(1, 10, 10, 10, 9999, 1, 1)                             -- type out of range
assert(#Blast.poll(B, 1.1) == 0, 'garbage entries are ignored')
mem.put_header(5000, 0)
mem.put_entry(0, 1, 2, 3, 125, 9, 9)
assert(#Blast.poll(B, 1.2) == 0 and B.bad > 0, 'an insane count makes the read count as bad, nothing returned')
mem.put_header(0, 0)
local dead = make_mem({ dead = true }); local Bd = { mem = dead, prev = {}, recent = {}, reads = 0, bad = 0 }
assert(#Blast.poll(Bd, 0) == 0 and Bd.bad == 1, 'unreadable memory later: nothing, no error')
out[#out + 1] = 'poll: old blasts skipped, new ones once, two per frame, garbage ignored'

-- 3. the wave: a Hellbomb 50 m away reaches you after 50 / 150 s and PUSHES for BLAST_PUSH s, away and up
local P1 = { BLAST_SCALE = 1, BLAST_PUSH = 0.15 }
local w = Blast.wave({ x = 0, y = 0, z = 0, type = 125 }, 0, P1)
local p = { 50, 0, 1 }
local ta = math.sqrt(50 ^ 2 + 1) / 150
assert(Blast.dv({ w }, p, 0, ta - 0.01, P1) == nil, 'not yet')
local function mag(d) return d and math.sqrt(d[1] ^ 2 + d[2] ^ 2 + d[3] ^ 2) or 0 end
local whole = Blast.dv({ w }, p, ta - 0.01, ta + 0.2, P1)
local half = Blast.dv({ w }, p, ta, ta + 0.075, P1)
local want = 14 * (1 - math.sqrt(2501) / 120) ^ 2
assert(whole[1] > 0 and whole[3] > 0 and math.abs(mag(whole) - want) < 0.01, string.format('away and up, %.2f m/s in all (want %.2f)', mag(whole), want))
assert(math.abs(mag(half) - want / 2) < 0.01, 'spread over the push: half the time, half the push')
assert(Blast.dv({ w }, p, ta + 0.2, ta + 0.3, P1) == nil, 'over once the push has passed')
assert(Blast.dv({ w }, { 130, 0, 0 }, 0, 10, P1) == nil, 'beyond its reach: nothing')
local small = Blast.wave({ x = 0, y = 0, z = 0, type = 224 }, 0, P1)
assert(small.R == 15 and Blast.wave({ type = 999, x = 0, y = 0, z = 0 }, 0, P1).R == 25, 'grenade small, unknown types modest')
assert(#Blast.prune({ w, small }, 1.0) == 1, 'the grenade wave is done, the Hellbomb travels on')
assert(Blast.wave({ x = 0, y = 0, z = 0, type = 125 }, 0, { BLAST_SCALE = 0 }) == nil, 'BLAST_SCALE 0 = off')
local capped = Blast.dv({ Blast.wave({ x = 0, y = 0, z = 0, type = 125 }, 0, { BLAST_SCALE = 10 }) }, { 5, 0, 0 }, 0, 1, { BLAST_MAX_DV = 20 })
assert(math.abs(mag(capped) - 20) < 1e-6, 'capped at BLAST_MAX_DV')
out[#out + 1] = string.format('wave: Hellbomb at 50 m pushes %.1f m/s over 0.15 s, %.2f s after the blast', want, ta)

-- 3b. step rate switched (60 -> 240 Hz): the cloth's speed is the same right across the switch (no
--     jolt). The faster steps damp a little less (the length correction loses less energy per step),
--     so while a wave passes the cloth is livelier; that is fine for a blast and lasts about a second.
do
  local c = Chain.new({ 0.2, 0.2 }); local a = { 0, 0, 1 }
  local tg = { { 0, 0, 0.8 }, { 0, 0, 0.6 } }
  Chain.step(c, a, tg, 1 / 60, { SUBSTEP_HZ = 60 })
  c.pp[2] = { c.p[2][1] - 0.03, c.p[2][2], c.p[2][3] }
  for _ = 1, 5 do Chain.step(c, a, tg, 1 / 60, { SUBSTEP_HZ = 60, DAMPING = 0.05 }) end
  local v60 = (c.p[2][1] - c.pp[2][1]) / c.h
  Chain.rate(c, 1 / 240)
  local v240 = (c.p[2][1] - c.pp[2][1]) / c.h
  assert(math.abs(v60 - v240) < 1e-9 and v60 ~= 0, 'same speed across the switch: ' .. v60 .. ' / ' .. v240)
  for _ = 1, 120 do Chain.step(c, a, tg, 1 / 60, { SUBSTEP_HZ = 240, DAMPING = 0.05 }) end
  for _ = 1, 600 do Chain.step(c, a, tg, 1 / 60, { SUBSTEP_HZ = 60, DAMPING = 0.05 }) end
  assert(math.abs(c.out[2][1]) < 0.005, 'and it settles after going back to 60 Hz: ' .. c.out[2][1])
  out[#out + 1] = string.format('fast steps: speed %.2f m/s kept across the switch, settles after', v60)
end

-- 4. on a real skirt: it flares away from the blast and settles back; lengths hold; no NaN
local nc, L = 12, { 0.12, 0.12, 0.12, 0.12, 0.12 }
local S = Skirt.new(nc, L)
local A, T = {}, {}
for c = 1, nc do
  local a = 2 * math.pi * (c - 1) / nc
  A[c] = { 0.17 * math.cos(a), 0.17 * math.sin(a), 1.0 }
  T[c] = {}; for j = 1, #L do T[c][j] = { (0.17 + 0.03 * j) * math.cos(a), (0.17 + 0.03 * j) * math.sin(a), 1.0 - 0.12 * j } end
end
local P = { MARGIN = 0.03, BLAST_SCALE = 1 }
local waves = { Blast.wave({ x = -30, y = 0, z = 0.5, type = 125 }, 0.2, P) }   -- a Hellbomb 30 m to the -x side
local function hem_x() local s = 0; for c = 1, nc do s = s + S.out[c][#L][1] end; return s / nc end
local t, dt, rest_x, peak = 0, 1 / 60, nil, 0
for f = 1, 300 do
  local t0 = t; t = t + dt
  if f == 10 then rest_x = hem_x() end
  if S.chains[1].p then Blast.kick_skirt(S, waves, t0, t, P, dt) end
  Skirt.step(S, A, T, dt, P)
  if rest_x then peak = math.max(peak, hem_x() - rest_x) end
  for c = 1, nc do for j = 1, #L do local q = S.out[c][j]; assert(q[1] == q[1] and q[3] == q[3], 'no NaN') end end
end
local final = hem_x() - rest_x
assert(peak > 0.05, 'the hem is blown away from the blast (+x): ' .. peak)
assert(math.abs(final) < 0.01, 'and settles back: ' .. final)
for c = 1, nc do
  local prev = A[c]
  for j = 1, #L do local q = S.out[c][j]; assert(math.abs(Chain.len(Chain.sub(q, prev)) - L[j]) < 0.02, 'lengths hold'); prev = q end
end
out[#out + 1] = string.format('skirt: hem blown %.0f cm away from a Hellbomb at 30 m, settled to %.1f mm', 100 * peak, 1000 * math.abs(final))

-- 5. a strong Hellbomb 60 m beside the real Arknight skirt (sim/work/ark_stocky.lua) on the real leg
--    colliders, with the push and fast steps: the hem flies far, the simulated cloth stays out of the
--    legs, no NaN. (2026-10-17: in game a 20 m/s kick at MAX_SPEED 25 showed the dress through both
--    legs; in this solver even that setting keeps the simulated surface outside, so what showed was
--    most likely the visible mesh, fuller than the surface between the bones. Strength is the lever.)
do
  local Body = assert(loadfile('mod/lib/body.lua'))()
  local rest = assert(loadfile('sim/work/ark_stocky.lua'))()
  local n2 = #rest
  local A2, T2, S2 = {}, {}, nil
  for c = 1, n2 do A2[c] = rest[c][1]; T2[c] = {}; for kk = 2, #rest[c] do T2[c][kk - 1] = rest[c][kk] end end
  local function lens(c) local Lc = {}; for kk = 2, #rest[c] do Lc[kk - 1] = Chain.len(Chain.sub(rest[c][kk], rest[c][kk - 1])) end; return Lc end
  S2 = Skirt.new(n2, lens(1)); for c = 1, n2 do S2.chains[c].L = lens(c) end
  local J = { l_thigh = { -0.087, -0.019, 0.942 }, l_knee = { -0.144, -0.034, 0.516 }, l_foot = { -0.191, -0.118, 0.104 },
              r_thigh = { 0.087, -0.019, 0.942 }, r_knee = { 0.144, -0.034, 0.516 }, r_foot = { 0.191, -0.118, 0.104 } }
  local legs = Body.capsules(J, { BODY_COLLIDE = 0 })
  local PB = { MARGIN = 0.03, BLAST_SCALE = 5, BLAST_MAX_DV = 20, BLAST_PUSH = 0.15 }
  local wv = { Blast.wave({ x = 60, y = 0, z = 0.5, type = 125 }, 0.1, PB) }
  local tt, worst, moved, hem0 = 0, 0, 0, nil
  for f = 1, 150 do
    local t0 = tt; tt = tt + 1 / 60
    local PP = {}; for k2, v in pairs(PB) do PP[k2] = v end
    if tt > 0.3 and tt < 1.2 then PP.SUBSTEP_HZ = 240; PP.MAX_SPEED = 30 end
    if S2.chains[1].p then Blast.kick_skirt(S2, wv, t0, tt, PP, 1 / (PP.SUBSTEP_HZ or 60)) end
    Skirt.step(S2, A2, T2, 1 / 60, PP, legs)
    if f == 3 then hem0 = {}; for c = 1, n2 do hem0[c] = S2.out[c][#T2[c]] end end
    for c = 1, n2 do for j2 = 1, #T2[c] do
      local q = S2.out[c][j2]
      assert(q[1] == q[1] and q[2] == q[2] and q[3] == q[3], 'no NaN')
      for _, lg in ipairs(legs) do worst = math.max(worst, lg.r - Body.dist_to(lg, q)) end
      if hem0 and j2 == #T2[c] then moved = math.max(moved, Chain.len(Chain.sub(q, hem0[c]))) end
    end end
  end
  assert(moved > 0.3, 'the hem flies: ' .. moved)
  assert(worst < 0.005, 'the simulated cloth stays out of the legs: ' .. worst)
  out[#out + 1] = string.format('real skirt, strong Hellbomb at 60 m: hem flies %.0f cm, %.1f mm into a leg at worst', 100 * moved, 1000 * math.max(0, worst))
end

print('test_blast: ok (' .. table.concat(out, '; ') .. ')')
