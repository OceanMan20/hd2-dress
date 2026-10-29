"""HD2 Dress auto-rig: add skirt physics bones to an existing armour mod, in one command.
   ~/apps/blender-5.2.2-linux-x64/blender -b -P tools/dress_autorig.py -- MOD_PATCH OUTDIR [options]
     MOD_PATCH   the mod's 9ba626afa44a3aa3.patch_N (read-only; the .gpu_resources/.stream beside it)
     OUTDIR      gets a SMALL add-on patch with only the rigged armour pieces (install it after the
                 mod: a later patch overrides those units), + hd2dress_register.json
   options:
     --units A,B     unit names to rig (default: every Torso/Hip piece with cloth below the waist)
     --chains 12     chains around the body (more = rounder, costs more)
     --joints 6      bones per chain, waist to hem
     --waist 0.93    height (m, rest pose) where the cloth starts to move
     --blend 0.08    metres over which the cloth fades from the body's weights to the chains
     --exclude-back  leave a narrow sector at the back alone (e.g. a tail modelled in the mesh)
     --name TEXT     the mod's name (for the registration addon)
     --tail auto|none   a tail = separate mesh pieces reaching far behind the body (default auto);
                     it gets its own chain (dress_t01_bK) and its own feel (TAIL_* settings)
     --tail-joints 5 bones in the tail chain
Reads the game files and the mod, never writes them. Quick and dirty on purpose: it needs no
input from the author. For hand-made quality, see docs/AUTHORING.md: name your own bones
dress_cNN_bK and the HD2 Dress addon simulates them the same way.

How it works (per rigged mesh):
  1. cloth = vertices below WAIST (outside the BLEND zone they belong to the cloth fully);
  2. the cloth is cut into CHAINS sectors around the hips axis; in each sector the median radius at
     JOINTS+1 heights from the waist to that sector's hem gives the chain's joints, so the chains
     follow the skirt's real shape (A-line, flare, a longer back);
  3. bones dress_cNN_b1..bK along each chain, b1 parented to hips, each next to the one before;
  4. each cloth vertex is weighted to the 2 nearest chains (by angle) x 2 nearest bones (by height),
     blended with its original weights across the BLEND zone, max 4 influences, normalised."""
import bpy, sys, os, addon_utils, math, json, statistics, mathutils
args = sys.argv[sys.argv.index('--') + 1:]
PATCH_IN, OUTDIR = os.path.abspath(args[0]), os.path.abspath(args[1])
def opt(name, conv, default):
    return conv(args[args.index(name) + 1]) if name in args else default
UNITS = opt('--units', lambda s: s.split(','), None)
NC, NJ = opt('--chains', int, 12), opt('--joints', int, 6)   # 6: with 4 the cloth bent in hoops (2026-10-15)
WAIST, BLEND = opt('--waist', float, 0.93), opt('--blend', float, 0.08)
EXCLUDE_BACK = '--exclude-back' in args
TAIL_MODE = opt('--tail', str, 'auto')
NT = opt('--tail-joints', int, 5)
TAIL_REACH = 0.6        # a piece counts as a tail if it reaches this far behind the hips axis (m) ...
TAIL_WIDTH = 0.4        # ... and is at most this wide (m)
CENTER = (0.0, -0.02)          # hips axis (x, y) in the Helldiver rest pose
GAME = os.path.expanduser('~/.local/share/Steam/steamapps/common/Helldivers 2/data/')
assert not OUTDIR.startswith(os.path.realpath(GAME)), 'refusing to write into the game folder'
os.makedirs(OUTDIR, exist_ok=True)

addon_utils.enable('HD2SDK-CommunityEdition'); m = sys.modules['HD2SDK-CommunityEdition']
m.Global_gamepath = GAME
sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(GAME)
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
st = bpy.context.scene.Hd2ToolPanelSettings
st.ImportLods = False; st.AutoLods = True; st.ImportMaterials = False
st.AutoSaveUnitMaterials = False   # the mod's materials stay in the mod's patch (saving them re-encodes every texture)
TM = m.Global_TocManager
TM.LoadArchive(GAME + m.BaseArchiveHexID, True, False)
modpatch = TM.LoadArchive(PATCH_IN, True, True)
uids = list(modpatch.TocDict.get(m.UnitID, {}).keys())
for uid in uids:
    TM.Load(uid, m.UnitID)
meshes = {o.name: o for o in bpy.data.objects if o.type == 'MESH' and 'Z_ObjectID' in o}

