"""PERSONAL TEST HELPER, not part of HD2 Dress (not shipped, not in the author docs).
Put an armour mod (and its HD2 Dress rig) onto a different armour, e.g. one the player owns.
   ~/apps/blender-5.2.2-linux-x64/blender -b -P dev/retarget.py -- MOD_PATCH RIG_PATCH REGISTER_JSON OUTDIR \
        --to ARMOUR_ARCHIVE [--helmet HELMET_ARCHIVE] [--helmet-from UNIT_HEX] [--name TEXT]
Reads the game, the mod and the rig; writes only OUTDIR:
  9ba626afa44a3aa3.patch_0 (+ .gpu_resources, .stream): the mod's pieces under the target armour's
      unit ids. Install it AFTER the original mod (its materials/textures stay in the mod's patch).
  hd2dress_register.lua / .json: the dress registration with the new unit ids.
Matching: each target piece takes the mod piece with the same (slot, piece type, body type); the
rigged dress pieces come from RIG_PATCH. Target pieces with no counterpart (e.g. shoulder pads the
mod doesn't have) become a 1 mm triangle so they don't show. With --helmet, the target helmet
takes the mod's head piece (--helmet-from, else the first unlabelled piece with real geometry).
Units are copied whole (skeleton, LODs, materials), the way HD2SDK's "copy to new id" does."""
import bpy, sys, os, json, addon_utils
args = sys.argv[sys.argv.index('--') + 1:]
MOD, RIG, REG, OUT = (os.path.abspath(a) for a in args[:4])
def opt(name, default=None): return args[args.index(name) + 1] if name in args else default
TO, HELMET, HELMET_FROM = opt('--to'), opt('--helmet'), opt('--helmet-from')
NAME = opt('--name', 'retargeted dress')
GAME = os.path.expanduser('~/.local/share/Steam/steamapps/common/Helldivers 2/data/')
assert TO, '--to ARMOUR_ARCHIVE is required'
assert not OUT.startswith(os.path.realpath(GAME)), 'refusing to write into the game folder'
os.makedirs(OUT, exist_ok=True)

addon_utils.enable('HD2SDK-CommunityEdition'); m = sys.modules['HD2SDK-CommunityEdition']
m.Global_gamepath = GAME
sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(GAME)
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
st = bpy.context.scene.Hd2ToolPanelSettings
st.ImportMaterials = False; st.ImportLods = False; st.AutoLods = True
st.AutoSaveUnitMaterials = False
TM = m.Global_TocManager
base = TM.LoadArchive(GAME + m.BaseArchiveHexID, True, False)

def key_of(o):
    s = lambda k: str(o.get(k, '')).replace('HelldiverCustomization', '')
    return (s('Z_CustomizationSlot'), s('Z_CustomizationPieceType'), s('Z_CustomizationBodyType'))
def load_units(arch, uids):
    """uid -> (blender mesh object, slot key, verts)"""
    out = {}
    for uid in uids:
        before = set(bpy.data.objects)
        try:
            if arch is None: TM.Load(uid, m.UnitID)
            else: arch.TocDict[m.UnitID][uid].Load(True, True)
        except Exception as e:
            print(f'RETARGET load failed {uid:016x}: {e}'); continue
        mesh = next((o for o in bpy.data.objects if o not in before and o.type == 'MESH'), None)
        if mesh: out[uid] = (mesh, key_of(mesh), len(mesh.data.vertices))
    return out

target_arch = TM.LoadArchive(GAME + TO, True, False)
target = load_units(None, list(target_arch.TocDict[m.UnitID].keys()))
helm_uids = []
if HELMET:
    ha = TM.LoadArchive(GAME + HELMET, True, False)
    helm_uids = list(ha.TocDict[m.UnitID].keys())
    target.update(load_units(None, helm_uids))
modp = TM.LoadArchive(MOD, True, True)
rigp = TM.LoadArchive(RIG, True, True)
mod = load_units(modp, list(modp.TocDict[m.UnitID].keys()))
rig_ids = set(rigp.TocDict[m.UnitID].keys())

by_key = {}
for uid, (o, k, n) in mod.items():
    if k[0]: by_key.setdefault(k, []).append((n, uid))
plan, blanks = {}, []
for tuid, (o, k, n) in target.items():
    if tuid in helm_uids:
        src = int(HELMET_FROM, 16) if HELMET_FROM else next((u for u, (mo, mk, mn) in sorted(mod.items()) if not mk[0] and mn > 100), None)
        if src: plan[tuid] = src
        else: blanks.append(tuid)
        continue
    cands = sorted(by_key.get(k, []), reverse=True)        # most geometry first
    if cands: plan[tuid] = cands[0][1]
    else: blanks.append(tuid)
for tuid, src in sorted(plan.items(), key=lambda kv: target[kv[0]][0].name):
    print(f'RETARGET {target[tuid][0].name:34} {tuid:016x} <- {"RIG " if src in rig_ids else "mod "}{src:016x} {mod[src][0].name if src in mod else ""}')
