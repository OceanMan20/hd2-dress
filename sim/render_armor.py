"""Render a real armour mod moving with the game's animations and HD2 Dress physics.
   ~/apps/blender-5.2.2-linux-x64/blender -b -P sim/render_armor.py -- PREP.json SIM.csv OUT.mp4 \
        --mod MOD_PATCH --rig RIG_PATCH [--body Stocky] [--size 960x720] [--title TEXT] [--textures]
PREP.json: from sim/prepare.py (every joint per frame: run anim_export.py with --all-bones).
SIM.csv:   from sim/run_sim.lua with DRESS= this rig's chains (sim/dress_rest.py).
Left: the dress with HD2 Dress physics (the rigged piece, its dress bones following the simulation).
Right: the same mod as published (its original piece, plain skinning). Same animation, side by side."""
import bpy, sys, os, json, math, mathutils, subprocess, tempfile, shutil, addon_utils
args = sys.argv[sys.argv.index('--') + 1:]
PREP, SIM, OUT = args[0], args[1], args[2]
def opt(name, default=None): return args[args.index(name) + 1] if name in args else default
MOD, RIG = os.path.abspath(opt('--mod')), os.path.abspath(opt('--rig'))
BODY = opt('--body', 'Stocky')
W, H = (int(x) for x in opt('--size', '960x720').split('x'))
TITLE = opt('--title', 'HD2 Dress')
TEX = '--textures' in args
CAM = mathutils.Vector([float(x) for x in opt('--cam', '-2.3,-1.9,0.35').split(',')])   # camera offset from the hips (m)
LENS = float(opt('--lens', '38'))

addon_utils.enable('HD2SDK-CommunityEdition'); m = sys.modules['HD2SDK-CommunityEdition']
G = os.path.expanduser('~/.local/share/Steam/steamapps/common/Helldivers 2/data/'); m.Global_gamepath = G
sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(G)
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
st = bpy.context.scene.Hd2ToolPanelSettings; st.ImportMaterials = TEX; st.ImportLods = False
TM = m.Global_TocManager
TM.LoadArchive(G + m.BaseArchiveHexID, True, False)
modp = TM.LoadArchive(MOD, True, True)
def load_units(arch, uids, tag):
    got = []
    for uid in uids:
        before = set(bpy.data.objects)
        e = arch.TocDict[m.UnitID][uid]
        e.Load(True, True)
        new = [o for o in bpy.data.objects if o not in before]
        for o in new: o['set'] = tag
        got += new
    return got
def body_ok(o):
    n = o.name
    if 'Slim' in n and BODY != 'Slim': return False
    if 'Stocky' in n and BODY != 'Stocky': return False
    return True
# the published mod: every visible piece of this body type
orig = load_units(modp, list(modp.TocDict[m.UnitID].keys()), 'orig')
mesh_orig = [o for o in orig if o.type == 'MESH' and len(o.data.vertices) > 100 and body_ok(o)]
heads = [o for o in mesh_orig if o.name[0].isdigit()]
for h in heads[1:]: mesh_orig.remove(h)                      # two identical head pieces: keep one
for o in orig:
    if o.type == 'MESH' and o not in mesh_orig: o.hide_render = True
# the rigged dress piece (replaces the original torso in the physics copy)
rigp = TM.LoadArchive(RIG, True, True)
rigged = load_units(rigp, list(rigp.TocDict[m.UnitID].keys()), 'phys')
dress = next(o for o in rigged if o.type == 'MESH' and BODY in o.name)
for o in rigged:
    if o.type == 'MESH' and o is not dress: o.hide_render = True
dress_orig = next(o for o in mesh_orig if o.name.split('.')[0] == dress.name.split('.')[0] or o.name.startswith(dress.name.split('_lod')[0]))
print('ARMOR pieces', [o.name for o in mesh_orig], 'dress', dress.name, 'original', dress_orig.name)