def rig_of(o): return next((md.object for md in o.modifiers if md.type == 'ARMATURE'), None)
def world_verts(o): return [o.matrix_world @ v.co for v in o.data.vertices]
def angle_of(p): return math.atan2(p.x - CENTER[0], p.y - CENTER[1]) % (2 * math.pi)   # 0 = front (+Y), clockwise from above
def radius_of(p): return math.hypot(p.x - CENTER[0], p.y - CENTER[1])

if UNITS is None:
    UNITS = []
    for n, o in meshes.items():
        slot = str(o.get('Z_CustomizationSlot', ''))
        if not any(s in slot for s in ('Torso', 'Hip')): continue
        rig = rig_of(o)
        if not rig or 'hips' not in rig.data.bones: continue
        below = sum(1 for p in world_verts(o) if p.z < WAIST - BLEND and radius_of(p) > 0.12)
        if below > 200: UNITS.append(n)
print('AUTORIG targets:', UNITS)
assert UNITS, 'no mesh with cloth below the waist found (use --units)'

def sector(a):  # continuous chain coordinate 0..NC
    return a / (2 * math.pi) * NC

report = {'chains': NC, 'joints': NJ, 'waist': WAIST, 'blend': BLEND, 'units': []}
def find_tail(o, P):
    """vertex indices of the tail: connected mesh pieces that reach far behind and are narrow"""
    if TAIL_MODE == 'none': return set()
    import bmesh
    bm = bmesh.new(); bm.from_mesh(o.data); bm.verts.ensure_lookup_table()
    seen, tail = set(), set()
    for v in bm.verts:
        if v.index in seen: continue
        stack, isl = [v], []; seen.add(v.index)
        while stack:
            x = stack.pop(); isl.append(x.index)
            for e in x.link_edges:
                w = e.other_vert(x)
                if w.index not in seen: seen.add(w.index); stack.append(w)
        ys = [P[i].y for i in isl]; xs = [P[i].x for i in isl]
        if min(ys) < CENTER[1] - TAIL_REACH and max(xs) - min(xs) < TAIL_WIDTH:
            tail.update(isl)
    bm.free()
    return tail

def tail_chain(P, tail):
    """joints along the tail: from its root (the point nearest the hips) by distance from the root"""
    hips = mathutils.Vector((CENTER[0], CENTER[1], WAIST + 0.1))
    root = min(tail, key=lambda i: (P[i] - hips).length)
    d = {i: (P[i] - P[root]).length for i in tail}
    dmax = max(d.values()) or 1
    pos = []
    for k in range(NT + 1):
        lo, hi = dmax * (k - 0.5) / NT, dmax * (k + 0.5) / NT
        pts = [P[i] for i in tail if lo <= d[i] < hi] or [P[root]]
        c = mathutils.Vector((0, 0, 0))
        for p in pts: c += p
        pos.append(c / len(pts))
    return pos, d, dmax

