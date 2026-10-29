-- Offline tests for mod/lib/chain.lua. Run from the repo root: luajit tools/test_chain.lua
local Chain = assert(loadfile('mod/lib/chain.lua'))()
local L = { 0.2, 0.2 }
local function targets_for(a) return { { a[1], a[2], a[3] - 0.2 }, { a[1], a[2], a[3] - 0.4 } } end
local function tip_angle(c, a)   -- degrees of the whole chain from straight down
  local d = Chain.sub(c.out[2], a); local l = Chain.len(d)
  return math.deg(math.acos(math.max(-1, math.min(1, -d[3] / l))))
end
local function lengths_ok(c, a)
  return math.abs(Chain.len(Chain.sub(c.out[1], a)) - 0.2) < 1e-9 and math.abs(Chain.len(Chain.sub(c.out[2], c.out[1])) - 0.2) < 1e-9
end

-- 1. at rest it stays at rest
local c = Chain.new(L)
local a = { 0, 0, 1 }
for _ = 1, 600 do Chain.step(c, a, targets_for(a), 1 / 60) end
assert(tip_angle(c, a) < 1e-6 and lengths_ok(c, a), 'rest stays rest')

-- 2. walk sideways for 1 s at 1.5 m/s, then stop: lags, then settles
-- returns: max angle while moving, angle 0.3 s after the stop, angle 3 s after the stop
local function run(fps)
  local ch = Chain.new(L); local an = { 0, 0, 1 }
  Chain.step(ch, an, targets_for(an), 1 / fps)
  local dt, t, maxa, a03, a3 = 1 / fps, 0, 0, nil, nil
  while t < 4 do
    t = t + dt
    if t <= 1 then an = { an[1] + 1.5 * dt, 0, 1 } end
    Chain.step(ch, an, targets_for(an), dt)
    assert(lengths_ok(ch, an), 'lengths exact at ' .. fps .. ' fps')
    local ang = tip_angle(ch, an)
    if t <= 1 then maxa = math.max(maxa, ang) end
    if not a03 and t >= 1.3 then a03 = ang end
    if not a3 and t >= 4 - 1e-9 then a3 = ang end
  end
  return maxa, a03, a3 or tip_angle(ch, an)
end
local m60, s60, e60 = run(60)
assert(m60 > 5, 'lags behind while walking: ' .. m60)
assert(e60 < 1, 'settles after stopping: ' .. e60)
local m17, s17, e17 = run(17)
local m144, s144, e144 = run(144)
local tol = math.max(0.3 * m60, 4)   -- degrees; drawing between fixed physics steps wobbles a little
assert(math.abs(m17 - m60) < tol and math.abs(m144 - m60) < tol,
  string.format('frame-rate independent sway: 17 fps %.1f, 60 fps %.1f, 144 fps %.1f', m17, m60, m144))
assert(e17 < 1 and e144 < 1, 'settles at any frame rate')

-- 3. cone limit holds under a violent jerk
c = Chain.new(L); a = { 0, 0, 1 }
Chain.step(c, a, targets_for(a), 1 / 60)
local P = { MAX_ANGLE = 60, STIFFNESS = 0, DAMPING = 0, TELEPORT = 10 }
for i = 1, 30 do a = { a[1] + 0.5, 0, 1 }; Chain.step(c, a, targets_for(a), 1 / 60, P)
  local d = Chain.sub(c.out[1], a); assert(math.deg(math.acos(-d[3] / Chain.len(d))) <= 60 + 1e-6, 'cone limit') end

-- 4. a teleport (mission load, respawn) resets instead of whipping
c = Chain.new(L); a = { 0, 0, 1 }
Chain.step(c, a, targets_for(a), 1 / 60)
a = { 50, 0, 1 }; Chain.step(c, a, targets_for(a), 1 / 60)
assert(tip_angle(c, a) < 1e-6 and c.resets == 2, 'teleport resets')

-- 5. FOLLOW = 1 carries the chain rigidly: no lag
local function maxlag(follow)
  local ch = Chain.new(L); local an = { 0, 0, 1 }; local mx = 0
  Chain.step(ch, an, targets_for(an), 1 / 60)
  for _ = 1, 60 do an = { an[1] + 0.025, 0, 1 }; Chain.step(ch, an, targets_for(an), 1 / 60, { FOLLOW = follow }); mx = math.max(mx, tip_angle(ch, an)) end
  return mx
end
assert(maxlag(1) < 1e-6 and maxlag(0) > 5, 'FOLLOW')
-- 6. a leg capsule swinging through the chain pushes it out (milestone 4)
c = Chain.new(L); a = { 0, 0, 1 }
Chain.step(c, a, targets_for(a), 1 / 60)
local min_d, min_tip = 1, 1
for i = 0, 60 do   -- a thigh-sized capsule sweeps from behind the chain to in front of it, crossing it
  local y = 0.3 - i * 0.01
  local cap = { { a = { -0.2, y, 0.75 }, b = { 0.2, y, 0.75 }, r = 0.08 } }
  Chain.step(c, a, targets_for(a), 1 / 60, nil, cap)
  for j = 1, 2 do
    local p = c.out[j]
    local d = math.sqrt((p[2] - y) ^ 2 + (p[3] - 0.75) ^ 2)
    if math.abs(p[1]) <= 0.2 then min_d = math.min(min_d, d) end
  end
  min_tip = math.min(min_tip, c.out[2][2])
end
assert(min_d >= 0.08 + 0.01 - 1e-6, 'never inside the capsule: ' .. min_d)
assert(min_tip < -0.05, 'pushed along by the sweep (then slides off): tip y ' .. min_tip)
-- per-bone values (c.over): a very damped last bone lags less after a sideways jerk; no over = unchanged
local function sway_with(over, P)
  local ch = Chain.new(L); ch.over = over; local an = { 0, 0, 1 }
  Chain.step(ch, an, targets_for(an), 1 / 60, P)
  local mx = 0
  for f = 1, 40 do an = { an[1] + (f <= 20 and 0.03 or 0), 0, 1 }; Chain.step(ch, an, targets_for(an), 1 / 60, P); mx = math.max(mx, tip_angle(ch, an)) end
  return mx
end
local s_plain, s_empty = sway_with(nil), sway_with({})
local s_damped = sway_with({ [1] = { DAMPING = 0.9 }, [2] = { DAMPING = 0.9 } })
local s_heavy = sway_with({ [2] = { GRAVITY = 40 } })
assert(s_plain == s_empty, 'empty over changes nothing')
assert(s_damped < s_plain - 1, 'own DAMPING per bone takes effect: ' .. s_damped .. ' vs ' .. s_plain)
assert(s_heavy < s_plain - 1, 'own GRAVITY per bone takes effect: ' .. s_heavy .. ' vs ' .. s_plain)
assert(sway_with(nil, { MUL_DAMPING = 5 }) < s_plain - 1, 'the player multiplier scales it')
print(string.format('test_chain: ok (sway 17/60/144 fps: %.1f/%.1f/%.1f deg; 0.3 s after stop %.1f deg; settled %.2f deg)', m17, m60, m144, s60, e60))