for tuid in blanks:
    print(f'RETARGET {target[tuid][0].name:34} {tuid:016x} <- blank (no counterpart in the mod)')

# new patch: whole-unit copies under the target ids, then the blanks saved through the SDK
TM.ActiveArchive = base
TM.CreatePatchFromActive('HD2 Dress retarget')
PATCH_OUT = os.path.join(OUT, m.BaseArchiveHexID + '.patch_0')
TM.ActivePatch.UpdatePath(PATCH_OUT)
for tuid, src in plan.items():
    e = (rigp if src in rig_ids else modp).TocDict[m.UnitID][src]
    if not e.IsLoaded: e.Load(False, False)
    TM.AddEntryToPatchID(e, tuid, ReloadUI=False)

def blank(target_obj):
    rig = next((md.object for md in target_obj.modifiers if md.type == 'ARMATURE'), None)
    b = 'hips' if rig and 'hips' in rig.data.bones else (rig.data.bones[0].name if rig else None)
    me = target_obj.data
    me.clear_geometry()
    me.from_pydata([(0, 0, 1.0), (0.001, 0, 1.0), (0, 0.001, 1.0)], [], [(0, 1, 2)])
    if not me.uv_layers: me.uv_layers.new()
    for g in list(target_obj.vertex_groups): target_obj.vertex_groups.remove(g)
    if b: target_obj.vertex_groups.new(name=b).add([0, 1, 2], 1.0, 'REPLACE')
if blanks:
    bpy.ops.object.select_all(action='DESELECT')
    for tuid in blanks:
        o = target[tuid][0]; blank(o); o.select_set(True)
        bpy.context.view_layer.objects.active = o
    print('RETARGET blanks saved', bpy.ops.helldiver2.archive_unit_batchsave())
print('RETARGET patch entries', {hex(t): len(v) for t, v in TM.ActivePatch.TocDict.items()})
TM.PatchActiveArchive()

# registration with the new ids. The whole entry is carried over (parts, ring/sheet, layers, which
# bone each part hangs from, single chains, the author's values and per-bone values); only the unit
# id changes. Each rigged piece (and each repeated copy of it) becomes one entry per target piece
# it was copied onto. Reads the add-on's export (units[].unit + copies) and the old autorig format
# (units[].unit_id, bones_per_chain).
def lua_value(v):
    if isinstance(v, dict):
        return '{ ' + ', '.join(f'[{json.dumps(k) if isinstance(k, str) else k}] = {lua_value(x)}' for k, x in v.items()) + ' }'
    if isinstance(v, (list, tuple)): return '{ ' + ', '.join(lua_value(x) for x in v) + ' }'
    if isinstance(v, str): return json.dumps(v)
    if isinstance(v, bool): return 'true' if v else 'false'
    return repr(round(v, 5)) if isinstance(v, float) else repr(v)
def int_keys(v):   # JSON turned the per-bone tables' number keys into strings; Lua needs numbers
    if isinstance(v, dict): return {(int(k) if isinstance(k, str) and k.isdigit() else k): int_keys(x) for k, x in v.items()}
    if isinstance(v, list): return [int_keys(x) for x in v]
    return v
reg = json.load(open(REG))
targets_of = {}
for tuid, src in plan.items(): targets_of.setdefault(src, []).append(tuid)
entries = []
for u in reg['units']:
    e = int_keys({k: v for k, v in u.items() if k not in ('rest', 'copies', 'unit', 'unit_id', 'bones_per_chain')})
    if 'bones_per_chain' in u: e['bones'] = u['bones_per_chain']
    ids = [int(x, 16) for x in (u.get('copies') or [u.get('unit') or u['unit_id']])]
    hit = False
    for src in ids:
        for tuid in targets_of.get(src, []):
            entries.append(dict(e, name=f'{NAME} / {u.get("name", "?")}', unit=f'{tuid:016x}')); hit = True
    if not hit: print('RETARGET warning: rigged piece', u.get('name'), 'is not on any target piece')
json.dump({'units': entries}, open(os.path.join(OUT, 'hd2dress_register.json'), 'w'), indent=1)
slug = ''.join(ch if ch.isalnum() else '_' for ch in NAME.lower()).strip('_')[:40] or 'dress'
lines = [f'-- HD2-Addon: mods/hd2dress/reg_{slug}',
         f'-- HD2 Dress registration for "{NAME}" (dev/retarget.py). Needs the HD2 Dress addon.',
         'HD2DRESS_REGISTRY = rawget(_G, "HD2DRESS_REGISTRY") or {}']
for e in entries: lines.append(f'table.insert(HD2DRESS_REGISTRY, {lua_value(e)})')
open(os.path.join(OUT, 'hd2dress_register.lua'), 'w').write('\n'.join(lines) + '\n')
print('RETARGET registration:', len(entries), 'entries;', ', '.join(f'{e["name"]} -> {e["unit"]}' for e in entries))
print('RETARGET wrote', PATCH_OUT)
