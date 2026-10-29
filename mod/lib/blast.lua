-- Blasts (shock waves on the cloth): the game's explosion queue, read-only, and the wave physics.
-- Pure Lua: every memory read goes through a `mem` adapter, so the tests run on fake memory and the
-- game gives a ReadProcessMemory adapter (a bad address fails the read instead of crashing the game).
--
-- The queue (found 2026-10-17 by reading HD2Runtime 0.31.3's notes, then verified live on bongo
-- with LLM: a Leveller, an incendiary grenade, a Hellbomb, an orbital precision strike and a 500 kg
-- bomb all appeared with their positions). No code is taken from HD2Runtime (no licence); these are
-- facts about the game:
--   game.dll + QUEUE_RVA -> queue; queue + 32: u32 count, u32 kicked; queue + 40: entries, 152 bytes
--   each: f32 x, y, z, u32 type (+12), source (+16), owner (+20), u64 creditor peer (+24).
--   The game handles up to 8 per frame and reuses slot 0 for the next one, so entries are read
--   every frame and a new one is a slot whose contents changed.
-- Pins for game.dll build 6AB3B43F (sha256 2E2C3B7C...): checked once at open(); any mismatch (a
-- game patch) switches the reader off with a log line, and the dress keeps working without waves.
--
--   local B = Blast.open(mem)               -- nil, why   when the build or the code does not match
--   local list = Blast.poll(B, now)         -- new explosions this frame: {x, y, z, type, source, owner, creditor}
--   local w = Blast.wave(e, now, P)         -- the shock wave of one explosion (nil = too small)
--   local dv = Blast.dv(waves, p, t0, t1, P) -- velocity kick (m/s) for a cloth joint at p, fronts passing it in (t0, t1]
local Blast = {}

Blast.PIN = {
  build = 0x6AB3B43F,          -- game.dll PE timestamp
  image_size = 0x4744000,
  request_rva = 0x13C0A80,     -- the game's explosion request: its first bytes must be exactly these
  request_bytes = '\x40\x53\x48\x83\xec\x30\x8b\x41\x20\x4c\x8b\xda\x48\x8b\xd9\x3d\x00\x01\x00\x00\x0f\x83\x69\x02\x00\x00',
  queue_rva = 0x346D558,
  count = 32, entries = 40, stride = 152, capacity = 256, per_frame = 8,
  type = 12, source = 16, owner = 20, creditor = 24,
  type_bound = 423,
}

-- explosion types measured live (2026-10-17) -> wave size: S = kick in m/s at the centre, R = reach (m)
Blast.TYPES = {
  [125] = { name = 'Hellbomb', S = 14, R = 120 },
  [277] = { name = '500 kg bomb (blast)', S = 12, R = 100 },
  [193] = { name = '500 kg bomb (impact)', S = 5, R = 40 },
  [343] = { name = 'orbital precision strike', S = 10, R = 80 },
  [204] = { name = 'Leveller', S = 6, R = 45 },
  [184] = { name = 'Leveller (second blast)', S = 6, R = 45 },
  [224] = { name = 'incendiary grenade', S = 3, R = 15 },
}
Blast.DEFAULT = { name = 'explosion', S = 4, R = 25 }     -- every other type: a modest one
-- 2026-10-17 in game (Hellbomb at 60 m, beside the Helldiver): a single kick above ~10 m/s sent the
-- skirt through both legs (a joint moved further in one 1/60 s step than a leg is wide). Now the wave
-- PUSHES for BLAST_PUSH seconds (billows, keeps its momentum) and while a wave passes the cloth runs
-- BLAST_SUBSTEPS x faster steps, so BLAST_MAX_SPEED (much higher than the normal MAX_SPEED) still moves
-- a joint less per step than a shin is wide: the legs block it.
Blast.DEFAULTS = { BLAST = 1, BLAST_SCALE = 4, BLAST_SPEED = 150, BLAST_LIFT = 0.35, BLAST_MAX_DV = 20,
                   BLAST_PUSH = 0.15, BLAST_SUBSTEPS = 4, BLAST_MAX_SPEED = 30,
                   BLAST_RESPONSE = 1 }   -- per dress (its author): how strongly this cloth reacts; players have BLAST_SCALE

local function u32(s, at) local a, b, c, d = s:byte(at + 1, at + 4); return a + b * 256 + c * 65536 + d * 16777216 end
local function u64(s, at) return u32(s, at) + u32(s, at + 4) * 4294967296 end
local function f32(s, at)
  local v = u32(s, at)
  local sign = v >= 2147483648 and -1 or 1
  local e = math.floor(v / 8388608) % 256
  local m = v % 8388608
  if e == 255 then return 0 / 0 end
  if e == 0 then return sign * m * 2 ^ -149 end
  return sign * (1 + m / 8388608) * 2 ^ (e - 127)
end
Blast.u32, Blast.f32 = u32, f32

