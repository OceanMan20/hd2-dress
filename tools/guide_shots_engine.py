"""Guide screenshots for the engine-cloth panel (docs/GUIDE.md), from a real Blender window.
   env -u WAYLAND_DISPLAY DISPLAY=:0 blender --window-geometry 0 0 1400 1300 SCENE.blend -P tools/guide_shots_engine.py -- ARMOUR_PATCH COLOUR OUT_DIR
SCENE: a copy of tests/fixtures/skirt_test.blend (the test edits it). Each picture draws ONE panel section (the panel is
long), runs the add-on like an author would, and saves the window plus the sidebar's position (OUT_DIR/shots.json).
Cut out with: python3 tools/guide_crop_engine.py OUT_DIR docs/img/guide"""
import bpy, addon_utils, sys, os, json, time
args = sys.argv[sys.argv.index('--') + 1:]
PATCH, COLOUR, OUT = (os.path.abspath(a) for a in args[:3])
os.makedirs(OUT, exist_ok=True)
addon_utils.enable('HD2SDK-CommunityEdition'); addon_utils.enable('hd2_dress')
import hd2_dress
from hd2_dress import jobs
PT = hd2_dress.HD2DRESS_PT_panel
ORIG_DRAW = PT.draw
META = {}
sc = bpy.context.scene; props = sc.hd2dress
P = hd2_dress.prep_mod()


def ctx():
    win = bpy.context.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    return win, area, {r.type: r for r in area.regions}


def only(section):
    """Draw only one section of the panel (and the status line) for the next picture."""
    def draw(self, context):
        L = self.layout; L.label(text=hd2_dress.ui(context).status, icon='INFO')
        getattr(self, 'draw_' + section)(context, props, L.box())
    PT.draw = draw


def shot(name):
    win, area, reg = ctx()
    for r in area.regions: r.tag_redraw()
    with bpy.context.temp_override(window=win, area=area, region=reg['WINDOW']):
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=3)
        bpy.ops.screen.screenshot(filepath=os.path.join(OUT, name + '.png'))
    META[name] = {'window': [win.width, win.height], 'ui': [reg['UI'].x, reg['UI'].y, reg['UI'].width, reg['UI'].height]}
    json.dump(META, open(os.path.join(OUT, 'shots.json'), 'w'), indent=1)
    print('GUIDESHOT', name, flush=True)


def shot_area(name, win_index=0):
    """The whole 3D view (viewport + sidebar), or a whole window (win_index) for the preview window."""
    wm = bpy.context.window_manager; win = wm.windows[win_index]
    area = next((a for a in win.screen.areas if a.type == 'VIEW_3D'), None) if win_index == 0 else win.screen.areas[0]
    reg = {r.type: r for r in area.regions}
    for a in win.screen.areas: a.tag_redraw()
    with bpy.context.temp_override(window=win, area=area, region=reg.get('WINDOW')):
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=3)
        bpy.ops.screen.screenshot(filepath=os.path.join(OUT, name + '.png'))
    box = [area.x, area.y, area.width, area.height] if win_index == 0 else [0, 0, win.width, win.height]
    META[name] = {'window': [win.width, win.height], 'area': box}
    json.dump(META, open(os.path.join(OUT, 'shots.json'), 'w'), indent=1)
    print('GUIDESHOT', name, flush=True)


def look_at(objs, rot=(78, 0, 20)):
    import math, mathutils
    win, area, reg = ctx(); r3d = area.spaces[0].region_3d
    pts = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
    c = sum(pts, mathutils.Vector()) / len(pts)
    r3d.view_perspective = 'PERSP'; r3d.view_rotation = mathutils.Euler([math.radians(a) for a in rot]).to_quaternion()
    r3d.view_location = c; r3d.view_distance = 1.5


def edit_select(o, idx):
    if bpy.context.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
    for x in bpy.context.selected_objects: x.select_set(False)
    bpy.context.view_layer.objects.active = o; o.select_set(True)
    for v in o.data.vertices: v.select = v.index in idx
    for e in o.data.edges: e.select = all(o.data.vertices[i].select for i in e.vertices)
    for f in o.data.polygons: f.select = all(o.data.vertices[i].select for i in f.vertices)
    bpy.ops.object.mode_set(mode='EDIT')


def setup():
    win, area, reg = ctx()
    sp = area.spaces[0]; sp.show_region_ui = True; sp.overlay.show_cursor = False; sp.show_gizmo = False
    def walk(c):
        for k in c.__subclasses__(): yield k; yield from walk(k)
    for T in set(walk(bpy.types.Panel)):        # HD2 Dress alone in the sidebar (scripts cannot switch tabs)
        if getattr(T, 'bl_space_type', '') == 'VIEW_3D' and getattr(T, 'bl_region_type', '') == 'UI' and T is not PT:
            try: bpy.utils.unregister_class(T)
            except (RuntimeError, ValueError): pass
    bpy.context.preferences.view.ui_scale = 1.0
    for o in bpy.context.selected_objects: o.select_set(False)
    bpy.context.view_layer.objects.active = None