for name in UNITS:
    o = meshes[name]; rig = rig_of(o)
    P = world_verts(o)
    tail = find_tail(o, P)
    cloth = [i for i, p in enumerate(P) if p.z < WAIST and i not in tail]
    # per sector: hem height (low percentile, robust to a few stray vertices) and radius profile
    chains = []
    for c in range(NC):
        a_mid = 2 * math.pi * (c + 0.5) / NC
        a_lo, a_hi = 2 * math.pi * c / NC, 2 * math.pi * (c + 1) / NC
        pts = [P[i] for i in cloth if a_lo <= angle_of(P[i]) < a_hi]
        if len(pts) < 10:
            pts = [P[i] for i in cloth]                        # sparse sector: use the whole skirt
        # hem = the lowest cloth in this sector (a 3 % percentile cut the slim dress's long front
        # panel off, 2026-10-15); points far out from the body (a tail, a weapon) do not count
        near = [p.z for p in pts if radius_of(p) < 0.5] or [p.z for p in pts]
        hem = min(near)
        levels = [WAIST - (WAIST - hem) * k / NJ for k in range(NJ + 1)]
        joints = []
        for k, z in enumerate(levels):
            band = [radius_of(p) for p in pts if abs(p.z - z) < max(0.03, (WAIST - hem) / NJ / 2)]
            r = statistics.median(band) if band else (joints[-1][1] if joints else 0.18)
            joints.append((z, r))
        dx, dy = math.sin(a_mid), math.cos(a_mid)
        chains.append({'angle': a_mid, 'hem': hem,
                       'pos': [mathutils.Vector((CENTER[0] + r * dx, CENTER[1] + r * dy, z)) for z, r in joints]})
    # bones
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    inv = rig.matrix_world.inverted()
    names = []
    for c, ch in enumerate(chains):
        parent = rig.data.edit_bones['hips']
        row = []
        for k in range(1, NJ + 1):
            bn = f'dress_c{c + 1:02d}_b{k}'
            eb = rig.data.edit_bones.get(bn) or rig.data.edit_bones.new(bn)
            eb.head = inv @ ch['pos'][k - 1]; eb.tail = inv @ ch['pos'][k]
            eb.parent = parent; parent = eb; row.append(bn)
        names.append(row)
    bpy.ops.object.mode_set(mode='OBJECT')
    # weights
    groups = {g.name: g for g in o.vertex_groups}
    for row in names:
        for bn in row:
            if bn not in groups: groups[bn] = o.vertex_groups.new(name=bn)
    gname = {g.index: g.name for g in o.vertex_groups}
    back_lo, back_hi = math.pi * (1 - 0.6 / NC), math.pi * (1 + 0.6 / NC)
    changed = 0
    for i in cloth:
        p = P[i]
        f = min(1.0, (WAIST - p.z) / BLEND) if BLEND > 0 else 1.0
        f = f * f * (3 - 2 * f)                                   # smoothstep
        if f <= 0: continue
        a = angle_of(p)
        if EXCLUDE_BACK and back_lo <= a <= back_hi: continue
        s = sector(a) - 0.5                                       # chain c's centre sits at c + 0.5
        c0 = int(math.floor(s)) % NC; c1 = (c0 + 1) % NC; wc1 = s - math.floor(s)
        cw = {}
        for c, wc in ((c0, 1 - wc1), (c1, wc1)):
            ch = chains[c]
            span = max(1e-3, WAIST - ch['hem'])
            t = min(NJ - 1e-6, max(0.0, (WAIST - p.z) / span * NJ))   # 0..NJ along the chain
            u = t - 0.5                                               # bone k's centre at k - 0.5
            k0 = int(math.floor(u)); wk1 = u - k0
            for k, wk in ((k0, 1 - wk1), (k0 + 1, wk1)):
                k = min(NJ - 1, max(0, k))
                bn = names[c][k]
                cw[bn] = cw.get(bn, 0) + wc * wk
        orig = {gname[g.group]: g.weight for g in o.data.vertices[i].groups if g.weight > 0}
        mix = {}
        for bn, w in orig.items(): mix[bn] = mix.get(bn, 0) + w * (1 - f)
        for bn, w in cw.items(): mix[bn] = mix.get(bn, 0) + w * f
        top = sorted(mix.items(), key=lambda kv: -kv[1])[:4]
        tot = sum(w for _, w in top) or 1
        for g in list(o.data.vertices[i].groups):
            o.vertex_groups[g.group].remove([i])
        for bn, w in top:
            groups[bn].add([i], w / tot, 'REPLACE')
        changed += 1
    tails = []
    if tail:
        tpos, td, tdmax = tail_chain(P, tail)
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode='EDIT')
        parent = rig.data.edit_bones['hips']; trow = []
        for k in range(1, NT + 1):
            bn = f'dress_t01_b{k}'
            eb = rig.data.edit_bones.get(bn) or rig.data.edit_bones.new(bn)
            eb.head = inv @ tpos[k - 1]; eb.tail = inv @ tpos[k]
            eb.parent = parent; parent = eb; trow.append(bn)
        bpy.ops.object.mode_set(mode='OBJECT')
        for bn in trow:
            if bn not in groups: groups[bn] = o.vertex_groups.new(name=bn)
        gname = {g.index: g.name for g in o.vertex_groups}
        for i in tail:
            t = min(NT - 1e-6, td[i] / tdmax * NT)
            f = min(1.0, t / 0.6); f = f * f * (3 - 2 * f)        # the root blends into the body
            u = t - 0.5; k0 = int(math.floor(u)); wk1 = u - k0
            cw = {}
            for k, wk in ((k0, 1 - wk1), (k0 + 1, wk1)):
                k = min(NT - 1, max(0, k)); cw[trow[k]] = cw.get(trow[k], 0) + wk
            orig = {gname[g.group]: g.weight for g in o.data.vertices[i].groups if g.weight > 0}
            mix = {}
            for bn, w in orig.items(): mix[bn] = mix.get(bn, 0) + w * (1 - f)
            for bn, w in cw.items(): mix[bn] = mix.get(bn, 0) + w * f
            top = sorted(mix.items(), key=lambda kv: -kv[1])[:4]; tot = sum(w for _, w in top) or 1
            for g in list(o.data.vertices[i].groups): o.vertex_groups[g.group].remove([i])
            for bn, w in top: groups[bn].add([i], w / tot, 'REPLACE')
        tails.append({'prefix': 'dress_t01', 'bones': NT, 'names': trow,
                      'lengths': [round((tpos[k] - tpos[k - 1]).length, 4) for k in range(1, NT + 1)],
                      'rest': [[round(x, 4) for x in p] for p in tpos]})
        print(f'AUTORIG {name}: tail {len(tail)} vertices, {NT} bones, {tdmax:.2f} m long')
    print(f'AUTORIG {name}: {len(cloth)} cloth vertices, {changed} re-weighted, {NC}x{NJ} bones; hem per chain '
          + ' '.join(f'{ch["hem"]:.2f}' for ch in chains))
    report['units'].append({'name': name, 'unit_id': f'{int(o["Z_ObjectID"]):016x}', 'chains': NC, 'bones_per_chain': NJ,
                            'bones': names, 'hem': [round(ch['hem'], 3) for ch in chains],
                            'lengths': [[round((ch['pos'][k] - ch['pos'][k - 1]).length, 4) for k in range(1, NJ + 1)] for ch in chains],
                            'rest': [[[round(x, 4) for x in pt] for pt in ch['pos']] for ch in chains], 'tails': tails})

