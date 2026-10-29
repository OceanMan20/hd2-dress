"""Render a simulator run (sim/run_sim.lua CSV) to a video: the Helldiver's legs/spine as sticks, the
skirt as a cloth surface. Physics skirt on the left, rigid skirt (plain skinning) on the right, same
motion, so the difference is easy to see.
   ~/apps/blender-5.2.2-linux-x64/blender -b -P sim/render.py -- RUN.csv OUT.mp4 [--size 960x540] [--every 1] [--title TEXT]"""
import bpy, bmesh, sys, os, csv, math, mathutils, subprocess, tempfile, shutil
args = sys.argv[sys.argv.index('--') + 1:]
src, out = args[0], args[1]
def opt(name, default):
    return args[args.index(name) + 1] if name in args else default
W, H = (int(x) for x in opt('--size', '960x540').split('x'))
EVERY = int(opt('--every', '1'))
TITLE = opt('--title', os.path.basename(src))

rows, meta = [], {}
with open(src) as f:
    hdr = f.readline().strip().split(',')
    for line in f:
        if line.startswith('#'):
            meta = dict(kv.split('=') for kv in line[1:].split()); continue
        rows.append([float(x) for x in line.strip().split(',')])
col = {h: i for i, h in enumerate(hdr)}
NC, NS, FPS = int(meta['N_CHAINS']), int(meta['SEGS']), float(meta['fps'])
def P(r, name): return mathutils.Vector((r[col[name + '_x']], r[col[name + '_y']], r[col[name + '_z']]))

for o in list(bpy.data.objects): bpy.data.objects.remove(o)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.light = 'STUDIO'; sc.display.shading.color_type = 'MATERIAL'
sc.display.shading.show_shadows = True; sc.display.shading.show_cavity = True
sc.render.resolution_x, sc.render.resolution_y = W, H
sc.render.film_transparent = False
w = bpy.data.worlds.new('w'); sc.world = w; w.color = (0.08, 0.09, 0.11)

def mat(name, rgb):
    m = bpy.data.materials.new(name); m.diffuse_color = (*rgb, 1); return m
M_BODY, M_PHYS, M_RIGID, M_FLOOR = mat('body', (0.75, 0.72, 0.66)), mat('phys', (0.55, 0.12, 0.2)), mat('rigid', (0.25, 0.3, 0.45)), mat('floor', (0.2, 0.21, 0.23))

STICKS = [('hips', 'spine1'), ('spine1', 'head'), ('hips', 'l_thigh'), ('hips', 'r_thigh'),
          ('l_thigh', 'l_knee'), ('l_knee', 'l_foot'), ('l_foot', 'l_toe'),
          ('r_thigh', 'r_knee'), ('r_knee', 'r_foot'), ('r_foot', 'r_toe')]
RADIUS = {('l_thigh', 'l_knee'): 0.085, ('r_thigh', 'r_knee'): 0.085, ('l_knee', 'l_foot'): 0.06, ('r_knee', 'r_foot'): 0.06}

def make_body(tag):
    objs = []
    for a, b in STICKS:
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=RADIUS.get((a, b), 0.035), depth=1)
        o = bpy.context.active_object; o.name = f'{tag}_{a}_{b}'; o.data.materials.append(M_BODY); objs.append((o, a, b))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.11, segments=16, ring_count=8)
    head = bpy.context.active_object; head.data.materials.append(M_BODY)
    return objs, head
def place(o, p, q):
    d = q - p; L = d.length or 1e-4
    o.location = (p + q) / 2
    o.rotation_mode = 'QUATERNION'
    o.rotation_quaternion = mathutils.Vector((0, 0, 1)).rotation_difference(d.normalized())
    o.scale = (1, 1, L)

def make_skirt(tag, m):
    me = bpy.data.meshes.new(tag)
    verts = [(0, 0, 0)] * (NC * (NS + 1))
    faces = []
    for c in range(NC):
        c2 = (c + 1) % NC
        for j in range(NS):
            faces.append((c * (NS + 1) + j, c2 * (NS + 1) + j, c2 * (NS + 1) + j + 1, c * (NS + 1) + j + 1))
    me.from_pydata(verts, [], faces)
    o = bpy.data.objects.new(tag, me); sc.collection.objects.link(o); me.materials.append(m)
    sol = o.modifiers.new('thick', 'SOLIDIFY'); sol.thickness = 0.006; sol.offset = 0   # centred: no smoothing,
    # which would pull the cloth inward and show clipping the simulation does not have
    return o

OFFSET = {'phys': mathutils.Vector((-0.6, 0, 0)), 'rigid': mathutils.Vector((0.6, 0, 0))}
scenes = {}
for kind, m in (('phys', M_PHYS), ('rigid', M_RIGID)):
    body, head = make_body(kind)
    scenes[kind] = (body, head, make_skirt(f'skirt_{kind}', m))
bpy.ops.mesh.primitive_plane_add(size=200); bpy.context.active_object.data.materials.append(M_FLOOR)

cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 35

_cache = os.path.expanduser('~/.cache/hd2-dress'); os.makedirs(_cache, exist_ok=True)
tmp = tempfile.mkdtemp(prefix='dress_render_', dir=_cache)   # not /tmp: Dolphin thumbnailed every frame (2026-10-15)
frames = rows[::EVERY]
for n, r in enumerate(frames):
    hips = P(r, 'hips')
    for kind, (body, head, skirt) in scenes.items():
        off = OFFSET[kind]
        for o, a, b in body: place(o, P(r, a) + off, P(r, b) + off)
        head.location = P(r, 'head') + off + mathutils.Vector((0, 0, 0.08))
        vs = skirt.data.vertices
        for c in range(NC):
            for j in range(NS + 1):
                vs[c * (NS + 1) + j].co = P(r, f'{kind}_c{c + 1}_j{j}') + off
        skirt.data.update()
    # camera: behind-left, following the hips (3/4 rear view, like the game's third person)
    target = mathutils.Vector((hips.x, hips.y, 0.75))
    cam.location = target + mathutils.Vector((-2.2, -3.4, 0.9))
    cam.rotation_mode = 'QUATERNION'
    cam.rotation_quaternion = (target - cam.location).to_track_quat('-Z', 'Y')
    sc.render.filepath = os.path.join(tmp, f'{n:05d}.png')
    bpy.ops.render.render(write_still=True)
    if n % 30 == 0: print(f'RENDER {n}/{len(frames)}', flush=True)
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS / EVERY), '-i', os.path.join(tmp, '%05d.png'),
                '-vf', f"drawtext=text='{TITLE}':x=12:y=12:fontsize=18:fontcolor=white,"
                f"drawtext=text='RED = physics + leg collision    BLUE = rigid (plain skinning, what model mods get)':x=12:y=h-30:fontsize=16:fontcolor=white", '-c:v', 'libx264', '-pix_fmt', 'yuv420p', out], check=True)
shutil.rmtree(tmp)
print('RENDER wrote', out)