-- mem = { base = game.dll base address (number), read = function(address, length) -> string or nil }
function Blast.open(mem)
  local K = Blast.PIN
  if not (mem and mem.base and mem.base > 0) then return nil, 'game.dll not found' end
  local hdr = mem.read(mem.base, 4096)
  if not (hdr and #hdr == 4096 and hdr:sub(1, 2) == 'MZ') then return nil, 'game.dll header unreadable' end
  local pe = u32(hdr, 60)
  if pe < 64 or pe + 88 > #hdr or hdr:sub(pe + 1, pe + 4) ~= 'PE\0\0' then return nil, 'game.dll PE header' end
  local stamp, size = u32(hdr, pe + 8), u32(hdr, pe + 80)
  if stamp ~= K.build or size ~= K.image_size then
    return nil, string.format('game.dll is build %08X (size %X), the explosion reader knows %08X: waves off until updated', stamp, size, K.build)
  end
  local code = mem.read(mem.base + K.request_rva, #K.request_bytes)
  if code ~= K.request_bytes then return nil, 'the explosion request code differs from the known build: waves off' end
  return { mem = mem, prev = {}, recent = {}, reads = 0, bad = 0 }
end

-- the new explosions since the last call (dedupe: the same entry seen again within 1 s is not new)
function Blast.poll(B, now)
  local K = Blast.PIN
  local mem = B.mem
  local qp = mem.read(mem.base + K.queue_rva, 8)
  if not qp then B.bad = B.bad + 1; return {} end
  local q = u64(qp, 0)
  if q == 0 then return {} end
  local raw = mem.read(q + K.count, 8 + K.per_frame * K.stride)       -- count, kicked, then the first 8 slots
  if not raw then B.bad = B.bad + 1; return {} end
  local count, kicked = u32(raw, 0), u32(raw, 4)
  if count > K.capacity or kicked > K.per_frame then B.bad = B.bad + 1; return {} end
  B.reads = B.reads + 1
  local out = {}
  for i = 0, K.per_frame - 1 do
    local at = 8 + i * K.stride
    local key = raw:sub(at + 1, at + 32)
    if key ~= B.prev[i] then
      B.prev[i] = key
      local e = { x = f32(raw, at), y = f32(raw, at + 4), z = f32(raw, at + 8), type = u32(raw, at + K.type),
                  source = u32(raw, at + K.source), owner = u32(raw, at + K.owner), creditor = u64(raw, at + K.creditor) }
      local sane = e.type > 0 and e.type < K.type_bound
      for _, v in ipairs({ e.x, e.y, e.z }) do if v ~= v or math.abs(v) > 100000 then sane = false end end
      if sane and B.started and not (B.recent[key] and now - B.recent[key] < 1) then out[#out + 1] = e end
      B.recent[key] = now
    end
  end
  B.started = true            -- the first read only learns what is already there (old blasts)
  for k, t in pairs(B.recent) do if now - t > 5 then B.recent[k] = nil end end
  return out
end

local function g(P, k) local v = P and P[k]; if v == nil then v = Blast.DEFAULTS[k] end; return v end

function Blast.wave(e, now, P)
  local T = Blast.TYPES[e.type] or Blast.DEFAULT
  local s = g(P, 'BLAST_SCALE')
  if s <= 0 then return nil end
  return { c = { e.x, e.y, e.z }, t0 = now, S = T.S * s, R = T.R * math.sqrt(s), v = g(P, 'BLAST_SPEED'), name = T.name, type = e.type }
end

-- the waves still travelling at time now (a front past its reach is done)
function Blast.prune(waves, now)
  local out = {}
  for _, w in ipairs(waves) do if (now - w.t0 - 0.5) * w.v <= w.R then out[#out + 1] = w end end
  return out
end

-- the velocity change (m/s) for a joint at p during (t0, t1], or nil: each wave pushes for BLAST_PUSH
-- seconds from the moment its front reaches the joint, in total S x (1 - d/R)^2 (capped at BLAST_MAX_DV)
function Blast.dv(waves, p, t0, t1, P)
  local lift, cap, push = g(P, 'BLAST_LIFT'), g(P, 'BLAST_MAX_DV'), math.max(1e-3, g(P, 'BLAST_PUSH'))
  local kx, ky, kz, any = 0, 0, 0, false
  for _, w in ipairs(waves) do
    local dx, dy, dz = p[1] - w.c[1], p[2] - w.c[2], p[3] - w.c[3]
    local d = math.sqrt(dx * dx + dy * dy + dz * dz)
    local ta = w.t0 + d / w.v                                   -- the front reaches this joint
    local share = (math.min(t1, ta + push) - math.max(t0, ta)) / push
    if d < w.R and share > 0 then
      local a = math.min(cap, w.S * (1 - d / w.R) ^ 2 * g(P, 'BLAST_RESPONSE')) * share
      if d > 1e-6 then dx, dy, dz = dx / d, dy / d, dz / d else dx, dy, dz = 0, 0, 1 end
      dz = dz + lift
      local n = math.sqrt(dx * dx + dy * dy + dz * dz)
      kx, ky, kz, any = kx + a * dx / n, ky + a * dy / n, kz + a * dz / n, true
    end
  end
  if not any then return nil end
  local m = math.sqrt(kx * kx + ky * ky + kz * kz)
  if m > cap then kx, ky, kz = kx * cap / m, ky * cap / m, kz * cap / m end   -- several waves at once
  return { kx, ky, kz }
end

-- give every joint of a chain / a skirt its kick (velocity in verlet = p - pp per substep of h s)
function Blast.kick_chain(c, waves, t0, t1, P, h)
  if not (c.p and c.pp) then return 0 end
  if c.h and c.h ~= h then          -- same as Chain.rate: velocity to the new step size first
    local r = h / c.h
    for i = 1, c.n do local p, q = c.p[i], c.pp[i]; c.pp[i] = { p[1] - (p[1] - q[1]) * r, p[2] - (p[2] - q[2]) * r, p[3] - (p[3] - q[3]) * r } end
  end
  c.h = h
  local n = 0
  for i = 1, c.n do
    local d = Blast.dv(waves, c.p[i], t0, t1, P)
    if d then
      local q = c.pp[i]
      c.pp[i] = { q[1] - d[1] * h, q[2] - d[2] * h, q[3] - d[3] * h }
      n = n + 1
    end
  end
  return n
end
function Blast.kick_skirt(S, waves, t0, t1, P, h)
  local n = 0
  for c = 1, S.nc do n = n + Blast.kick_chain(S.chains[c], waves, t0, t1, P, h) end
  return n
end

return Blast