# a NEW patch holding only the rigged units (the mod's textures/materials stay in the mod's patch;
# re-saving the whole mod made HD2SDK re-encode every texture, ~10+ min, 2026-10-15)
base = TM.LoadArchive(GAME + m.BaseArchiveHexID, True, False)
TM.ActiveArchive = base
TM.CreatePatchFromActive('HD2 Dress rig')
PATCH_OUT = os.path.join(OUTDIR, m.BaseArchiveHexID + '.patch_0')
TM.ActivePatch.UpdatePath(PATCH_OUT)
bpy.ops.object.select_all(action='DESELECT')
for name in UNITS: meshes[name].select_set(True)
bpy.context.view_layer.objects.active = meshes[UNITS[0]]
print('AUTORIG batchsave', bpy.ops.helldiver2.archive_unit_batchsave())
print('AUTORIG patch entries', {hex(t): len(v) for t, v in TM.ActivePatch.TocDict.items()})
TM.PatchActiveArchive()
json.dump(report, open(os.path.join(OUTDIR, 'hd2dress_register.json'), 'w'), indent=1)
# the registration addon: tells the HD2 Dress runtime which armour units carry dress bones. Every
# Bingus addon shares one Lua state, so a global list works whichever addon loads first.
MODNAME = opt('--name', str, os.path.basename(os.path.dirname(PATCH_IN)) or 'dress')
slug = ''.join(ch if ch.isalnum() else '_' for ch in MODNAME.lower()).strip('_')[:40] or 'dress'
lines = [f'-- HD2-Addon: mods/hd2dress/reg_{slug}',
         f'-- HD2 Dress registration for "{MODNAME}" (made by tools/dress_autorig.py). Needs the HD2 Dress addon.',
         'HD2DRESS_REGISTRY = rawget(_G, "HD2DRESS_REGISTRY") or {}']
for u in report['units']:
    lens = '{' + ','.join('{' + ','.join(str(x) for x in row) + '}' for row in u['lengths']) + '}'
    tl = ', '.join('{ prefix = "%s", bones = %d, lengths = {%s} }' % (t['prefix'], t['bones'], ','.join(str(x) for x in t['lengths'])) for t in u.get('tails', []))
    lines.append(f'table.insert(HD2DRESS_REGISTRY, {{ name = {json.dumps(MODNAME + " / " + u["name"])}, unit = "{u["unit_id"]}", '
                 f'chains = {u["chains"]}, bones = {u["bones_per_chain"]}, lengths = {lens}, tails = {{ {tl} }} }})')
open(os.path.join(OUTDIR, 'hd2dress_register.lua'), 'w').write('\n'.join(lines) + '\n')
print('AUTORIG wrote', PATCH_OUT)
