-- hd2dress_poserec [seconds] (HD2 Dress research, read-only): records the B-01 hip unit's leg/hip bones
-- every frame (world position + the three axes of the bone) to hd2dress_poserec.txt, for emote analysis.
local sr = rawget(_G, 'stingray')
local A, W, U, M = sr.Application, sr.World, sr.Unit, sr.Matrix4x4
local P = use('hd2_perf')
local seconds = tonumber(args[1] or '12') or 12
local NODES = { 'root', 'hips', 'spine1', 'r_thigh', 'r_knee', 'r_foot', 'l_thigh', 'l_knee', 'l_foot' }
local path = 'hd2dress_poserec.txt'
local f = io.open(path, 'wb'); f:write('# frame unit node px py pz  xx xy xz  yx yy yz  zx zy zz\n')
local t0, n = nil, 0
local function v(x) return string.format('%.4f %.4f %.4f', x.x, x.y, x.z) end
return function()
    local world = A.main_world(); if not world then return false end
    local units = {}
    for _, hex in ipairs({ '2f66b9373cb58485', '0387a158d04848f4' }) do
        local ok, list = pcall(W.units_by_resource, world, sr.IdString64.from_hex(hex))
        for _, u in ipairs(ok and list or {}) do units[#units + 1] = u end
    end
    t0 = t0 or P.clock(); n = n + 1
    for ui, u in ipairs(units) do
        for _, name in ipairs(NODES) do
            local okn, has = pcall(U.has_node, u, name)
            if okn and has then
                local m = U.world_pose(u, U.node(u, name))
                f:write(string.format('%d %d %s %s  %s  %s  %s\n', n, ui, name, v(M.translation(m)), v(M.x(m)), v(M.y(m)), v(M.z(m))))
            end
        end
    end
    if P.clock() - t0 < seconds * 1000 then return false end
    f:close(); out(string.format('recorded %d frames, %d hip units -> %s', n, #units, path)); return true
end
