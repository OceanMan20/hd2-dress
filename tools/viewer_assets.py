"""HD2 Dress motion preview, assets (run in a background Blender, never in the author's session: loading the Helldiver's
archive pulls in its 12 MB animation state machine):
    blender -b -P tools/viewer_assets.py -- OUT_DIR
Writes into OUT_DIR:
  helldiver.blend   the Helldiver's skeleton (armature 'hd2dress_avatar') + the preview animations as actions
                    'hd2dress_<NAME>' (fake user)
  colliders.json    the stock cape cloth's body colliders: [{bone, kind, start, end, radius, offset(4x4 row-major)}]
                    (offset and start/end are in the bone's space; HD2SDK bones carry the game's node matrices, so
                    world = armature.matrix_world @ pose_bone.matrix @ offset @ point)
"""
import bpy, sys, os, json, struct
args = sys.argv[sys.argv.index('--') + 1:]
OUT = os.path.abspath(os.path.expanduser(args[0])); os.makedirs(OUT, exist_ok=True)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.argv = [sys.argv[0], '--', 'archives']                  # import the build tool's helpers without running it
import importlib.util
spec = importlib.util.spec_from_file_location('hd2dress_cloth', os.path.join(HERE, 'hd2dress_cloth.py'))
hc = importlib.util.module_from_spec(spec)
try: spec.loader.exec_module(hc)
except SystemExit: pass
m, TM, GAME = hc.m, hc.TM, hc.GAME

AVATAR_ARCHIVE, AVATAR_UNIT = '18235e0c9ec0e636', 0x4d1c334d294dfa97
ANIMS = {   # name: animation id (found by motion, sim/classify.py and sim/stress_prepare.py)
    'JOG': 8958390548417319837, 'RUN': 4928390151762733173, 'CROUCH': 10224704622709553933,
    'DIVE': 15973994310853105570, 'CRAWL': 962193287716325945, 'GETUP': 2463154135084150628,
    'HIT': 2635010984077288310, 'STAND': 14033616244713305418,
}

# ---- 1. colliders from the stock cape cloth (the same shapes the build gives every garment)
from havok_model import Model
stock, _ = hc.template_bytes()
m1 = Model.load(stock, 1); names = [m1.text(x['name']) for x in m1.root['skeletons'][0]['bones']]
md = Model.load(stock, 4); V = lambda x: x.value if hasattr(x, 'value') else x
sim = V(md.root['simClothDatas'].item.elems[0]); ctm = sim['collidableTransformMap']
cols = []
for k, c in enumerate(sim['perInstanceCollidables'].item.elems):
    sh = V(V(c)['shape'])
    if sh.type.name != 'hclCapsuleShape': continue
    o = list(ctm['offsets'].item.elems[k])                    # Havok column-major 4x4 -> row-major
    off = [[o[r + 4 * cc] for cc in range(4)] for r in range(4)]
    cols.append(dict(bone=names[ctm['transformIndices'][k]], kind='capsule', start=list(sh['start'])[:3],
                     end=list(sh['end'])[:3], radius=float(sh['radius']), offset=off))
json.dump(cols, open(os.path.join(OUT, 'colliders.json'), 'w'), indent=1)
print('VIEWER colliders', len(cols), sorted({c['bone'] for c in cols}))

# ---- 2. the Helldiver skeleton + animations
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
st = bpy.context.scene.Hd2ToolPanelSettings; st.ImportLods = False; st.ImportMaterials = False
TM.LoadArchive(GAME + AVATAR_ARCHIVE, True, False)
TM.Load(AVATAR_UNIT, m.UnitID)
av = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
body = []
for o in list(bpy.data.objects):          # keep the body meshes (LOD0, skinned to the avatar) to show the Helldiver
    if o is av: continue
    rig = next((md.object for md in o.modifiers if md.type == 'ARMATURE'), None) if o.type == 'MESH' else None
    n = o.name.lower()
    if o.type == 'MESH' and rig is av and ('lod' not in n or n.endswith('lod0')) and 'shadow' not in n and 'culling' not in n:
        o.name = 'hd2dress_body_' + o.name; body.append(o.name)
        for slot in o.material_slots: slot.material = None
    else:
        bpy.data.objects.remove(o)
print('VIEWER body meshes', body)
av.name = 'hd2dress_avatar'
if av.animation_data is None: av.animation_data_create()
bpy.context.view_layer.objects.active = av
got = []
for key, aid in ANIMS.items():
    e = TM.GetEntry(aid, m.AnimationID, SearchAll=True, IgnorePatch=False)
    if e is None: print('VIEWER missing animation', key); continue
    e.Load(Reload=True, MakeBlendObject=True)
    act = av.animation_data.action
    if act is None: print('VIEWER animation did not load', key); continue
    act.name = 'hd2dress_' + key; act.use_fake_user = True; got.append(key)
    av.animation_data.action = None
print('VIEWER animations', got)
json.dump(body, open(os.path.join(OUT, 'body.json'), 'w'))
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'helldiver.blend'))
print('VIEWER saved', OUT)