def rig_of(o): return next((md.object for md in o.modifiers if md.type == 'ARMATURE'), None)
D = json.load(open(PREP))
frames = D['frames']
# the physics copy = the original pieces (minus its torso) + the rigged dress, shifted left; the
# published copy shifted right. Each copy gets one master rig; every piece's rig copies it.
SHIFT = {'phys': mathutils.Vector((-0.55, 0.45, 0)), 'orig': mathutils.Vector((0.55, -0.45, 0))}   # side by side as seen from the camera
def make_copy(tag, pieces):
    objs = []
    for o in pieces:
        if tag == 'phys':
            c = o.copy(); c.data = o.data; bpy.context.scene.collection.objects.link(c)
            r = rig_of(o).copy(); bpy.context.scene.collection.objects.link(r)
            for md in c.modifiers:
                if md.type == 'ARMATURE': md.object = r
            c.parent = r
            objs.append(c)
        else:
            objs.append(o)
    return objs
phys_pieces = make_copy('phys', [o for o in mesh_orig if o is not dress_orig]) + [dress]
orig_pieces = mesh_orig
for o in mesh_orig: o.hide_render = False
masters = {'phys': rig_of(dress), 'orig': rig_of(dress_orig)}
for tag, pieces in (('phys', phys_pieces), ('orig', orig_pieces)):
    master = masters[tag]
    for o in pieces:
        r = rig_of(o)
        if r is master: continue
        for pb in r.pose.bones:
            if pb.name in master.pose.bones:
                c = pb.constraints.new('COPY_TRANSFORMS'); c.target = master; c.subtarget = pb.name
for tag, master in masters.items():
    master.location = SHIFT[tag]

def depth(b):
    d = 0
    while b.parent: b, d = b.parent, d + 1
    return d
def levels(rig, names):
    by = {}
    for n in names:
        if n in rig.pose.bones: by.setdefault(depth(rig.pose.bones[n]), []).append(n)
    return [by[k] for k in sorted(by)]
anim_levels = {tag: levels(r, [b for b in D['bones'] if not b.startswith('dress_')]) for tag, r in masters.items()}

# simulation output
rows = []
with open(SIM) as f:
    hdr = f.readline().strip().split(',')
    for line in f:
        if line.startswith('#'): meta = dict(kv.split('=') for kv in line[1:].split()); continue
        rows.append([float(x) for x in line.strip().split(',')])
col = {h: i for i, h in enumerate(hdr)}
NC, NS = int(meta['N_CHAINS']), int(meta['SEGS'])
NT, TS = int(meta.get('TAILS', 0)), int(meta.get('TAIL_SEGS', 0))
def simp(r, c, j): return mathutils.Vector((r[col[f'phys_c{c}_j{j}_x']], r[col[f'phys_c{c}_j{j}_y']], r[col[f'phys_c{c}_j{j}_z']]))

def pose_body(tag, fr):
    rig = masters[tag]; inv = rig.matrix_world.inverted()
    for lvl in anim_levels[tag]:
        for n in lvl:
            v = fr[n]
            M = mathutils.Matrix.LocRotScale(mathutils.Vector(v[:3]) + SHIFT[tag], mathutils.Quaternion(v[3:7]), None)
            rig.pose.bones[n].matrix = inv @ M
        bpy.context.view_layer.update()
H32 = sys.modules['HD2SDK-CommunityEdition.utils.hashing'].murmur32_hash
def dname(c, k, prefix='dress_c'):   # added bones come back from the patch under their hash (the SDK has no name for them)
    n = f'{prefix}{c:02d}_b{k}'
    return n if n in masters['phys'].pose.bones else str(H32(n.encode()))
def tailp(r, t, j): return mathutils.Vector((r[col[f'tail{t}_j{j}_x']], r[col[f'tail{t}_j{j}_y']], r[col[f'tail{t}_j{j}_z']]))
def aim(pb, want):
    cur = pb.matrix.copy(); head = cur.translation
    y = cur.to_3x3() @ mathutils.Vector((0, 1, 0))
    R = y.rotation_difference(want).to_matrix().to_4x4()
    rot = R @ mathutils.Matrix(cur.to_3x3()).to_4x4(); rot.translation = head
    pb.matrix = rot
