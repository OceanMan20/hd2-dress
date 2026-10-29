"""Screenshots for the author guide (docs/GUIDE.md), taken from a real Blender session.
   WAYLAND_DISPLAY= blender EMPTY.blend -P tools/guide_shots.py -- MOD_PATCH_0 OUT_DIR
(X11: Blender cannot read its own window under Wayland.) Each step runs the add-on like a person
would, then saves the whole window plus where the sidebar and the 3D view are (OUT_DIR/shots.json);
tools/guide_crop.py cuts the pictures out."""
import bpy, addon_utils, sys, os, json, math, mathutils
args = sys.argv[sys.argv.index('--') + 1:]
MOD, OUT = os.path.abspath(args[0]), os.path.abspath(args[1])
os.makedirs(OUT, exist_ok=True)
addon_utils.enable('HD2SDK-CommunityEdition'); addon_utils.enable('hd2_dress')
import hd2_dress
from hd2_dress import preview, rigging, helpers
sc = bpy.context.scene; props = sc.hd2dress
bpy.context.preferences.view.ui_scale = 1.0
META = {}
W = {}


def ctx():
    win = bpy.context.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    reg = {r.type: r for r in area.regions}
    return win, area, reg


def view(rot=(80, 0, 150), loc=(0, 0, 0.95), dist=2.6):
    win, area, reg = ctx()
    r3d = area.spaces[0].region_3d
    r3d.view_perspective = 'PERSP'
    r3d.view_rotation = mathutils.Euler([math.radians(a) for a in rot]).to_quaternion()
    r3d.view_location = loc; r3d.view_distance = dist


def shot(name):
    win, area, reg = ctx()
    # Blender's built-in Transform panel sits on the same tab while an object is active: none is,
    # for the picture (the 4b picture needs its bone active and is scrolled past it instead)
    keep = bpy.context.view_layer.objects.active
    sel = [o for o in bpy.context.selected_objects]
    if name != '08_one_bone' and (keep is None or keep.mode == 'OBJECT'):
        for o in sel: o.select_set(False)
        bpy.context.view_layer.objects.active = None
    with bpy.context.temp_override(window=win, area=area, region=reg['WINDOW']):
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=3)
        bpy.ops.screen.screenshot(filepath=os.path.join(OUT, name + '.png'))
    META[name] = {'window': [win.width, win.height],
                  'regions': {t: [r.x, r.y, r.width, r.height] for t, r in reg.items() if t in ('UI', 'WINDOW')}}
    if bpy.context.view_layer.objects.active is None and keep is not None:
        bpy.context.view_layer.objects.active = keep
        for o in sel: o.select_set(True)
    print('GUIDESHOT', name, flush=True)


def scroll_panel(lines):
    win, area, reg = ctx()
    with bpy.context.temp_override(window=win, area=area, region=reg['UI']):
        for _ in range(abs(lines)):
            (bpy.ops.view2d.scroll_down if lines > 0 else bpy.ops.view2d.scroll_up)(deltax=0, deltay=60 if lines > 0 else -60)


def frames(n):
    for i in range(n): sc.frame_set(sc.frame_start + (i % max(1, sc.frame_end - sc.frame_start)))


def tidy():
    # only the dress's own skeleton: HD2SDK loads a second one with the piece that still drew its
    # finger bones in the window
    for o in bpy.data.objects:
        if o.type == 'ARMATURE' and o is not W.get('rig') and o.name != 'hd2dress_avatar':
            o.hide_set(True); o.hide_viewport = True


def step_load():
    win, area, reg = ctx()
    sp = area.spaces[0]
    sp.show_region_ui = True; sp.overlay.show_cursor = False; sp.show_gizmo = False; sp.shading.type = 'SOLID'
    with bpy.context.temp_override(window=win, area=area, region=reg['WINDOW']):
        props.body = 'Stocky'; props.textures = False
        bpy.ops.hd2dress.load('EXEC_DEFAULT', filepath=MOD)
    # the sidebar opens on its first tab; the HD2 Dress panel moves onto it for the pictures
    P = hd2_dress.HD2DRESS_PT_panel
    # the sidebar opens on its first tab and scripts cannot switch tabs: every other (Python) sidebar
    # panel goes away for the pictures, so HD2 Dress is the only tab left (Blender's built-in Transform
    # panel only shows while an object is active; shot() clears that)
    def walk(c):
        for k in c.__subclasses__():
            yield k; yield from walk(k)
    for T in set(walk(bpy.types.Panel)):
        if getattr(T, 'bl_space_type', '') == 'VIEW_3D' and getattr(T, 'bl_region_type', '') == 'UI' and T is not P:
            try: bpy.utils.unregister_class(T)
            except Exception: pass
    tidy(); view(); shot('01_loaded')


