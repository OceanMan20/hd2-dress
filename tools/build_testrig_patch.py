"""Engine-cloth TEST RIG, step 1: the armour side.
   ~/apps/blender-5.2.2-linux-x64/blender -b -P tools/build_testrig_patch.py -- OUTDIR
Reads the game files, writes ONLY to OUTDIR (refuses the game folder).

B-01 Tactical hip armour (Hip_Armor_Slim + Hip_Armor_Stocky, shared by every B-01 variation) gets:
- twelve cloth STRIPS hanging around the hips (every 30 degrees), 10 cm wide, 25-55 cm long, double
  sided, in a bright yellow emissive material (HD2SDK 'emissive' template), every vertex 100% on
  'hips' (so without cloth they hang rigid);
- the body bones the hip unit lacks but cloth collision needs (knees, feet, spine1), at their rest
  positions taken from the full skeleton in the cape unit, so their nodes exist in the unit.
Outputs in OUTDIR:
  9ba626afa44a3aa3.patch_0 (+ .gpu_resources, .stream)   the armour patch
  testrig.blend                                           open it in Blender to see the rig
  testrig_strips.json                                     strip layout for the cloth generator
"""
import bpy, bmesh, sys, os, json, math, addon_utils, mathutils
args = sys.argv[sys.argv.index('--') + 1:]
OUTDIR = os.path.abspath(args[0])
GAME = os.path.expanduser('~/.local/share/Steam/steamapps/common/Helldivers 2/data/')
ARCHIVE = '562a45e9bc984eb9'
CAPE_BONES = os.environ.get('TESTRIG_CAPE', '0') == '1'   # also add cape1..cape8 (cloth 'wind' follows them)          # B-01 Tactical (Variation 2); the units are shared by all variations
HOSTS = ['Hip_Armor_Slim_lod0', 'Hip_Armor_Stocky_lod0']
EXTRA_BONES = [('r_knee', 'r_thigh'), ('r_foot', 'r_knee'), ('l_knee', 'l_thigh'), ('l_foot', 'l_knee'), ('spine1', 'hips'),
               ('spine2', 'spine1'), ('chest', 'spine2'), ('neck', 'chest'), ('head', 'neck'),
               ('l_clavicle', 'chest'), ('r_clavicle', 'chest'), ('l_shoulder', 'l_clavicle'), ('r_shoulder', 'r_clavicle'),
               ('l_elbow', 'l_shoulder'), ('r_elbow', 'r_shoulder')]
LAYOUT = os.environ.get('TESTRIG_LAYOUT', 'strips')      # 'strips' (12 hip strips), 'skirt_shoulders' or 'skirt'
SKIRT_SEGMENTS, SKIRT_LENGTH = int(os.environ.get('TESTRIG_SKIRT_SEGMENTS', '24')), float(os.environ.get('TESTRIG_SKIRT_LENGTH', '0.45'))                  # connected skirt: panels around, length (m)
SH_Z, SH_R = 1.50, 0.26                                  # shoulder ring: height, distance from the body axis

# strips: (name, angle around the body in degrees: 0 = front (+Y), 90 = left (-X)... , length m)
RING_Z, RING_R = 0.93, 0.19            # top of the strips: height and distance from the body axis
ROOT_IN_PALETTE = os.environ.get('TESTRIG_ROOT', '0') == '1'      # add 'root' to the bone palette (character shaders)
DOUBLE_SIDED = os.environ.get('TESTRIG_DOUBLE', '0') == '1'   # 0: one layer (cape shader draws both sides)
UV_MODE = os.environ.get('TESTRIG_UV', 'cylinder')           # 'cylinder' (continuous unwrap) or 'single'
UV_TILE_U, UV_TILE_V = 1.0, 1.0                              # texture repeats around the body / per metre of height
CLOTH_UV = 0.5                         # the single texture coordinate every cloth vertex uses (solid colour)
FLARE = float(os.environ.get('TESTRIG_FLARE', '0.45'))                            # strips angle outward (A-line): +0.45 m out per metre down, clear of the legs
WIDTH, ROW = 0.10, 0.05                # strip width, row spacing (m); 3 columns across
LENGTHS = [0.25, 0.35, 0.45, 0.55]     # cycled around the ring
STRIPS = [(f's{i:02d}_{a:03d}', a, LENGTHS[i % 4]) for i, a in enumerate(range(0, 360, 30))]   # 12 strips, 0 = front
COLOR = (1.0, 0.78, 0.0)               # bright HD2 yellow (base colour and glow)
assert not OUTDIR.startswith(os.path.realpath(GAME)), 'refusing to write into the game folder'
os.makedirs(OUTDIR, exist_ok=True)