def steps():
    setup(); yield 1.0
    objs = P.cloth_objects()
    slim = next(o for o in objs if 'Slim' in o.name); stocky = next(o for o in objs if o is not slim)
    skirt = sorted(P.cloth_verts(slim))
    for o in objs:                                           # a fresh scene: no pieces, no pins
        for g in [g for g in o.vertex_groups if P.is_cloth_group(g.name) or g.name == 'pin']: o.vertex_groups.remove(g)
    stocky.hide_set(True)
    for o in bpy.data.objects:                               # the skeletons draw every bone name: hide them
        if o.type == 'ARMATURE': o.hide_set(True)
    props.pieces.clear(); bpy.ops.hd2dress.refresh(); PT.draw = ORIG_DRAW
    hd2_dress.ui().status = 'Mark cloth with a piece (1), then Check (2) and Build (5)'
    look_at([slim]); bpy.context.view_layer.objects.active = slim; slim.select_set(True); yield 0.5
    shot_area('01_start'); yield 0.2
    # 1 New piece: the skirt selected in Edit Mode
    edit_select(slim, set(skirt)); props.new_name = 'skirt'; bpy.ops.hd2dress.piece_new(); yield 0.5
    shot_area('02_new_piece'); yield 0.2
    # pins: the waistband (top row), everything else hidden like an author does with H
    top = max(slim.data.vertices[i].co.z for i in skirt)
    band = {i for i in skirt if slim.data.vertices[i].co.z > top - 0.004}
    edit_select(slim, set(skirt)); bpy.ops.mesh.hide(unselected=True)
    bpy.ops.object.mode_set(mode='OBJECT'); edit_select(slim, band); yield 0.5
    shot_area('03_pin_band'); yield 0.2
    bpy.ops.hd2dress.pin(action='assign'); bpy.ops.mesh.select_all(action='DESELECT'); yield 0.5
    shot_area('04_pinned'); yield 0.2
    bpy.ops.mesh.reveal(select=False); bpy.ops.object.mode_set(mode='OBJECT')
    # the other body
    stocky.hide_set(False); bpy.ops.hd2dress.copy_pieces(); stocky.hide_set(True); yield 0.5
    shot_area('06_copy_body'); yield 0.2
    stocky.hide_set(False)
    for o in bpy.context.selected_objects: o.select_set(False)
    bpy.context.view_layer.objects.active = None
    # 2 Check & fix: a fresh scene has things Fix all can do
    for o in objs:
        while len(o.data.uv_layers) > 1: o.data.uv_layers.remove(o.data.uv_layers[-1])
        if 'root' in o.vertex_groups: o.vertex_groups.remove(o.vertex_groups['root'])
    bpy.ops.hd2dress.check(); only('check'); yield 0.5; shot('05_check'); yield 0.2
    bpy.ops.hd2dress.fix(); only('check'); yield 0.5; shot('07_check_clean'); yield 0.2
    # 3 Physics with Fit to my model
    bpy.ops.hd2dress.fit_body()
    while jobs.running(): yield 0.5
    props.fit_part = 'hips'
    keep_fit = PT.draw_body_fit; PT.draw_body_fit = lambda self, c, p_, b: None
    only('physics'); yield 0.5; shot('08_physics'); yield 0.2
    PT.draw_body_fit = keep_fit; only('body_fit'); yield 0.5; shot('08b_body_fit'); yield 0.2
    # Show colliders: the capsules over the model, hips picked (green)
    PT.draw = ORIG_DRAW; props.show_colliders = True
    while jobs.running(): yield 0.5
    stocky.hide_set(True); look_at([slim], rot=(80, 0, 35)); win, area, reg = ctx(); area.spaces[0].region_3d.view_distance = 2.2
    yield 0.8; shot_area('08c_colliders'); yield 0.2
    props.show_colliders = False; stocky.hide_set(False)
    # 4 Look
    props.look_mode = 'CHARACTER'; props.color_map = COLOUR; props.normal_map = ''; only('look'); yield 0.5; shot('09_look'); yield 0.2
    nwin = len(bpy.context.window_manager.windows)
    bpy.ops.hd2dress.preview()
    while jobs.running(): yield 1.0
    yield 3.0
    if len(bpy.context.window_manager.windows) > nwin: shot_area('10_preview', len(bpy.context.window_manager.windows) - 1); yield 0.2
    # 5 Build
    props.cloth_name = 'my_skirt'; props.mod_name = 'My skirt'; props.armour_patch = PATCH
    props.out_dir = os.path.join(OUT, 'build')
    bpy.ops.hd2dress.build(install=False); only('build'); yield 4.0; shot('11_build')
    while jobs.running(): yield 1.0
    yield 1.0; only('build'); yield 0.5; shot('12_built'); yield 0.2
    PT.draw = ORIG_DRAW
    print('GUIDESHOTS DONE', flush=True)
    bpy.ops.wm.quit_blender()


_it = steps()
def _tick():
    try: return next(_it)
    except StopIteration: return None
    except Exception:
        import traceback; traceback.print_exc(); bpy.ops.wm.quit_blender(); return None
bpy.app.timers.register(_tick, first_interval=2.0)
