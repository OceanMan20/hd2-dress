"""Gating test patch: do bones that exist ONLY in an armour piece keep a rotation the mod writes?
   ~/apps/blender-5.2.2-linux-x64/blender -b -P tools/build_gate_patch.py -- OUTDIR
Reads the game files, writes ONLY to OUTDIR (refuses the game folder).

B-01 Tactical hip armour (Hip_Armor_Slim + Hip_Armor_Stocky, shared by every B-01 variation) gets
three new bones and three small flaps, everything else of the piece unchanged:
  dress_test_a  parent hips      back-left flap, upper half   (the mod rotates this one)
  dress_test_b  parent test_a    back-left flap, lower half   (never written: does a child follow?)
  dress_ctrl    parent hips      back-right flap              (never written: the control)
The flaps hang behind the hips, facing the third-person camera: thin boxes in the piece's own
material, every vertex 100% on its bone.
Output: OUTDIR/9ba626afa44a3aa3.patch_0 (+ .gpu_resources, .stream). Arsenal renumbers on install.
NOTE: it patches the same units as the HD2 Jaeger build (B-01): disable that one for this test."""
import bpy, bmesh, sys, os, addon_utils, mathutils
args = sys.argv[sys.argv.index('--') + 1:]
OUTDIR = os.path.abspath(args[0])
GAME = os.path.expanduser('~/.local/share/Steam/steamapps/common/Helldivers 2/data/')
ARCHIVE = '562a45e9bc984eb9'          # B-01 Tactical (Variation 2); the units are shared by all variations
HOSTS = ['Hip_Armor_Slim_lod0', 'Hip_Armor_Stocky_lod0']
# tunable test geometry (metres, Helldiver rest pose: +Y = forward (toes), +X = right, +Z = up;
# l_thigh at x -0.087, the hip armour reaches back to y -0.13)
FLAP_X = 0.10            # flap centres this far left / right of the middle
FLAP_Y = -0.17           # behind the hips
FLAP_TOP, FLAP_MID, FLAP_BOT = 0.95, 0.75, 0.55
FLAP_HALF_W = 0.07       # half width (left-right)
FLAP_HALF_T = 0.006      # half thickness (front-back)
BONES = [  # name, parent, head, tail
    ('dress_test_a', 'hips', (-FLAP_X, FLAP_Y, FLAP_TOP), (-FLAP_X, FLAP_Y, FLAP_MID)),
    ('dress_test_b', 'dress_test_a', (-FLAP_X, FLAP_Y, FLAP_MID), (-FLAP_X, FLAP_Y, FLAP_BOT)),
    ('dress_ctrl', 'hips', (FLAP_X, FLAP_Y, FLAP_TOP), (FLAP_X, FLAP_Y, FLAP_BOT)),
]
assert not OUTDIR.startswith(os.path.realpath(GAME)), 'refusing to write into the game folder'
os.makedirs(OUTDIR, exist_ok=True)

addon_utils.enable('HD2SDK-CommunityEdition')
m = sys.modules['HD2SDK-CommunityEdition']
m.Global_gamepath = GAME
sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(GAME)
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
st = bpy.context.scene.Hd2ToolPanelSettings
st.ImportLods = False; st.AutoLods = True; st.ImportMaterials = False

TM = m.Global_TocManager
BASE = m.BaseArchiveHexID
TM.LoadArchive(GAME + BASE, True, False)
TM.CreatePatchFromActive('HD2 Dress gate test')
PATCH_FILE = os.path.join(OUTDIR, f'{BASE}.patch_0')
TM.ActivePatch.UpdatePath(PATCH_FILE)
toc = TM.LoadArchive(GAME + ARCHIVE, True, False)
for uid in list(toc.TocDict.get(m.UnitID, {}).keys()):
    TM.Load(uid, m.UnitID)
units = {o.name: o for o in bpy.data.objects if o.type == 'MESH' and 'Z_ObjectID' in o}
print('GATE units:', sorted(units))

def rig_of(o):
    return next((md.object for md in o.modifiers if md.type == 'ARMATURE'), None)

def add_bones(rig):
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    inv = rig.matrix_world.inverted()
    for name, parent, head, tail in BONES:
        eb = rig.data.edit_bones.get(name) or rig.data.edit_bones.new(name)
        eb.head = inv @ mathutils.Vector(head); eb.tail = inv @ mathutils.Vector(tail)
        eb.parent = rig.data.edit_bones[parent]
    bpy.ops.object.mode_set(mode='OBJECT')
    print('GATE bones on', rig.name, len(rig.data.bones))

def box(bm, dl, gi, x, z0, z1):
    """thin box from z0 down to z1 at x, every vertex 100% on group gi"""
    vs = []
    for z in (z0, z1):
        for dx in (-FLAP_HALF_W, FLAP_HALF_W):
            for dy in (-FLAP_HALF_T, FLAP_HALF_T):
                v = bm.verts.new((x + dx, FLAP_Y + dy, z)); v[dl][gi] = 1.0; vs.append(v)
    # index = zi*4 + xi*2 + yi
    for q in [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]:
        bm.faces.new([vs[i] for i in q])

def add_flaps(obj):
    """Build the flaps as their own object (same material, same groups layout), then join them
    into the unit object so its HD2 properties, rig and material stay as they are."""
    me = bpy.data.meshes.new('dress_flaps')
    fo = bpy.data.objects.new('dress_flaps', me); bpy.context.scene.collection.objects.link(fo)
    groups = [fo.vertex_groups.new(name=n).index for n, *_ in BONES]
    bm = bmesh.new(); dl = bm.verts.layers.deform.verify()
    box(bm, dl, groups[0], -FLAP_X, FLAP_TOP, FLAP_MID)
    box(bm, dl, groups[1], -FLAP_X, FLAP_MID, FLAP_BOT)
    box(bm, dl, groups[2], FLAP_X, FLAP_TOP, FLAP_BOT)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])   # outward, so backface culling keeps every side
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(me); bm.free()
    for uv in obj.data.uv_layers: me.uv_layers.new(name=uv.name)
    if obj.material_slots: me.materials.append(obj.material_slots[0].material)
    fo.matrix_world = mathutils.Matrix.Identity(4)
    me.transform(obj.matrix_world.inverted())          # into the unit object's frame
    fo.matrix_world = obj.matrix_world.copy()
    bpy.ops.object.select_all(action='DESELECT')
    fo.select_set(True); obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    before = len(obj.data.vertices)
    bpy.ops.object.join()
    print(f'GATE flaps into {obj.name}: {before} -> {len(obj.data.vertices)} verts, groups {[g.name for g in obj.vertex_groups]}')

for h in HOSTS:
    o = units[h]
    add_bones(rig_of(o))
    add_flaps(o)

bpy.ops.object.select_all(action='DESELECT')
for h in HOSTS: units[h].select_set(True)
bpy.context.view_layer.objects.active = units[HOSTS[0]]
print('GATE batchsave', bpy.ops.helldiver2.archive_unit_batchsave())
assert TM.ActivePatch.Path == PATCH_FILE, TM.ActivePatch.Path
TM.PatchActiveArchive()
print('GATE wrote', PATCH_FILE)