addon_utils.enable('HD2SDK-CommunityEdition')
m = sys.modules['HD2SDK-CommunityEdition']
m.Global_gamepath = GAME
sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(GAME)
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
st = bpy.context.scene.Hd2ToolPanelSettings
st.ImportLods = False; st.AutoLods = os.environ.get('TESTRIG_AUTOLODS', '1') == '1'; st.ImportMaterials = False   # AutoLods copies LOD0 (and its cloth material) into LOD1-3
TM = m.Global_TocManager

# 1. rest positions of the missing bones, from the full skeleton in the cape unit
TM.LoadArchive(GAME + '18235e0c9ec0e636', True, False)
TM.Load(0x3c33cf10a26cbb3e, m.UnitID)
cape_rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
rest = {b.name: (cape_rig.matrix_world @ b.matrix_local, b.length) for b in cape_rig.data.bones}   # full rest matrix incl. roll
if CAPE_BONES: EXTRA_BONES += [('cape1', 'chest')] + [(f'cape{i}', f'cape{i-1}') for i in range(2, 9)]
print('RIG cape skeleton bones:', len(rest), 'has', [n for n, _ in EXTRA_BONES if n in rest])
for o in list(bpy.data.objects): bpy.data.objects.remove(o)

# 2. the B-01 hip units
BASE = m.BaseArchiveHexID
TM.LoadArchive(GAME + BASE, True, False)
TM.CreatePatchFromActive('HD2 Dress engine cloth test rig')
PATCH_FILE = os.path.join(OUTDIR, f'{BASE}.patch_0')
TM.ActivePatch.UpdatePath(PATCH_FILE)
toc = TM.LoadArchive(GAME + ARCHIVE, True, False)
for uid in (0x2f66b9373cb58485, 0x0387a158d04848f4):
    TM.Load(uid, m.UnitID)
units = {o.name: o for o in bpy.data.objects if o.type == 'MESH' and 'Z_ObjectID' in o}
print('RIG units:', sorted(units))


def rig_of(o):
    return next((md.object for md in o.modifiers if md.type == 'ARMATURE'), None)


def add_bones(rig):
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    inv = rig.matrix_world.inverted()
    for name, parent in EXTRA_BONES:
        if name in rig.data.edit_bones: continue
        M, length = rest[name]
        eb = rig.data.edit_bones.new(name); eb.length = length
        eb.matrix = inv @ M                 # exact rest orientation (roll) of the real bone: the game drives it with
        eb.length = length                  # the real bone's animation, so a different roll rotates everything on it
        eb.parent = rig.data.edit_bones.get(parent)
    bpy.ops.object.mode_set(mode='OBJECT')
    print('RIG bones on', rig.name, [b.name for b in rig.data.bones])


def make_material():
    """An HD2SDK 'emissive' material with solid yellow colour/glow and a flat normal map."""
    import numpy as np
    before = set(bpy.data.materials.keys())
    m.CreateModdedMaterial('emissive')
    mat = bpy.data.materials[next(k for k in bpy.data.materials.keys() if k not in before)]
    fills = {'BaseColorMetalMap': (*COLOR, 0.0), 'EmissiveFStop10IntensityMap': (*COLOR, 1.0),
             'NormalXyAoRoughMap': (0.5, 0.5, 1.0, 0.6)}
    for n in mat.node_tree.nodes:
        if n.type != 'TEX_IMAGE' or not n.image: continue
        key = next((k for k in fills if k in n.label or k in n.name), None)
        if key is None: continue
        img = bpy.data.images.new(f'hd2dress_{key}', 64, 64, alpha=True)
        img.pixels = list(fills[key]) * (64 * 64)
        path = os.path.join(OUTDIR, f'hd2dress_{key}.png')
        img.filepath_raw = path; img.file_format = 'PNG'; img.save()
        img.filepath = path
        if 'Normal' in key: img.colorspace_settings.name = 'Non-Color'
        n.image = img
    print('RIG material', mat.name)
    return mat


