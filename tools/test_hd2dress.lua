-- Offline test of mod/hd2dress.lua (gating test addon) against a fake engine.
-- Run from the repo root: luajit tools/test_hd2dress.lua
-- Scenarios: the engine leaves the added bone alone (writes must read back as 'kept'), and the
-- engine resets it to rest every frame (must read back as 'reset'). Also: key cycling, world change.
local lines, trace, beat, settings_file = {}, {}, '', nil
local real_open = io.open
io.open = function(path, mode)   -- capture the addon's log and trace instead of writing files
  if tostring(path):find('HD2Dress.log', 1, true) then
    return { write = function(_, s) for l in s:gmatch('[^\n]+') do lines[#lines + 1] = l end end, close = function() end }
  end
  if tostring(path):find('HD2Dress_heartbeat.txt', 1, true) then
    return { seek = function() beat = '' end, write = function(_, s) beat = beat .. s end, flush = function() end, close = function() end }
  end
  if tostring(path):find('HD2Dress_settings.txt', 1, true) then
    if mode == 'r' then
      if not settings_file then return nil end
      return { read = function() return settings_file end, close = function() end }
    end
    local buf = {}
    return { write = function(_, s) buf[#buf + 1] = s end, close = function() settings_file = table.concat(buf) end }
  end
  if tostring(path):find('HD2Dress_trace.csv', 1, true) then
    return { write = function(_, s) for l in s:gmatch('[^\n]+') do trace[#trace + 1] = l end end, flush = function() end, close = function() end }
  end
  return real_open(path, mode)
end
local real_getenv = os.getenv
os.getenv = function(k) if k == 'LOCALAPPDATA' then return 'C:\\fake' end return real_getenv(k) end

local function Q(x, y, z, w) return { qx = x, qy = y, qz = z, qw = w } end
local REST = Q(0, 0, 0.7071068, 0.7071068)
local rot = { test = REST, child = Q(0, 0, 0, 1), ctrl = REST, hips = Q(0, 0, 0, 1) }   -- test and control share a rest direction
local pos = { [1] = { x = 0, y = 0, z = 0 }, test = { x = -0.1, y = -0.17, z = 0.95 }, child = { x = -0.1, y = -0.17, z = 0.75 },
              ctrl = { x = 0.1, y = -0.17, z = 0.95 }, hips = { x = 0, y = -0.02, z = 0.97 } }
local world = 'world1'
local engine_resets = false
local pressed_now = false
local updates = 0
stingray = {
  Application = { main_world = function() return world end },
  Keyboard = { button_index = function(n) return n == 'home' and 36 or nil end, pressed = function() return pressed_now end },
  IdString64 = { from_hex = function(h) return h end },
  Vector3 = function(x, y, z) return { x = x, y = y, z = z } end,
  Quaternion = { to_elements = function(q) return q.qx, q.qy, q.qz, q.qw end, from_elements = function(x, y, z, w) return Q(x, y, z, w) end },
  World = { units_by_resource = function(w, hex)
              if w ~= world then error('wrong world') end
              if hex == '0387a158d04848f4' then return { 'hip' } end
              if hex == '4d1c334d294dfa97' then return { 'me' } end
              return {} end,
            update_unit = function(w, u) updates = updates + 1 end },
  Unit = { alive = function(u) return u == 'hip' end,
           has_node = function(u, n) return u == 'hip' and ({ dress_test_a = 1, dress_test_b = 1, dress_ctrl = 1, hips = 1 })[n] ~= nil end,
           node = function(u, n) return ({ dress_test_a = 'test', dress_test_b = 'child', dress_ctrl = 'ctrl', hips = 'hips' })[n] end,
           local_rotation = function(u, n) return rot[n] end,
           set_local_rotation = function(u, n, q) assert(u == 'hip' and (n == 'test' or n == 'child'), 'only the test chain is written'); rot[n] = q end,
           world_position = function(u, n) return pos[n] or pos[1] end,
           world_rotation = function(u, n) return rot[n] or Q(0, 0, 0, 1) end },   -- parent (hips) is identity: world = local
}
update = function() end
render = function() end
local f = assert(io.popen('python3 tools/pack.py expand mod/hd2dress.lua')); local src = f:read('*a'); f:close()   -- as shipped
assert(src:match('^%-%- HD2%-Addon: mods/oceanman/hd2dress\n'), 'first line must be the HD2-Addon header')
assert(loadstring(src))()

local t = 0
local function frame(key)
  pressed_now = key or false
  update(1 / 60)
  if engine_resets then rot.test = REST end   -- the "animation" between update and render
  render()
  t = t + 1 / 60
end
local function last(pat) for i = #lines, 1, -1 do if lines[i]:find(pat) then return lines[i] end end end
local function frames(n) for _ = 1, n do frame() end end

frames(130)                                   -- off: finds the piece, logs a baseline
assert(last('armour piece found'), 'found the piece')
assert(last('off: %d+ frames, kept 0, reset %d+, other 0'), 'off baseline: ' .. tostring(last('%[gate%] off')))
frame(true)                                   -- -> hold @render
frames(130)
local l = last('hold @render:')
assert(l and l:find('reset 0, other 0'), 'kept when the engine leaves it alone: ' .. tostring(l))
local kept = tonumber(l:match('kept (%d+)')); assert(kept and kept > 100, 'kept count: ' .. tostring(l))
assert(updates > 100, 'update_unit after the write')
local vs = last('vs the control flap'); assert(vs and vs:find('max 45%.0'), 'angle vs control: ' .. tostring(vs))
assert(trace[1]:find('^t,mode,target_deg,vs_control_deg'), 'trace header')
local cols = {}; for x in trace[#trace]:gmatch('[^,]+') do cols[#cols + 1] = tonumber(x) end
assert(#cols == 21 and cols[2] == 1 and math.abs(cols[4] - 45) < 0.01, 'trace row: ' .. trace[#trace])
-- 45 deg about the bone's x from REST
local qx, qy, qz, qw = rot.test.qx, rot.test.qy, rot.test.qz, rot.test.qw
local h = math.rad(45) / 2
assert(math.abs(qw - REST.qw * math.cos(h)) < 1e-6, 'w of rest * axis(45)')
assert(math.abs(qx - REST.qw * math.sin(h)) < 1e-6 and math.abs(qy - REST.qz * math.sin(h)) < 1e-6, 'x/y of rest * axis(45)')
engine_resets = true
frames(250)                                   -- two log windows: the second is all 'reset'
l = last('hold @render:')
assert(l and l:find('kept 0') and tonumber(l:match('reset (%d+)')) > 100, 'reset when the engine rewrites: ' .. tostring(l))
engine_resets = false
frame(true)                                   -- -> hold @update
frames(130)
l = last('hold @update:'); assert(l and l:find('reset 0, other 0'), 'update phase kept: ' .. tostring(l))
frame(true)                                   -- -> once
frames(130)
l = last('once %(write'); assert(l and l:find('writes 0') or l:find('writes 1'), 'once writes at most once per window: ' .. tostring(l))
assert(tonumber(l:match('kept (%d+)')) > 100, 'once: stays: ' .. tostring(l))
frame(true)                                   -- -> swing
frames(130)
l = last('swing @render:'); assert(l and l:find('reset 0'), 'swing: ' .. tostring(l))
assert(settings_file and settings_file:find('DAMPING=0.4'), 'settings file written with defaults')
assert(beat:find('^frame %d+ t [%d.]+ mode 4 stage render: done') and #beat == 96, 'heartbeat line: ' .. beat)
frame(true)                                   -- -> spring chain
assert(last('mode %-> SPRING CHAIN'), 'spring mode')
frames(60)                                    -- standing still: the chain hangs at rest
local function ang(q) local d = math.abs(q.qx * REST.qx + q.qy * REST.qy + q.qz * REST.qz + q.qw * REST.qw); return math.deg(2 * math.acos(math.min(1, d))) end
assert(ang(rot.test) < 0.5, 'chain at rest when still: ' .. ang(rot.test))
local x0 = pos.test.x
local swing = 0
for i = 1, 30 do pos.test = { x = x0 + i * 0.03, y = pos.test.y, z = pos.test.z }; frame(); swing = math.max(swing, ang(rot.test)) end   -- walk 1.8 m/s for 0.5 s
assert(swing > 3, 'chain lags behind when the body moves: ' .. swing)
frames(240)                                   -- stop: it settles
assert(ang(rot.test) < 1, 'chain settles: ' .. ang(rot.test))
settings_file = settings_file:gsub('DAMPING=0.4', 'DAMPING=0.3')
frames(150)
assert(last('settings changed: DAMPING=0.3'), 'live settings reload')
frame(true)                                   -- -> off: test chain back at rest
assert(rot.test.qw == REST.qw and rot.test.qz == REST.qz, 'back to rest when cycling')
world = 'world2'                              -- mission load: forget without calling into the old unit
frames(5)
assert(last('forgotten %(world changed%)'), 'world change handled')
for _, x in ipairs(lines) do if x:find('error') then error('addon error: ' .. x) end end
print('test_hd2dress: ok (' .. #lines .. ' log lines, ' .. #trace .. ' trace rows)')