def step_bones():
    win, area, reg = ctx()
    d = next(o for o in bpy.data.objects if o.type == 'MESH' and not o.hide_get() and rigging.rig_of(o)
             and any(b.name.startswith('dress_') for b in rigging.rig_of(o).data.bones))
    props.target = d; W['dress'] = d
    with bpy.context.temp_override(window=win, area=area, region=reg['WINDOW']):
        bpy.context.view_layer.objects.active = d
        bpy.ops.hd2dress.use_bones()
    W['rig'] = rigging.rig_of(d)
    tidy()
    for o in []:
        if o.type == 'ARMATURE':
            shown = [b.name for b in o.data.bones if not b.hide]
            print('GUIDEDBG', o.name, 'visible' if o.visible_get() else 'hidden', 'is dress rig' if o is W['rig'] else '',
                  len(shown), 'bones not hidden; e.g.', [n for n in shown if not n.startswith('dress_')][:5],
                  'collections:', [(c.name, c.is_visible) for c in o.data.collections_all][:6], flush=True)
    view(); shot('02_use_my_bones')
    view(rot=(80, 0, 90), dist=2.4); shot('03_strips_side')


def step_edit():
    win, area, reg = ctx()
    with bpy.context.temp_override(window=win, area=area, region=reg['WINDOW']):
        bpy.ops.hd2dress.edit_bones()
    view(rot=(85, 0, 160), loc=(0, 0, 1.0), dist=2.2); shot('04_edit_bones')
    rig = rigging.rig_of(W['dress']); helpers.set_mode(rig, 'OBJECT')


def step_body():
    win, area, reg = ctx()
    with bpy.context.temp_override(window=win, area=area, region=reg['WINDOW']):
        props.anim = 'JOG'; bpy.ops.hd2dress.play()
        frames(20)
    tidy()
    view(rot=(80, 0, 150)); shot('05_preview_show_body')       # the panel while playing
    with bpy.context.temp_override(window=win, area=area, region=reg['WINDOW']):
        bpy.ops.hd2dress.rest(); props.show_body = True
    tidy()
    view(rot=(80, 0, 150)); shot('05b_show_body_rest')
    props.show_body = False


def step_blast():
    win, area, reg = ctx()
    with bpy.context.temp_override(window=win, area=area, region=reg['WINDOW']):
        bpy.ops.hd2dress.rest(); props.anim = 'JOG'
        props.blast_kind = 'HELLBOMB'; props.blast_dir = 'RIGHT'; props.blast_dist = 15
        bpy.ops.hd2dress.blast()
        frames(14)
    tidy()
    view(rot=(80, 0, 150)); shot('06_test_blast')
    with bpy.context.temp_override(window=win, area=area, region=reg['WINDOW']):
        bpy.ops.hd2dress.rest()


def step_tune():
    scroll_panel(12); shot('07_tune'); scroll_panel(-12)


def step_one_bone():
    win, area, reg = ctx()
    rig = rigging.rig_of(W['dress'])
    rig.hide_set(False)
    with bpy.context.temp_override(window=win, area=area, region=reg['WINDOW']):
        for o in bpy.context.selected_objects: o.select_set(False)
        rig.select_set(True); bpy.context.view_layer.objects.active = rig
        helpers.set_mode(rig, 'POSE')
        name = next(b.name for b in rig.data.bones if b.name.endswith('c03_b4'))
        rig.data.bones.active = rig.data.bones[name]
        pb = rig.pose.bones[name]
        with bpy.context.temp_override(active_pose_bone=pb, active_object=rig, object=rig):
            bpy.ops.hd2dress.bone_init()
    scroll_panel(30); shot('08_one_bone'); scroll_panel(-30)
    helpers.set_mode(rig, 'OBJECT')


def step_export():
    win, area, reg = ctx()
    props.mod_name = 'My Dress'; props.out_dir = os.path.join(OUT, 'export') + '/'
    with bpy.context.temp_override(window=win, area=area, region=reg['WINDOW']):
        bpy.ops.hd2dress.export()
    scroll_panel(40); shot('09_export'); scroll_panel(-40)


STEPS = [step_load, step_bones, step_edit, step_body, step_blast, step_tune, step_one_bone, step_export]


def tick():
    if not STEPS:
        json.dump(META, open(os.path.join(OUT, 'shots.json'), 'w'), indent=1)
        print('GUIDESHOT done', flush=True)
        bpy.ops.wm.quit_blender(); return None
    f = STEPS.pop(0)
    try: f()
    except Exception:
        import traceback; traceback.print_exc(); print('GUIDESHOT failed', f.__name__, flush=True)
    return 0.5


bpy.app.timers.register(tick, first_interval=3.0)