def pose_dress(r):
    rig = masters['phys']; inv = rig.matrix_world.inverted()
    for k in range(1, NS + 1):
        for c in range(1, NC + 1):
            pb = rig.pose.bones[dname(c, k)]
            pb.matrix_basis = mathutils.Matrix.Identity(4)
        bpy.context.view_layer.update()
        for c in range(1, NC + 1):
            pb = rig.pose.bones[dname(c, k)]
            cur = pb.matrix.copy()                                   # rest pose under the moved parent
            head = cur.translation
            want = inv.to_3x3() @ (simp(r, c, k) - simp(r, c, k - 1))
            y = cur.to_3x3() @ mathutils.Vector((0, 1, 0))
            R = y.rotation_difference(want).to_matrix().to_4x4()
            rot = R @ mathutils.Matrix(cur.to_3x3()).to_4x4()
            rot.translation = head
            pb.matrix = rot
        bpy.context.view_layer.update()
    for k in range(1, TS + 1):          # the tail, same way
        for t in range(1, NT + 1):
            pb = rig.pose.bones[dname(t, k, 'dress_t')]
            pb.matrix_basis = mathutils.Matrix.Identity(4)
        bpy.context.view_layer.update()
        for t in range(1, NT + 1):
            aim(rig.pose.bones[dname(t, k, 'dress_t')], inv.to_3x3() @ (tailp(r, t, k) - tailp(r, t, k - 1)))
        bpy.context.view_layer.update()

sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.light = 'STUDIO'; sc.display.shading.color_type = 'TEXTURE' if TEX else 'MATERIAL'
sc.display.shading.show_shadows = True; sc.display.shading.show_cavity = True
sc.render.resolution_x, sc.render.resolution_y = W, H
wd = bpy.data.worlds.new('w'); sc.world = wd; wd.color = (0.08, 0.09, 0.11)
if not TEX:
    cloth = bpy.data.materials.new('cloth'); cloth.diffuse_color = (0.62, 0.6, 0.56, 1)
    for o in phys_pieces + orig_pieces:
        o.data.materials.clear() if o.data.users == 1 else None
        for i in range(len(o.material_slots)): o.material_slots[i].link = 'OBJECT'; o.material_slots[i].material = cloth
bpy.ops.mesh.primitive_plane_add(size=200)
fl = bpy.data.materials.new('floor'); fl.diffuse_color = (0.18, 0.19, 0.21, 1); bpy.context.active_object.data.materials.append(fl)
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = LENS

_cache = os.path.expanduser('~/.cache/hd2-dress'); os.makedirs(_cache, exist_ok=True)
tmp = tempfile.mkdtemp(prefix='armor_render_', dir=_cache)   # not /tmp: Dolphin thumbnailed every frame (2026-10-15)
n = min(len(frames), len(rows))
for i in range(n):
    fr, r = frames[i], rows[i]
    pose_body('phys', fr); pose_body('orig', fr)
    pose_dress(r)
    hips = mathutils.Vector(fr['hips'][:3])
    target = mathutils.Vector((hips.x, hips.y, 0.9))
    cam.location = target + CAM
    cam.rotation_mode = 'QUATERNION'; cam.rotation_quaternion = (target - cam.location).to_track_quat('-Z', 'Y')
    sc.render.filepath = os.path.join(tmp, f'{i:05d}.png')
    bpy.ops.render.render(write_still=True)
    if i % 20 == 0: print(f'ARMOR {i}/{n}', flush=True)
fps = D['fps']
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(fps), '-i', os.path.join(tmp, '%05d.png'),
                '-vf', f"drawtext=text='{TITLE}':x=12:y=12:fontsize=18:fontcolor=white,"
                       f"drawtext=text='LEFT  HD2 Dress physics (auto-rig)      RIGHT  the mod as published':x=12:y=h-30:fontsize=16:fontcolor=white",
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', OUT], check=True)
shutil.rmtree(tmp)
print('ARMOR wrote', OUT)
