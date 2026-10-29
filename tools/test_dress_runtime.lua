-- Offline test of the generic dress runtime in mod/hd2dress.lua against a fake engine: a registered
-- 6x3 dress, the avatar's legs, body motion. Run from the repo root: luajit tools/test_dress_runtime.lua
local lines = {}
local real_open = io.open
io.open = function(path, mode)
  local p = tostring(path)
  if p:find('HD2Dress', 1, true) then
    return { write = function(_, s) if p:find('HD2Dress.log', 1, true) then for l in s:gmatch('[^\n]+') do lines[#lines + 1] = l end end end,
             read = function() if p:find('settings', 1, true) then return SETTINGS_TEXT end return nil end, seek = function() end, flush = function() end, close = function() end }
  end
  return real_open(path, mode)
end
os.getenv = (function(g) return function(k) if k == 'LOCALAPPDATA' then return 'C:\\fake' end return g(k) end end)(os.getenv)
local function Q(x, y, z, w) return { qx = x, qy = y, qz = z, qw = w } end
local NC, NB = 6, 3
local off = { 0, 0, 0 }                          -- where the body is (moves the hips + anchors + legs)
local rest_pos, rot = {}, {}
rest_pos.hips = { 0, 0, 0.95 }
for c = 1, NC do
  local a = 2 * math.pi * (c - 1) / NC
  for k = 1, NB do rest_pos[string.format('dress_c%02d_b%d', c, k)] = { 0.3 * math.sin(a), 0.3 * math.cos(a), 0.93 - 0.15 * (k - 1) } end   -- wider than thigh + clearance
end
for k = 1, 4 do rest_pos[string.format('dress_t01_b%d', k)] = { 0, -0.3 - 0.15 * (k - 1), 1.0 - 0.1 * (k - 1) } end
-- a second piece: a "helmet" with one hair chain hanging from the head
local helm_pos = { head = { 0, 0, 1.7 } }
for k = 1, 4 do helm_pos[string.format('dress_t01_b%d', k)] = { 0, -0.12, 1.65 - 0.12 * (k - 1) } end
local legs = { l_thigh = { -0.09, 0, 0.94 }, l_knee = { -0.12, 0, 0.5 }, l_foot = { -0.15, 0, 0.1 },
               r_thigh = { 0.09, 0, 0.94 }, r_knee = { 0.12, 0, 0.5 }, r_foot = { 0.15, 0, 0.1 },
               hips = { 0, 0, 0.97 }, spine1 = { 0, 0, 0.97 }, neck = { 0, 0, 1.55 }, head = { 0, 0, 1.69 },
               l_shoulder = { -0.21, 0, 1.47 }, l_elbow = { -0.3, 0, 1.2 }, l_hand = { -0.33, 0, 0.95 },
               r_shoulder = { 0.21, 0, 1.47 }, r_elbow = { 0.3, 0, 1.2 }, r_hand = { 0.33, 0, 0.95 } }
-- a third piece, the 0.7 format: a coat with an open cape (SHEET) from the chest and an outer skirt
-- layer (RING, layer 1) from the hips
local coat_pos = { chest = { 0, 0, 1.35 }, hips = { 0, 0, 0.95 } }
for c = 1, 3 do for k = 1, 3 do coat_pos[string.format('dress_cape_c%02d_b%d', c, k)] = { -0.12 + 0.12 * (c - 1), 0.17, 1.42 - 0.2 * (k - 1) } end end
for c = 1, NC do
  local a = 2 * math.pi * (c - 1) / NC
  for k = 1, NB do coat_pos[string.format('dress_outer_c%02d_b%d', c, k)] = { 0.34 * math.sin(a), 0.34 * math.cos(a), 0.95 - 0.15 * (k - 1) } end
end
local writes = 0
respawned = false
local dead = {}           -- units the "game" deleted: any call but alive() = a native crash
local crashes = 0        -- calls into deleted units (in the real game the first one crashes it)
local function live(u) if dead[u] then crashes = crashes + 1 end end
stingray = {
  Application = { main_world = function() return 'w' end },
  Keyboard = { button_index = function(n) return ({ home = 1, ['end'] = 2 })[n] end, pressed = function() return false end },
  IdString64 = { from_hex = function(h) return h end },
  Vector3 = function(x, y, z) return { x = x, y = y, z = z } end,
  Quaternion = { to_elements = function(q) return q.qx, q.qy, q.qz, q.qw end, from_elements = function(x, y, z, w) return Q(x, y, z, w) end },
  World = { units_by_resource = function(_, hex)   -- like the engine: deleted units are not listed
              if hex == 'abc' and not dead['dress'] and not respawned then return { 'dress' } end
              if hex == 'hhh' and not dead['helm'] then return { 'helm' } end
              if hex == 'ccc' and not dead['coat'] then return { 'coat' } end
              if hex == 'abc' and respawned and not dead['dress'] then return { 'dress', 'dress2' } end
              if hex == '4d1c334d294dfa97' and not dead['me'] then return respawned and { 'me', 'me2' } or { 'me' } end
              return {} end,
            update_unit = function() end },
  Unit = {
    alive = function(u) return not dead[u] end,
    has_node = function(u, n) if u == 'dress' or u == 'dress2' then return rest_pos[n] ~= nil end if u == 'me2' then return legs[n] ~= nil end if u == 'helm' then return helm_pos[n] ~= nil end if u == 'coat' then return coat_pos[n] ~= nil end if u == 'me' then return legs[n] ~= nil end return false end,
    node = function(u, n) return n end,
    local_rotation = function(u, n) live(u); return rot[n] or Q(0, 0, 0, 1) end,
    set_local_rotation = function(u, n, q) live(u); assert((u == 'dress' or u == 'dress2' or u == 'helm' or u == 'coat') and n:find('^dress_'), 'writes only dress bones'); if u ~= 'dress' then n = u .. ':' .. n end; rot[n] = q; writes = writes + 1 end,
    world_rotation = function() return Q(0, 0, 0, 1) end,
    world_position = function(u, n)
      live(u)
      if u == 'me2' or u == 'dress2' then   -- the respawned Helldiver, 10 m away, same pose
        local q = (u == 'me2' and legs[n]) or (u == 'dress2' and rest_pos[n]) or { 0, 0, 0 }
        if n == 1 then q = { 0, 0, 0 } end
        local o = freeze2 or off
        return { x = q[1] + o[1] + 10, y = q[2] + o[2], z = q[3] + o[3] }
      end
      local p = (u == 'dress' and rest_pos[n]) or (u == 'helm' and helm_pos[n]) or (u == 'coat' and coat_pos[n]) or (u == 'me' and legs[n]) or { 0, 0, 0 }
      if n == 1 then p = { 0, 0, 0 } end
      return { x = p[1] + off[1], y = p[2] + off[2], z = p[3] + off[3] }
    end,
  },
}
HD2DRESS_REGISTRY = { { name = 'test dress', unit = 'abc', chains = NC, bones = NB, lengths = nil, tails = { { prefix = 'dress_t01', bones = 4 } } },
                      { name = 'test hair', unit = 'hhh', chains = 0, bones = 0, tails = { { prefix = 'dress_t01', bones = 4, parent = 'head' } } },
                      { name = 'test coat', unit = 'ccc', chains = 0, bones = 0, tails = {},
                        parts = { { name = 'cape', type = 'SHEET', layer = 0, chains = 3, bones = 3, parents = { 'chest', 'chest', 'chest' }, format = 'dress_cape_c%02d_b%d' },
                                  { name = 'outer', type = 'RING', layer = 1, chains = NC, bones = NB, format = 'dress_outer_c%02d_b%d' } } } }
update = function() end; render = function() end
local f = assert(io.popen('python3 tools/pack.py expand mod/hd2dress.lua')); local src = f:read('*a'); f:close()
assert(loadstring(src))()
local function frame() update(1 / 60); render() end
local function last(pat) for i = #lines, 1, -1 do if lines[i]:find(pat) then return lines[i] end end end
for _ = 1, 30 do frame() end
assert(last('%[dress%] found "test dress": skirt ring 6x3, 1 single chain'), 'found the dress (0.6 format): ' .. tostring(last('%[dress%] found')))
assert(last('%[dress%] found "test hair": no strips, 1 single chain'), 'found the hair piece: ' .. tostring(last('%[dress%] found "test hair')))
assert(last('%[dress%] found "test coat": cape sheet 3x3, outer ring 6x3 layer 1, 0 single chain'), 'found the coat (two parts): ' .. tostring(last('%[dress%] found "test coat')))
assert(last('%[dress%] outfit: 3 piece%(s%) on 1 Helldiver%(s%).*body joints 16 of 16'), 'one outfit, three pieces, whole body: ' .. tostring(last('outfit')))
assert(last('%[blast%] explosion reader off'), 'off the game (no game.dll) the explosion reader switches itself off: ' .. tostring(last('%[blast%]')))
assert(rot['coat:dress_cape_c01_b1'] and rot['coat:dress_outer_c01_b1'], 'both coat parts are driven')
assert(rot['helm:dress_t01_b1'], 'the hair chain in the second piece is driven')
assert(writes >= 6 * 3 * 20, 'writes every frame: ' .. writes)
local function tilt(n) local q = rot[n]; return q and math.deg(2 * math.acos(math.min(1, math.abs(q.qw)))) or 0 end
assert(tilt('dress_c01_b1') < 1, 'at rest when still: ' .. tilt('dress_c01_b1'))
local maxt = 0
local capet = 0
for i = 1, 30 do off[2] = off[2] + 0.03; frame(); maxt = math.max(maxt, tilt('dress_c01_b1')); capet = math.max(capet, tilt('coat:dress_cape_c02_b1')) end   -- walk forward 1.8 m/s
assert(maxt > 5, 'the front swings back when walking: ' .. maxt)
assert(capet > 2, 'the cape swings too: ' .. capet)
for _ = 1, 400 do frame() end
assert(tilt('dress_c01_b1') < 1, 'settles: ' .. tilt('dress_c01_b1'))
assert(rot['dress_t01_b1'] and tilt('dress_t01_b4') < 3, 'tail written and back near rest: ' .. tilt('dress_t01_b4'))
-- respawn: a new Helldiver appears wearing the dress; the old one stays (a corpse keeps its armour).
-- The newest must get physics (0.7: it stayed on the corpse, the new dress stood as a cone).
respawned = true
local before = writes
for _ = 1, 150 do frame() end
assert(last('%[dress%] outfit: .* on 2 Helldiver%(s%)'), 'both dresses simulated (limit 4): ' .. tostring(last('outfit')))
assert(rot['dress2:dress_c01_b1'], 'the respawned Helldiver\'s dress is driven')
-- limit 1 (MAX_DRESSES=1): only the newest, the respawned one; the corpse's dress goes back to rest
SETTINGS_TEXT = 'MAX_DRESSES=1\n'
for _ = 1, 300 do frame() end
assert(last('%[dress%] outfit: .* on 1 Helldiver%(s%) %(moving and newest first, of 2'), 'limit 1 keeps only the newest: ' .. tostring(last('outfit')))
rot['dress_c01_b1'] = nil; rot['dress2:dress_c01_b1'] = nil
for i = 1, 30 do off[2] = off[2] + 0.03; frame() end
assert(rot['dress2:dress_c01_b1'] and not rot['dress_c01_b1'], 'only the respawned dress is driven now')
-- the newer Helldiver (me2) now lies still like a corpse, the older one (me) keeps moving: with one
-- slot, the moving one must win it within a few looks
freeze2 = { off[1], off[2], off[3] }
rot['dress_c01_b1'] = nil
for i = 1, 600 do off[2] = off[2] + 0.01; frame() end
assert(rot['dress_c01_b1'], 'the moving (older) Helldiver gets the slot back from a still, newer one')
assert(last('%[dress%] outfit: .* on 1 Helldiver'), 'still one slot')
freeze2 = nil
SETTINGS_TEXT = nil
-- sleep: everyone stands still for 4 s -> asleep (no bone writes); a step wakes them
for _ = 1, 260 do frame() end
local w1 = writes
for _ = 1, 60 do frame() end
assert(writes == w1, 'asleep while standing still: no writes (' .. (writes - w1) .. ')')
off[2] = off[2] + 0.1; frame(); frame()
assert(writes > w1, 'a step wakes the dress')
-- the preview Helldiver (dress + legs) is deleted mid-play: no call may touch it again
dead['dress'], dead['me'], dead['helm'], dead['coat'] = true, true, true, true
for _ = 1, 200 do frame() end
assert(crashes == 0, crashes .. ' calls into the deleted preview Helldiver (each one = a native crash in game)')
assert(last('let go of') or last('a piece is gone'), 'let go of the deleted pieces')
for _, l in ipairs(lines) do assert(not l:find('error'), l) end
print(string.format('test_dress_runtime: ok (swing %.1f deg, cape %.1f deg, %d bone writes)', maxt, capet, writes))