def strip_geometry():
    """Return (verts, faces, groups per vertex, meta). Top rows are pinned (by the cloth generator)."""
    verts, faces, groups, meta = [], [], [], []
    def strips(ring_z, ring_r, bone, prefix):
        for name, ang, length in STRIPS:
            a = math.radians(ang)
            out = mathutils.Vector((-math.sin(a), math.cos(a), 0)); side = mathutils.Vector((math.cos(a), math.sin(a), 0))
            rows = int(round(length / ROW)) + 1; first = len(verts)
            for r in range(rows):
                for c in range(3):
                    verts.append(out * (ring_r + r * ROW * FLARE) + side * ((c - 1) * WIDTH / 2) + mathutils.Vector((0, 0, ring_z - r * ROW)))
                    groups.append(bone)
            for r in range(rows - 1):
                for c in range(2):
                    i = first + r * 3 + c; faces.append((i, i + 1, i + 4, i + 3))
            meta.append(dict(name=prefix + name, angle=ang, length=length, rows=rows, cols=3, first=first, count=rows * 3, bone=bone))
    def skirt():
        rows = int(round(SKIRT_LENGTH / ROW)) + 1; first = len(verts); n = SKIRT_SEGMENTS
        for r in range(rows):
            for k in range(n):
                a = 2 * math.pi * k / n
                out = mathutils.Vector((-math.sin(a), math.cos(a), 0))
                verts.append(out * (RING_R + r * ROW * FLARE) + mathutils.Vector((0, 0, RING_Z - r * ROW))); groups.append('hips')
        for r in range(rows - 1):
            for k in range(n):
                a_, b_ = first + r * n + k, first + r * n + (k + 1) % n
                faces.append((a_, b_, b_ + n, a_ + n))
        meta.append(dict(name='skirt', angle=None, length=SKIRT_LENGTH, rows=rows, cols=n, first=first, count=rows * n, bone='hips'))
    if LAYOUT == 'skirt_shoulders':
        skirt(); strips(SH_Z, SH_R, 'chest', 'shoulder_')
    elif LAYOUT == 'skirt':
        skirt()
    else:
        strips(RING_Z, RING_R, 'hips', '')
    return verts, faces, groups, meta


