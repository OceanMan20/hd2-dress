"""Render a preview of a cloth's LOOK in Blender (no game needed): the colour map, normal map, roughness and the
optional tiled weave detail, on the mesh's own UVs. Shows texture placement and surface detail; it does NOT run the
game's shader or the cloth physics (the cloth hangs in its modelled rest shape).
    blender -b SCENE.blend -P tools/hd2dress_preview.py -- --settings my_dress.toml --object OBJ [--out out.png]
        [--views front,side,back] [--size 900] [--samples 48]"""
import bpy, sys, os, math, mathutils
try: import tomllib
except ModuleNotFoundError:                 # Python 3.10 (Blender 4.0/4.1): the same parser, bundled as tomli
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '_vendor')); import tomli as tomllib
args = sys.argv[sys.argv.index('--') + 1:]
def opt(n, d=None): return args[args.index(n) + 1] if n in args else d
st = tomllib.load(open(opt('--settings'), 'rb')); look = st.get('look', {})
sdir = os.path.dirname(os.path.abspath(opt('--settings')))
rel = lambda p: os.path.expanduser(p) if os.path.isabs(os.path.expanduser(p)) else os.path.join(sdir, p)
obj = bpy.data.objects[opt('--object')]
out = opt('--out', os.path.join(sdir, 'preview.png')); size = int(opt('--size', 900)); samples = int(opt('--samples', 48))
views = opt('--views', 'front,side,back').split(',')
for o in bpy.data.objects:                         # only the dressed object (and its armature) in the shot
    if o is not obj and o.type == 'MESH': o.hide_render = True
mat = bpy.data.materials.new('hd2dress_preview'); mat.use_nodes = True
nt = mat.node_tree; N = nt.nodes; L = nt.links
bsdf = next(n for n in N if n.type == 'BSDF_PRINCIPLED')
uv = N.new('ShaderNodeUVMap'); uv.uv_map = obj.data.uv_layers[0].name
def img(path, color=True):
    t = N.new('ShaderNodeTexImage'); t.image = bpy.data.images.load(rel(path))
    if not color: t.image.colorspace_settings.name = 'Non-Color'
    return t
col = img(look['color']); L.new(uv.outputs['UV'], col.inputs['Vector']); L.new(col.outputs['Color'], bsdf.inputs['Base Color'])
bsdf.inputs['Roughness'].default_value = float(look.get('roughness', 0.7))
if look.get('roughness_map'):
    rough = img(look['roughness_map'], False); L.new(uv.outputs['UV'], rough.inputs['Vector']); L.new(rough.outputs['Color'], bsdf.inputs['Roughness'])
normal_out = None
if look.get('normal'):
    nm = img(look['normal'], False); L.new(uv.outputs['UV'], nm.inputs['Vector'])
    nmap = N.new('ShaderNodeNormalMap'); L.new(nm.outputs['Color'], nmap.inputs['Color']); normal_out = nmap.outputs['Normal']
if look.get('weave'):                              # tiled detail normal, layered on top (Blender: bump-like mix)
    mp = N.new('ShaderNodeMapping'); t_ = float(look.get('weave_tiling', 40.0)); mp.inputs['Scale'].default_value = (t_, t_, 1)
    L.new(uv.outputs['UV'], mp.inputs['Vector'])
    wv = img(look['weave'], False); L.new(mp.outputs['Vector'], wv.inputs['Vector'])
    wmap = N.new('ShaderNodeNormalMap'); wmap.inputs['Strength'].default_value = float(look.get('weave_strength', 1.0))
    L.new(wv.outputs['Color'], wmap.inputs['Color'])
    if normal_out is not None:                     # combine: add the detail's tangent-space offset to the base normal
        mix = N.new('ShaderNodeVectorMath'); mix.operation = 'ADD'; L.new(normal_out, mix.inputs[0]); L.new(wmap.outputs['Normal'], mix.inputs[1])
        nrm = N.new('ShaderNodeVectorMath'); nrm.operation = 'NORMALIZE'; L.new(mix.outputs[0], nrm.inputs[0]); normal_out = nrm.outputs[0]
    else: normal_out = wmap.outputs['Normal']
if normal_out is not None: L.new(normal_out, bsdf.inputs['Normal'])
# only the cloth (vertex groups "cloth" / "cloth_<piece>") gets the look; the rest of the armour renders neutral grey
me = obj.data
gi = {g.index for g in obj.vertex_groups if g.name == 'cloth' or g.name.startswith('cloth_')}
cv = {v.index for v in me.vertices if any(x.group in gi and x.weight > 0.5 for x in v.groups)}
grey = bpy.data.materials.new('hd2dress_preview_armour'); grey.use_nodes = True
gb = next(n for n in grey.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
gb.inputs['Base Color'].default_value = (0.32, 0.32, 0.34, 1); gb.inputs['Roughness'].default_value = 0.6
me.materials.clear(); me.materials.append(grey); me.materials.append(mat)
for f in me.polygons: f.material_index = 1 if (not cv or all(i in cv for i in f.vertices)) else 0
# scene: camera, three-point lighting, neutral world
sc = bpy.context.scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = samples; sc.cycles.device = 'CPU'
sc.render.resolution_x = sc.render.resolution_y = size; sc.render.film_transparent = False
w = bpy.data.worlds.new('w'); w.use_nodes = True; w.node_tree.nodes['Background'].inputs[0].default_value = (0.18, 0.18, 0.2, 1); sc.world = w
bb = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
ctr = sum(bb, mathutils.Vector()) / 8; h = max(c.z for c in bb) - min(c.z for c in bb)
tgt = bpy.data.objects.new('t', None); sc.collection.objects.link(tgt); tgt.location = ctr
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 50; tr = cam.constraints.new('TRACK_TO'); tr.target = tgt; tr.track_axis = 'TRACK_NEGATIVE_Z'; tr.up_axis = 'UP_Y'
for nm_, loc, e in (('key', (2, 2.5, 2.5), 400), ('fill', (-2.5, 1.5, 1.5), 150), ('rim', (0, -2.5, 2.0), 250)):
    l = bpy.data.objects.new(nm_, bpy.data.lights.new(nm_, 'AREA')); l.data.energy = e; l.data.size = 2; l.location = loc
    sc.collection.objects.link(l); c = l.constraints.new('TRACK_TO'); c.target = tgt; c.track_axis = 'TRACK_NEGATIVE_Z'
dist = h * 2.6
dirs = {'front': (0, 1), 'side': (1, 0), 'back': (0, -1), 'front_left': (-0.7, 0.7)}
files = []
for v in views:
    dx, dy = dirs[v]; cam.location = ctr + mathutils.Vector((dx * dist, dy * dist, h * 0.25))
    f = os.path.splitext(out)[0] + f'_{v}.png'; sc.render.filepath = f; bpy.ops.render.render(write_still=True); files.append(f)
print('PREVIEW', ' '.join(files))
