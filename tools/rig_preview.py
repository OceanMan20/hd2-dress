"""Show what the auto-rig did: the dress coloured by which bone strip moves each part, the bones
drawn on top, as stills (front / side / back) and a video (turntable, then each strip bending).
   ~/apps/blender-5.2.2-linux-x64/blender -b -P tools/rig_preview.py -- MOD_PATCH RIG_PATCH OUTDIR [--body Stocky] [--size 720x900]
Colours: one hue per strip (12 around the body); the tail in white-gold; grey = still follows the
body (waistband, bodice); the shade gets lighter down each strip. Writes OUTDIR/rig_front.png,
rig_side.png, rig_back.png, rig_threequarter.png and OUTDIR/rig_preview.mp4."""
import bpy, bmesh, sys, os, math, colorsys, mathutils, subprocess, tempfile, shutil, addon_utils
args = sys.argv[sys.argv.index('--') + 1:]
MOD, RIG, OUT = (os.path.abspath(a) for a in args[:3])
def opt(name, default=None): return args[args.index(name) + 1] if name in args else default
BODY = opt('--body', 'Stocky')
W, H = (int(x) for x in opt('--size', '720x900').split('x'))
os.makedirs(OUT, exist_ok=True)

addon_utils.enable('HD2SDK-CommunityEdition'); m = sys.modules['HD2SDK-CommunityEdition']
G = os.path.expanduser('~/.local/share/Steam/steamapps/common/Helldivers 2/data/'); m.Global_gamepath = G
sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(G)
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
st = bpy.context.scene.Hd2ToolPanelSettings; st.ImportMaterials = False; st.ImportLods = False
TM = m.Global_TocManager
TM.LoadArchive(G + m.BaseArchiveHexID, True, False)
TM.LoadArchive(MOD, True, True)
rigp = TM.LoadArchive(RIG, True, True)
for uid in rigp.TocDict[m.UnitID]:
    rigp.TocDict[m.UnitID][uid].Load(True, True)
dress = next(o for o in bpy.data.objects if o.type == 'MESH' and BODY in o.name)
for o in list(bpy.data.objects):
    if o.type == 'MESH' and o is not dress: bpy.data.objects.remove(o)
rig = next(md.object for md in dress.modifiers if md.type == 'ARMATURE')

# added bones come back under their murmur32 hash: map them to names
H32 = sys.modules['HD2SDK-CommunityEdition.utils.hashing'].murmur32_hash
names = {}
for c in range(1, 33):
    for k in range(1, 13):
        n = f'dress_c{c:02d}_b{k}'; names[str(H32(n.encode()))] = n; names[n] = n
for t in range(1, 5):
    for k in range(1, 13):
        n = f'dress_t{t:02d}_b{k}'; names[str(H32(n.encode()))] = n; names[n] = n
def parse(n):
    n = names.get(n)
    if not n: return None
    kind = 'tail' if n.startswith('dress_t') else 'chain'
    idx, k = int(n[7:9]), int(n.split('_b')[1])
    return kind, idx, k
NC = max([parse(b.name)[1] for b in rig.data.bones if parse(b.name) and parse(b.name)[0] == 'chain'] or [12])
NK = max([parse(b.name)[2] for b in rig.data.bones if parse(b.name) and parse(b.name)[0] == 'chain'] or [6])

def colour(kind, idx, k, nk):
    light = 0.35 + 0.35 * (k - 1) / max(1, nk - 1)
    if kind == 'tail': return colorsys.hls_to_rgb(0.13, 0.55 + 0.3 * (k - 1) / max(1, nk - 1), 0.5)
    return colorsys.hls_to_rgb((idx - 1) / NC, light, 0.85)

# vertex colours: blend of the dress-bone colours by weight; grey for the body's own weights
gname = {g.index: g.name for g in dress.vertex_groups}
attr = dress.data.color_attributes.new('rig', 'BYTE_COLOR', 'POINT')
counts = {'chain': 0, 'tail': 0, 'body': 0}
for v in dress.data.vertices:
    r = g_ = b = 0.0; wsum = 0.0; dw = 0.0
    for ge in v.groups:
        p = parse(gname[ge.group])
        if p:
            cr, cg, cb = colour(p[0], p[1], p[2], NK if p[0] == 'chain' else 5)
            r += cr * ge.weight; g_ += cg * ge.weight; b += cb * ge.weight; dw += ge.weight
        wsum += ge.weight
    body = max(0.0, wsum - dw)
    r += 0.55 * body; g_ += 0.55 * body; b += 0.57 * body
    tot = max(1e-6, dw + body)
    attr.data[v.index].color = (r / tot, g_ / tot, b / tot, 1.0)
    counts['body' if dw < 0.5 * tot else ('tail' if any(parse(gname[ge.group]) and parse(gname[ge.group])[0] == 'tail' for ge in v.groups) else 'chain')] += 1
dress.data.color_attributes.active_color = attr
try: dress.data.color_attributes.render_color_index = dress.data.color_attributes.active_color_index
except Exception: pass
print('PREVIEW vertices moved by strips', counts['chain'], 'by the tail', counts['tail'], 'by the body', counts['body'])

# bones as sticks + joint balls, same colours, drawn through the cloth (x-ray via a second view layer is
# not available in Workbench stills, so the sticks are slightly thicker and the cloth a bit transparent)
mats = {}
def mat(key, rgb):
    if key not in mats:
        mt = bpy.data.materials.new(str(key)); mt.diffuse_color = (*rgb, 1); mats[key] = mt
    return mats[key]