def add_strips(obj, verts, faces, groups):
    me = bpy.data.meshes.new('hd2dress_strips')
    # the cape has THREE identical UV sets (UV0 = UV1 = UV2) and the cape shader reads some textures (the ID mask)
    # through a later set: make sure the host has 3 layers, so the export does not write zeros for UV2
    while len(obj.data.uv_layers) < 3:
        src = obj.data.uv_layers[0]; nl = obj.data.uv_layers.new(name=f'UVMap.{len(obj.data.uv_layers):03d}')
        for i, d in enumerate(src.data): nl.data[i].uv = d.uv
    fo = bpy.data.objects.new('hd2dress_strips', me); bpy.context.scene.collection.objects.link(fo)
    gidx = {g: fo.vertex_groups.new(name=g).index for g in sorted(set(groups))}
    if ROOT_IN_PALETTE: gidx['root'] = fo.vertex_groups.new(name='root').index
    bm = bmesh.new(); dl = bm.verts.layers.deform.verify()
    bv = []
    for k_, (p, g) in enumerate(zip(verts, groups)):
        v = bm.verts.new(p); v[dl][gidx[g]] = 1.0; bv.append(v)
        # one tiny root weight puts 'root' in the mesh's bone palette, so the render copy can be skinned to root
        # (character shaders skin the already-moved cloth again; root skinning makes that second move correct)
        if ROOT_IN_PALETTE and k_ == 0: v[dl][gidx['root']] = 0.001
    for f in faces: bm.faces.new([bv[i] for i in f])
    # back side: a second layer facing the other way. NOT for cloth: the cape shader is two-sided already, and two
    # coincident layers z-fight (blocky light/dark squares that turn to static when the cloth moves, 2026-10-18)
    if DOUBLE_SIDED:
        back = []
        for p, g in zip(verts, groups):
            v = bm.verts.new(p); v[dl][gidx[g]] = 1.0; back.append(v)
        for f in faces: bm.faces.new([back[i] for i in reversed(f)])
    # faces must point OUTWARD: the cape shader colours back faces with the cape's "inside" row (2026-10-18: the skirt
    # showed the inside colour from outside). Turn every face away from the body's vertical axis.
    bm.normal_update()
    wrong = [f for f in bm.faces if f.normal.x * f.calc_center_median().x + f.normal.y * f.calc_center_median().y < 0]
    if wrong: bmesh.ops.reverse_faces(bm, faces=wrong)
    print(f'RIG faces turned outward: {len(wrong)} of {len(bm.faces)}')
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(me); bm.free()
    for uv in obj.data.uv_layers:
        lay = me.uv_layers.new(name=uv.name)
        if UV_MODE == 'single':
            # one texel for every cloth vertex. Blender's default maps the WHOLE texture onto each face ("metal
            # grate"); but a single UV leaves the shader's per-pixel tangent frame (built from UV derivatives, HD2
            # meshes store no tangents) degenerate: the "camo squares" (2026-10-18)
            for d in lay.data: d.uv = (CLOTH_UV, CLOTH_UV)
        else:
            # continuous cylinder unwrap (the cape has UV0 = UV1 = UV2): u = angle around the body (0..1, front
            # = 0.5), v = height in metres. Faces across the seam at the back get u + 1 on their low side.
            for f in me.polygons:
                us = []
                for li in f.loop_indices:
                    co = me.vertices[me.loops[li].vertex_index].co
                    us.append((math.atan2(co.x, co.y) / (2 * math.pi) + 0.5, co.z))   # front (+Y) = 0.5, seam at the back
                if max(u for u, _ in us) - min(u for u, _ in us) > 0.5:
                    us = [(u + 1.0 if u < 0.5 else u, v) for u, v in us]
                for li, (u, v) in zip(f.loop_indices, us): lay.data[li].uv = (u * UV_TILE_U, v * UV_TILE_V)
    me.materials.append(STRIP_MAT or obj.material_slots[0].material)
    fo.matrix_world = mathutils.Matrix.Identity(4)
    me.transform(obj.matrix_world.inverted())
    fo.matrix_world = obj.matrix_world.copy()
    bpy.ops.object.select_all(action='DESELECT')
    fo.select_set(True); obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    before = len(obj.data.vertices)
    bpy.ops.object.join()
    print(f'RIG strips into {obj.name}: {before} -> {len(obj.data.vertices)} verts')
    return before


SAME_MATERIAL = os.environ.get('TESTRIG_SAME_MATERIAL') == '1'   # diagnostic: strips in the hip's own material
STRIP_MAT = None if SAME_MATERIAL else make_material()
verts, faces, groups, meta = strip_geometry()
layout = dict(strips=meta, ring_z=RING_Z, ring_r=RING_R, width=WIDTH, row=ROW,
              positions=[list(p) for p in verts], faces=faces, extra_bones=[n for n, _ in EXTRA_BONES], hosts={})
for h in HOSTS:
    o = units[h]
    add_bones(rig_of(o))
    layout['hosts'][h] = dict(original_vertices=add_strips(o, verts, faces, groups), unit=int(o['Z_ObjectID']))

FORCE_MAT = os.environ.get('TESTRIG_MATERIAL_ID')        # diagnostic: every slot of the host meshes -> this material id
if FORCE_MAT:
    fm = bpy.data.materials.get(FORCE_MAT) or bpy.data.materials.new(FORCE_MAT)
    for h in HOSTS:
        for slot in units[h].material_slots: slot.material = fm
    print('RIG forced material', FORCE_MAT)
bpy.ops.object.select_all(action='DESELECT')
for h in HOSTS: units[h].select_set(True)
bpy.context.view_layer.objects.active = units[HOSTS[0]]
print('RIG batchsave', bpy.ops.helldiver2.archive_unit_batchsave())
if STRIP_MAT: print('RIG material save', TM.Save(int(STRIP_MAT.name), m.MaterialID))
assert TM.ActivePatch.Path == PATCH_FILE, TM.ActivePatch.Path
TM.PatchActiveArchive()
json.dump(layout, open(os.path.join(OUTDIR, 'testrig_strips.json'), 'w'), indent=1)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUTDIR, 'testrig.blend'))
print('RIG wrote', PATCH_FILE)
