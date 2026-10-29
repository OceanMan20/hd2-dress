-- Offline test for mod/lib/skirt.lua: a leg capsule sweeping through the skirt must not pass through
-- the cloth BETWEEN chains (the 2026-10-15 bug: only the joints collided). Run: luajit tools/test_skirt.lua
local Chain = assert(loadfile('mod/lib/chain.lua'))()
local Skirt = assert(loadfile('mod/lib/skirt.lua'))()(Chain)
local NC, NS, L = 8, 3, 0.14
local function ring_at(cx, cy)
  local A, T = {}, {}
  for c = 1, NC do
    local a = 2 * math.pi * (c - 1) / NC
    A[c] = { cx + 0.2 * math.sin(a), cy + 0.2 * math.cos(a), 1.0 }
    T[c] = {}; for j = 1, NS do T[c][j] = { A[c][1], A[c][2], 1.0 - L * j } end
  end
  return A, T
end
local S = Skirt.new(NC, { L, L, L })
local A, T = ring_at(0, 0)
Skirt.step(S, A, T, 1 / 60)
-- a thigh-like capsule pointing forward, passing through the FRONT between chains 1 and 2 and
-- moving forward (+Y) from inside the skirt to well in front of it
local worst = 0
for i = 0, 50 do
  local y = 0.0 + i * 0.008
  local cap = { { a = { 0.08, y - 0.1, 0.8 }, b = { 0.08, y + 0.25, 0.8 }, r = 0.07 } }
  Skirt.step(S, A, T, 1 / 60, { MARGIN = 0.02, SAMPLES = 4 }, cap)
  -- measure the drawn surface finely
  for c = 1, NC do
    local c2 = c % NC + 1
    for j = 1, NS do
      local q = { j == 1 and A[c] or S.out[c][j - 1], j == 1 and A[c2] or S.out[c2][j - 1], S.out[c][j], S.out[c2][j] }
      for si = 0, 8 do for sj = (j == 1 and 1 or 0), 8 do
        local u, v = si / 8, sj / 8
        local w = { (1 - u) * (1 - v), u * (1 - v), (1 - u) * v, u * v }
        local x = { 0, 0, 0 }
        for k = 1, 4 do for d = 1, 3 do x[d] = x[d] + q[k][d] * w[k] end end
        local cp = cap[1]
        local ab = { cp.b[1] - cp.a[1], cp.b[2] - cp.a[2], cp.b[3] - cp.a[3] }
        local t = math.max(0, math.min(1, ((x[1] - cp.a[1]) * ab[1] + (x[2] - cp.a[2]) * ab[2] + (x[3] - cp.a[3]) * ab[3]) / (ab[1] ^ 2 + ab[2] ^ 2 + ab[3] ^ 2)))
        local dd = math.sqrt((x[1] - cp.a[1] - ab[1] * t) ^ 2 + (x[2] - cp.a[2] - ab[2] * t) ^ 2 + (x[3] - cp.a[3] - ab[3] * t) ^ 2)
        worst = math.max(worst, cp.r - dd)
      end end
    end
  end
end
assert(worst < 0.005, string.format('leg inside the cloth surface by %.1f cm', worst * 100))
-- the old joint-only chain does let it through (keeps the test honest)
local chains = {}; for c = 1, NC do chains[c] = Chain.new({ L, L, L }); Chain.step(chains[c], A[c], T[c], 1 / 60) end
local old = 0
for i = 0, 50 do
  local y = i * 0.008
  local cap = { { a = { 0.08, y - 0.1, 0.8 }, b = { 0.08, y + 0.25, 0.8 }, r = 0.07 } }
  for c = 1, NC do Chain.step(chains[c], A[c], T[c], 1 / 60, { MARGIN = 0.02 }, cap) end
  local c, c2 = 1, 2   -- centre of the front panel between levels 1 and 2 (no joint there)
  local x = { 0, 0, 0 }
  for _, pt in ipairs({ chains[c].out[1], chains[c2].out[1], chains[c].out[2], chains[c2].out[2] }) do
    for d = 1, 3 do x[d] = x[d] + pt[d] / 4 end
  end
  local cp = cap[1]
  local t = math.max(0, math.min(1, (x[2] - cp.a[2]) / (cp.b[2] - cp.a[2])))
  local dd = math.sqrt((x[1] - 0.08) ^ 2 + (x[2] - (cp.a[2] + (cp.b[2] - cp.a[2]) * t)) ^ 2 + (x[3] - 0.8) ^ 2)
  old = math.max(old, cp.r - dd)
end
assert(old > 0.02, 'the joint-only chains should leak here (else this test proves nothing): ' .. old)
print(string.format('test_skirt: ok (surface solver worst %.2f cm inside; joint-only chains %.1f cm)', worst * 100, old * 100))