sticks = []
# the SDK reloads every bone with a short fixed tail: draw joint -> next joint instead
heads = {}
for bone in rig.data.bones:
    p = parse(bone.name)
    if p: heads[p] = rig.matrix_world @ bone.head_local
def tail_of(p):
    nxt = (p[0], p[1], p[2] + 1)
    if nxt in heads: return heads[nxt]
    prv = (p[0], p[1], p[2] - 1)
    return heads[p] + (heads[p] - heads[prv]) if prv in heads else heads[p] + mathutils.Vector((0, 0, -0.12))
for bone in rig.data.bones:
    p = parse(bone.name)
    if not p: continue
    h = heads[p]; t = tail_of(p)
    rgb = colour(p[0], p[1], p[2], NK if p[0] == 'chain' else 5)
    rgb = tuple(min(1, c * 1.25) for c in rgb)
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.006, depth=(t - h).length)
    o = bpy.context.active_object; o.location = (h + t) / 2
    o.rotation_mode = 'QUATERNION'; o.rotation_quaternion = mathutils.Vector((0, 0, 1)).rotation_difference((t - h).normalized())
    o.data.materials.append(mat((p[0], p[1]), rgb)); sticks.append((o, bone.name))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.012, segments=10, ring_count=6, location=h)
    s = bpy.context.active_object; s.data.materials.append(mat((p[0], p[1]), rgb)); s.parent = None; sticks.append((s, bone.name))

sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'
sh = sc.display.shading
sh.light = 'STUDIO'; sh.color_type = 'VERTEX'; sh.show_xray = False; sh.show_cavity = True
sc.render.resolution_x, sc.render.resolution_y = W, H
wd = bpy.data.worlds.new('w'); sc.world = wd; wd.color = (0.12, 0.13, 0.15)
# sticks keep their material colour: give them an object colour too and use per-object shading via a
# second render pass is overkill; instead colour the sticks' vertices as well
for o, bn in sticks:
    a = o.data.color_attributes.new('rig', 'BYTE_COLOR', 'POINT')
    c = o.data.materials[0].diffuse_color
    for i in range(len(o.data.vertices)): a.data[i].color = (c[0], c[1], c[2], 1)
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = 'ORTHO'; cam.data.ortho_scale = 1.55
target = mathutils.Vector((0, -0.12, 0.8))
def look(az_deg, el=0.15):
    a = math.radians(az_deg)
    cam.location = target + mathutils.Vector((math.sin(a) * 4, math.cos(a) * 4, el * 4))
    cam.rotation_mode = 'QUATERNION'; cam.rotation_quaternion = (target - cam.location).to_track_quat('-Z', 'Y')
def shot(path):
    sc.render.filepath = path; bpy.ops.render.render(write_still=True)

# the bones are inside the cloth: render stills twice, cloth + bones, and bones alone over a ghost
dress.color = (1, 1, 1, 0.35)
for name, az in (('front', 0), ('threequarter', 35), ('side', 90), ('back', 180)):
    look(az); shot(os.path.join(OUT, f'rig_{name}.png'))
dress.hide_render = True
for name, az in (('front', 0), ('side', 90)):
    look(az); shot(os.path.join(OUT, f'bones_{name}.png'))
dress.hide_render = False

# video: a turntable, then every strip bending outward one after another, then the tail
tmp = tempfile.mkdtemp(prefix='rig_preview_', dir=os.path.expanduser('~/.cache/hd2-dress'))
frame = 0
def put():
    global frame
    sc.render.filepath = os.path.join(tmp, f'{frame:05d}.png'); bpy.ops.render.render(write_still=True); frame += 1
for i in range(72):
    look(i * 5); put()
look(30)
pbs = {}
for pb in rig.pose.bones:
    p = parse(pb.name)
    if p: pbs.setdefault((p[0], p[1]), {})[p[2]] = pb
order = [('chain', c) for c in range(1, NC + 1)] + [('tail', t) for t in range(1, 5) if ('tail', t) in pbs]
for key in order:
    chain = pbs.get(key, {})
    for step in list(range(0, 9)) + list(range(8, -1, -1)):
        ang = math.radians(4 * step)
        for k, pb in chain.items():
            pb.rotation_mode = 'XYZ'; pb.rotation_euler = (ang, 0, 0)
        bpy.context.view_layer.update()
        # move the stick/ball markers with their bones
        posed = {parse(pb.name): rig.matrix_world @ pb.head for pb in rig.pose.bones if parse(pb.name)}
        for o, bn in sticks:
            p = parse(bn); hd = posed[p]
            nxt = (p[0], p[1], p[2] + 1); prv = (p[0], p[1], p[2] - 1)
            tl = posed[nxt] if nxt in posed else (hd + (hd - posed[prv]) if prv in posed else hd + mathutils.Vector((0, 0, -0.12)))
            if o.name.startswith('Cylinder'):
                o.location = (hd + tl) / 2
                o.rotation_quaternion = mathutils.Vector((0, 0, 1)).rotation_difference((tl - hd).normalized())
            else:
                o.location = hd
        put()
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '24', '-i', os.path.join(tmp, '%05d.png'),
                '-vf', "drawtext=text='HD2 Dress auto-rig - colour = which bone strip moves that cloth, grey = follows the body':x=10:y=h-28:fontsize=15:fontcolor=white",
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', os.path.join(OUT, 'rig_preview.mp4')], check=True)
shutil.rmtree(tmp)
print('PREVIEW wrote', OUT)
