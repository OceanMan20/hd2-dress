"""HD2 Dress: engine cloth for Helldivers 2 armour (needs HD2SDK Community Edition, enabled).

The game's own cloth physics (the system that moves the capes) on your armour: no scripts, players install the
patches like any armour mod. Panel order follows the work: 1 Cloth pieces, 2 Check & fix, 3 Physics, 4 Look, 5 Build.
The slow steps run in a separate Blender in the background (your session and HD2SDK's open patch are untouched)."""
bl_info = {
    'name': 'HD2 Dress',
    'author': 'OceanMan',
    'version': (0, 6, 24),
    'blender': (4, 0, 0),
    'location': '3D View > Sidebar (N) > HD2 Dress',
    'description': 'Engine cloth (the game\'s own cape physics) for Helldivers 2 armour: mark cloth pieces, tune, build patches',
    'category': 'Physics',
}
import bpy, os, sys, re, json, importlib, importlib.util
try: import tomllib
except ModuleNotFoundError:                 # Python 3.10 (Blender 4.0/4.1): the same parser, bundled as tomli
    for _d in (os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tools', '_vendor'),
               os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))), 'tools', '_vendor')):
        if os.path.isdir(_d): sys.path.insert(0, _d); break
    import tomli as tomllib
from bpy.props import (StringProperty, FloatProperty, IntProperty, BoolProperty, EnumProperty, CollectionProperty,
                       IntProperty)
from . import jobs, settings, viewer, colliders_view
importlib.reload(jobs); importlib.reload(settings); importlib.reload(viewer); importlib.reload(colliders_view)      # Blender's Reload Scripts keeps helper modules cached

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))


def tools_dir():
    """The engine tools: bundled in the installed add-on (tools/), or the repo's tools/ when run from a checkout."""
    for d in (os.path.join(ADDON_DIR, 'tools'), os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(ADDON_DIR))), 'tools')):
        if os.path.exists(os.path.join(d, 'hd2dress_cloth.py')): return d
    raise RuntimeError('HD2 Dress tools not found (reinstall the add-on zip)')


_PREP = None
def prep_mod():
    """tools/hd2dress_prep.py as a module (the same checks and fixes as the command line)."""
    global _PREP
    path = os.path.join(tools_dir(), 'hd2dress_prep.py')
    if _PREP is None or _PREP.__file__ != path or _PREP._mtime != os.path.getmtime(path):
        spec = importlib.util.spec_from_file_location('hd2dress_prep', path)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        mod._mtime = os.path.getmtime(path); _PREP = mod
    try: _PREP.LOOK = bpy.context.scene.hd2dress.look_mode      # a back side is fine with the one-sided colour-map look
    except AttributeError: pass
    return _PREP
settings.prep_mod = prep_mod


SDK_TESTED = (3, 11, 0)


def sdk_version():
    import addon_utils
    for mod in addon_utils.modules():
        if mod.__name__ == 'HD2SDK-CommunityEdition':
            return tuple(mod.bl_info.get('version', ())) if addon_utils.check(mod.__name__)[1] else None
    return None


def game_dir(props):
    sys.path.insert(0, tools_dir())
    import hd2_paths; importlib.reload(hd2_paths)
    if props.game_path:
        d = bpy.path.abspath(props.game_path)
        return d if hd2_paths.is_game_data(d) else None
    m = sys.modules.get('HD2SDK-CommunityEdition')
    if m is not None and hd2_paths.is_game_data(getattr(m, 'Global_gamepath', '')): return m.Global_gamepath
    try: return hd2_paths.game_data()
    except SystemExit: return None


def job_env(props):
    g = game_dir(props)
    return {'HD2_DATA': g} if g else {}


def ui(context=None):
    """Panel bookkeeping (status, background job, last build): on the window manager, so Ctrl+Z never rolls it back."""
    return (context or bpy.context).window_manager.hd2dress_ui


def status(context, text):
    ui(context).status = text
    print('HD2 Dress:', text)


def cache_dir(*sub):
    d = os.path.join(os.path.expanduser('~'), '.cache', 'hd2-dress', 'panel', *sub); os.makedirs(d, exist_ok=True)
    return d


def cloth_objects(): return prep_mod().cloth_objects()


def all_piece_names():
    names = []
    for o in cloth_objects():
        for g in prep_mod().cloth_groups(o):
            if g.name not in names: names.append(g.name)
    return names


def piece(props, name):
    return next((p for p in props.pieces if p.name == name), None)


def ensure_pieces(props):
    """A settings entry for every cloth group in the scene (new groups start from the tested defaults)."""
    added = 0
    for n in all_piece_names():
        if piece(props, n) is None:
            p = props.pieces.add(); p.name = n
            p.follow_legs = any(w in n.lower() for w in ('skirt', 'dress', 'robe', 'kilt', 'gown'))
            added += 1
    return added


def refresh_counts(props):
    P = prep_mod()
    for p in props.pieces:
        parts = []
        for o in cloth_objects():
            if p.name in o.vertex_groups:
                if o.mode == 'EDIT': o.update_from_editmode()
                parts.append(f'{P.label(o)} {len(P.group_verts(o, p.name))}')
        p.counts = ', '.join(parts) if parts else 'no vertex group'
    pins = []
    for o in cloth_objects():
        if o.mode == 'EDIT': o.update_from_editmode()
        pins.append(f'{P.label(o)} {len(P.group_verts(o, settings.PIN_GROUP) & P.cloth_verts(o))}')
    ui().pin_counts = ', '.join(pins)


def default_out(props):
    base = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.path.join(os.path.expanduser('~'), 'HD2Dress')
    return os.path.join(base, 'hd2dress_build', props.cloth_name or 'my_cloth')


def settings_path(props):
    if props.settings_file: return bpy.path.abspath(props.settings_file)
    if bpy.data.filepath: return os.path.splitext(bpy.data.filepath)[0] + '_cloth.toml'
    return None


class object_mode:
    """Run a block in Object Mode (mesh UVs and loops are not readable in Edit Mode), then return to the mode the
    author was in, with the same active object."""
    def __enter__(self):
        self.obj = bpy.context.view_layer.objects.active
        self.mode = self.obj.mode if self.obj is not None else 'OBJECT'
        if self.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
        return self

    def __exit__(self, *a):
        if self.mode != 'OBJECT' and self.obj is not None and self.obj.name in bpy.context.view_layer.objects:
            bpy.context.view_layer.objects.active = self.obj
            try: bpy.ops.object.mode_set(mode=self.mode)
            except RuntimeError: pass
        return False


def flush_edit():
    for o in bpy.data.objects:
        if o.type == 'MESH' and o.mode == 'EDIT': o.update_from_editmode()


# ======================================================================== properties
class HD2DressPiece(bpy.types.PropertyGroup):
    # name = the vertex group (cloth or cloth_<piece>)
    follow_legs: BoolProperty(name='Follow legs (skirt)', default=False,
                              description='Skirts and dresses: the lower part follows the thigh on its side, so a raised knee lifts the fabric '
                                          'instead of pushing through it. Off for capes, hair, sleeves, ribbons')
    mass: FloatProperty(name='Mass', default=0.004, min=0.0005, max=0.05, soft_min=0.001, soft_max=0.02,  step=0.01, precision=4,
                        description='Per cloth point (kg). Sets how strongly wind (the ship fan) pushes the cloth: lighter flutters more. Falling speed does not depend on it: use Gravity for that')
    stiffness: FloatProperty(name='Link stiffness', default=1.0, min=0.1, max=1.0,
                             description='Neighbour links. Keep 1.0: softer links opened gaps a knee slipped through (0.7) and went unstable (0.3)')
    leash: FloatProperty(name='Leash', default=1.0, min=0.0, max=2.0, soft_max=1.5,  unit='LENGTH',
                         description='How far a point may move from where it normally hangs (m). Tight leashes drag cloth back through '
                                     'bent legs (0.40-0.45 clipped in a kneel); 0.55+ holds')
    stretch: FloatProperty(name='Stretch', default=0.6, min=0.0, max=2.0, soft_max=1.0, 
                           description='How much longer than at rest a point may get from its pin row (0.6 = 1.6x)')
    bend: FloatProperty(name='Bend stiffness', default=0.24, min=0.0, max=1.0,
                        description='Resistance to folding. 0.8 = the stock cape (a skirt stood out like a cone); 0.24 drapes')
    counts: StringProperty(default='')
    expanded: BoolProperty(default=True)


LOOK_ITEMS = [('CHARACTER', 'Colour map (character shader)', 'A normal colour texture (+ normal map), matte. The build makes the material'),
              ('KEEP', 'Keep my material', 'Your own finished HD2 armour material (in your armour patch), exactly as it is: '
                                           'textures and values untouched, only the cloth switch is turned on'),
              ('OWN', 'My own cloth material', 'The cloth faces already use a cloth-capable material (cape shader). Advanced')]


class HD2DressUI(bpy.types.PropertyGroup):
    status: StringProperty(default='Mark cloth with a piece (1), then Check (2) and Build (5)')
    job_kind: StringProperty(default='')
    job_lines: StringProperty(default='')
    job_elapsed: FloatProperty(default=0.0)
    problems: StringProperty(default='')
    pin_counts: StringProperty(default='')
    last_out: StringProperty(default='')
    preview_playing: BoolProperty(default=False)
    preview_ms: FloatProperty(default=0.0)
    fit_summary: StringProperty(default='')


class HD2DressProps(bpy.types.PropertyGroup):
    game_path: StringProperty(name='Game data folder', 
                              description='…/steamapps/common/Helldivers 2/data (found automatically when empty)')
    pieces: CollectionProperty(type=HD2DressPiece)
    piece_index: IntProperty(default=0)
    new_name: StringProperty(name='Name', default='skirt', description='Piece name: the vertex group becomes cloth_<name>')
    # physics (whole outfit)
    gravity: FloatProperty(name='Gravity', default=14.0, min=0.0, max=40.0, soft_min=5.0, soft_max=25.0, 
                           description='This cloth only (m/s²). Stronger reads heavier: falls faster, less floaty. 9.81 = normal')
    wind: FloatProperty(name='Wind', default=1.0, min=0.0, max=4.0, soft_max=3.0,
                        description='How strongly the game\'s wind (the Super Destroyer breeze) blows this cloth. 0 = off, 1 = like the '
                                    'stock cape, 2 = double (strips whip around). Planets without wind: no effect')
    damping: FloatProperty(name='Damping', default=0.7, min=0.0, max=5.0, soft_max=2.0,  description='Air drag on the whole cloth (per second)')
    iterations: IntProperty(name='Iterations', default=4, min=1, max=8,
                            description='Solver passes per frame. 4 holds a raised knee; more = stiffer and slower')
    link_passes: IntProperty(name='Link passes', default=3, min=0, max=6, description='Extra neighbour-link passes per iteration')
    radius: FloatProperty(name='Point radius', default=0.025, min=0.005, max=0.06, soft_min=0.01, soft_max=0.04,  unit='LENGTH', precision=3,
                          description='Collision ball around each cloth point. 0.025 tested best (0.02 left a hole at the knee, 0.03 floats off the legs)')
    friction: FloatProperty(name='Friction', default=0.3, min=0.0, max=1.0,
                            description='Against the body. 0.3 lets a knee slide under the cloth; 0.8 carried a skirt up the leg in a kneel')
    floor_gap: FloatProperty(name='Floor gap', default=0.015, min=0.0, max=0.1, soft_max=0.05,  unit='LENGTH', precision=3,
                             description='Gap the cloth keeps off the floor and level geometry (the cape uses 0.07)')
    follow_thigh: FloatProperty(name='Thigh follow', default=0.6, min=0.0, max=1.0,
                                description='Pieces with Follow legs: how much of the hem follows the thigh (0 = off)')
    follow_front: BoolProperty(name='Front follows its own side', default=True,
                               description='The front half follows the thigh on its side (fixed bunching in the thumbs-up emote)')
    planes_on: BoolProperty(name='Leg walls (bone planes)', default=True,
                            description='What the stock cape uses against clipping: loose points near a leg get an invisible wall on the leg')
    planes_reach: FloatProperty(name='Reach', default=0.15, min=0.0, max=0.5, soft_max=0.3,  unit='LENGTH', description='Points this close to a leg get a wall')
    planes_margin: FloatProperty(name='Margin', default=0.0, min=0.0, max=0.05, unit='LENGTH', precision=3, description='Wall distance off the leg')
    kneecaps: BoolProperty(name='Kneecaps', default=True, description='An extra short capsule on each knee so collision matches a kneepad',
                           update=lambda s_, c: colliders_view.redraw())
    kneecap_grow: FloatProperty(name='Kneecap size', default=0.03, min=0.0, max=0.08, soft_max=0.05,  unit='LENGTH', precision=3,
                                description='How much thicker than the shin', update=lambda s_, c: colliders_view.redraw())
    fit_part: EnumProperty(name='Body part', items=[(k, n, '') for k, n, _ in settings.BODY_PARTS], default='hips',
                           update=lambda s_, c: colliders_view.redraw())
    show_colliders: BoolProperty(name='Show colliders', default=False, update=lambda s_, c: _show_colliders_changed(s_, c),
                                 description='Draw the invisible body colliders over your model (what the cloth collides with, '
                                             'with your Body fit values). Green = the body part picked below. Live while you move the sliders')
    fit_share: FloatProperty(name='Cover', default=0.85, min=0.5, max=1.0, subtype='FACTOR',
                             description='Fit to my model: how much of the body the colliders reach around (0.85 = all but the '
                                         'outermost 15%). Higher = fewer spots where the body pokes through, but the cloth stands off more')
    fit_margin: FloatProperty(name='Extra gap', default=0.0, min=-0.05, max=0.05, unit='LENGTH', precision=3,
                              description='Fit to my model: added to every fitted collider (positive = the cloth sits further off the body)')
    show_advanced: BoolProperty(name='Advanced', default=False)
    motion_min: FloatProperty(name='Carry from speed', default=0.5, min=0.0, max=10.0, soft_max=4.0, 
                              description='Fast moves carry the cloth with the hips from this speed (m/s; the cape uses 8)')
    motion_max: FloatProperty(name='Full carry at', default=2.0, min=0.1, max=20.0, soft_max=8.0,  description='Fully carried at this speed (m/s)')
    # look
    look_mode: EnumProperty(name='Look', items=LOOK_ITEMS, default='CHARACTER')
    color_map: StringProperty(name='Colour map', description='PNG/JPG on the cloth UVs, up to 2048')
    normal_map: StringProperty(name='Normal map', description='Optional, OpenGL/Blender style')
    normal_flip_green: BoolProperty(name='DirectX normal map (flip green)', default=False)
    ao_map: StringProperty(name='AO map', description='Optional ambient occlusion')
    roughness_map: StringProperty(name='Roughness map', description='Optional per-pixel roughness (white = matte); overrides the Roughness value')
    material_id: StringProperty(name='Cloth material ID', default='',
                                description='Optional. The material id (a number) the cloth faces use in the exported unit. Empty = read from the mesh')
    roughness: FloatProperty(name='Roughness', default=0.7, min=0.0, max=1.0, description='0 glossy, 1 matte (used with the normal map)')
    weave_on: BoolProperty(name='Fine weave detail', default=False,
                           description='Optional tiled detail normal. Keep it subtle: folded cloth can go dark (the base lighting does not follow folds)')
    weave_map: StringProperty(name='Weave normal map')
    weave_tiling: FloatProperty(name='Tiling', default=40.0, min=1.0, max=400.0, soft_max=120.0)
    weave_strength: FloatProperty(name='Strength', default=0.2, min=0.0, max=1.0)
    weave_aspect: FloatProperty(name='Aspect', default=1.0, min=0.25, max=8.0, description='Repeat across vs down (a skirt UV: ~2)')
    # build
    cloth_name: StringProperty(name='Cloth name', default='my_cloth', description='Unique per mod: the cloth\'s name in the game')
    mod_name: StringProperty(name='Mod name', default='')
    armour_patch: StringProperty(name='Armour patch', 
                                 description='The patch you exported with HD2SDK (…patch_0) from this scene, AFTER Check & fix')
    out_dir: StringProperty(name='Output folder', description='Where the patches go. Empty = hd2dress_build/<cloth name> next to the .blend')
    archives: StringProperty(name='Only archives', default='',
                             description='Optional, comma separated. Empty = every armour item that shares the unit (all of them need the cloth)')
    settings_file: StringProperty(name='Settings file', description='The saved record of this cloth (TOML). Empty = <your blend>_cloth.toml next to the .blend')
    preview_size: IntProperty(name='Size', default=600, min=200, max=2000)
    # motion preview
    preview_anim: EnumProperty(name='Move', items=[(k, n, '') for k, n, _ in viewer.ANIMS], default='JOG',
                               update=lambda self, c: viewer.use_anim(c.scene, self.preview_anim) if viewer.avatar() else None)
    preview_speed: FloatProperty(name='Speed', default=1.0, min=0.0, max=2.0,
                                 description='Forward speed of the walking moves (1 = the game\'s speed). The body stays in view, the cloth feels the speed')
    preview_breeze: BoolProperty(name='Ship breeze', default=False,
                                 description='Blow the Super Destroyer breeze (about 8 m/s, gusty) scaled by Wind. Planets: off')
    preview_wind_dir: FloatProperty(name='Breeze from', default=180.0, min=0.0, max=360.0, subtype='ANGLE' if False else 'NONE',
                                    description='Direction the breeze comes from, degrees (0 = from the front, 180 = from behind)')
    preview_colliders: BoolProperty(name='Show colliders', default=False,
                                    description='Draw the game cloth\'s body capsules (the shapes the cloth collides with)')


def _add_fit_props():
    for k, n, bones in settings.BODY_PARTS:
        paired = len(bones) == 2 or k == 'chest'
        HD2DressProps.__annotations__[f'fit_{k}_thick'] = FloatProperty(update=lambda s_, c: colliders_view.redraw(),
            name='Thickness', default=0.0, min=-0.25, max=0.3, soft_min=-0.15, soft_max=0.15, unit='LENGTH', precision=3,
            description=(f'{n}: make the collider this much thicker (or thinner, negative) than the standard Helldiver' if k != 'chest' else
                         'Chest: adds two colliders in front of the chest (7 cm + this) for models with a larger chest. 0 and all '
                         'other chest sliders untouched = no extra chest colliders'))
        HD2DressProps.__annotations__[f'fit_{k}_len'] = FloatProperty(update=lambda s_, c: colliders_view.redraw(),
            name='Length', default=1.0, min=0.3, max=3.0, soft_min=0.6, soft_max=1.6,
            description=f'{n}: collider length, 1 = standard (for longer or shorter limbs)')
        HD2DressProps.__annotations__[f'fit_{k}_fwd'] = FloatProperty(update=lambda s_, c: colliders_view.redraw(),
            name='Forward / back', default=0.0, min=-0.3, max=0.3, soft_min=-0.12, soft_max=0.12, unit='LENGTH', precision=3,
            description=f'{n}: move the collider forward (+) or back (-), e.g. back for a model whose buttocks stick out')
        HD2DressProps.__annotations__[f'fit_{k}_up'] = FloatProperty(update=lambda s_, c: colliders_view.redraw(),
            name='Up / down', default=0.0, min=-0.3, max=0.3, soft_min=-0.12, soft_max=0.12, unit='LENGTH', precision=3,
            description=f'{n}: move the collider up (+) or down (-)')
        HD2DressProps.__annotations__[f'fit_{k}_side'] = FloatProperty(update=lambda s_, c: colliders_view.redraw(),
            name='Outward' if paired else 'Right / left', default=0.0, min=-0.3, max=0.3, soft_min=-0.1, soft_max=0.1, unit='LENGTH',
            precision=3, description=f'{n}: move ' + ('both colliders outward (+) or inward (-), mirrored' if paired else 'the collider right (+) or left (-)'))


_add_fit_props()


# ======================================================================== operators: pieces and pins
def active_mesh(context):
    o = context.active_object
    return o if o is not None and o.type == 'MESH' else None


class HD2DRESS_OT_piece_new(bpy.types.Operator):
    """Make a new cloth piece from the selected vertices (Edit Mode). Each piece gets its own settings"""
    bl_idname = 'hd2dress.piece_new'; bl_label = 'New piece from selection'; bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context): return active_mesh(context) is not None and context.mode == 'EDIT_MESH'

    def execute(self, context):
        props = context.scene.hd2dress; o = active_mesh(context)
        name = re.sub(r'[^a-z0-9_]+', '_', props.new_name.strip().lower()).strip('_') or 'piece'
        group = 'cloth_' + name
        o.update_from_editmode()
        if not any(v.select for v in o.data.vertices): self.report({'ERROR'}, 'select the cloth vertices first'); return {'CANCELLED'}
        vg = o.vertex_groups.get(group) or o.vertex_groups.new(name=group)
        o.vertex_groups.active_index = vg.index
        bpy.ops.object.vertex_group_assign()
        ensure_pieces(props); refresh_counts(props)
        props.piece_index = next(i for i, p in enumerate(props.pieces) if p.name == group)
        status(context, f'piece {group}: {piece(props, group).counts} vertices on {o.name}')
        return {'FINISHED'}


def _group_op(context, name, op):
    o = active_mesh(context)
    if o is None or context.mode != 'EDIT_MESH': return 'switch to Edit Mode on the armour mesh'
    vg = o.vertex_groups.get(name)
    if vg is None:
        if op != 'assign': return f'{o.name} has no group {name}'
        vg = o.vertex_groups.new(name=name)
    o.vertex_groups.active_index = vg.index
    {'assign': bpy.ops.object.vertex_group_assign, 'remove': bpy.ops.object.vertex_group_remove_from,
     'select': bpy.ops.object.vertex_group_select, 'deselect': bpy.ops.object.vertex_group_deselect}[op]()
    return None


class HD2DRESS_OT_piece_edit(bpy.types.Operator):
    """Add the selected vertices to this piece, remove them, or select the piece's vertices (Edit Mode)"""
    bl_idname = 'hd2dress.piece_edit'; bl_label = 'Piece'; bl_options = {'REGISTER', 'UNDO'}
    piece: StringProperty()
    action: EnumProperty(items=[('assign', 'Add selection', ''), ('remove', 'Remove selection', ''), ('select', 'Select', ''),
                                ('deselect', 'Deselect', '')])

    @classmethod
    def description(cls, context, p):
        return {'assign': 'Add the selected vertices to this piece', 'remove': 'Take the selected vertices out of this piece',
                'select': 'Select this piece\'s vertices', 'deselect': 'Deselect this piece\'s vertices'}[p.action]

    def execute(self, context):
        props = context.scene.hd2dress
        err = _group_op(context, self.piece, self.action)
        if err: self.report({'ERROR'}, err); return {'CANCELLED'}
        refresh_counts(props)
        p = piece(props, self.piece)
        status(context, f'{self.piece}: {p.counts if p else "?"} vertices')
        return {'FINISHED'}


class HD2DRESS_OT_piece_delete(bpy.types.Operator):
    """Delete this piece: removes its vertex group from every mesh (the mesh itself is not changed)"""
    bl_idname = 'hd2dress.piece_delete'; bl_label = 'Delete piece'; bl_options = {'REGISTER', 'UNDO'}
    piece: StringProperty()

    def invoke(self, context, event):
        short = self.piece[6:] if self.piece.startswith('cloth_') else self.piece
        try:
            return context.window_manager.invoke_confirm(self, event, title=f'Delete piece "{short}"?', confirm_text='Delete',
                                                         message='Removes its vertex group from every mesh (the mesh itself is '
                                                                 'not changed). Ctrl+Z brings it back.', icon='WARNING')
        except TypeError:                      # Blender before 4.1: no title/message
            return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        props = context.scene.hd2dress
        for o in bpy.data.objects:
            if o.type == 'MESH' and self.piece in o.vertex_groups: o.vertex_groups.remove(o.vertex_groups[self.piece])
        i = next((i for i, p in enumerate(props.pieces) if p.name == self.piece), None)
        if i is not None: props.pieces.remove(i)
        props.piece_index = min(props.piece_index, max(0, len(props.pieces) - 1))
        status(context, f'deleted piece {self.piece}')
        return {'FINISHED'}


class HD2DRESS_OT_pin(bpy.types.Operator):
    """Pins: cloth vertices held to the body (where the cloth hangs from). A piece without pins hangs from its top row"""
    bl_idname = 'hd2dress.pin'; bl_label = 'Pins'; bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(items=[('assign', 'Pin selection', ''), ('remove', 'Unpin selection', ''), ('select', 'Select pins', '')])

    @classmethod
    def description(cls, context, p):
        return {'assign': 'Pin the selected vertices (they stay on the body)', 'remove': 'Unpin the selected vertices',
                'select': 'Select the pinned vertices'}[p.action]

    def execute(self, context):
        err = _group_op(context, settings.PIN_GROUP, self.action)
        if err: self.report({'ERROR'}, err); return {'CANCELLED'}
        refresh_counts(context.scene.hd2dress)
        status(context, f'pins: {ui(context).pin_counts}')
        return {'FINISHED'}


class HD2DRESS_OT_copy_pieces(bpy.types.Operator):
    """Copy every cloth piece and the pins from the selected body's mesh to the other body types of this armour piece
    (slim <-> stocky), vertex by vertex by position. Check the result: very different shapes may need touch-ups"""
    bl_idname = 'hd2dress.copy_pieces'; bl_label = 'Copy pieces to the other body'; bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        o = active_mesh(context)
        return o is not None and bool(prep_mod().cloth_groups(o))

    def execute(self, context):
        P = prep_mod(); props = context.scene.hd2dress
        with object_mode():
            src = active_mesh(context) or bpy.context.view_layer.objects.active
            others = [o for o in bpy.data.objects if o.type == 'MESH' and o is not src and 'Z_ObjectID' in o
                      and not P.is_lower_lod(o) and P.same_piece_other_body(o, src)]
            others = list(dict.fromkeys(others))
            if not others: self.report({'ERROR'}, 'no other body type of this armour piece in the scene'); return {'CANCELLED'}
            msgs = []
            for o in others: P.copy_pieces(src, o, msgs.append)
        ensure_pieces(props); refresh_counts(props)
        for m in msgs: print('HD2 Dress copy:', m)
        got = ', '.join(f'{short(m.split(": ")[1].split(" ")[0])} {m.split(" ")[2]}' for m in msgs)
        status(context, f'Copied from {P.label(src)} to {", ".join(P.label(o) for o in others)}: {got} vertices. Check it.')
        return {'FINISHED'}


class HD2DRESS_OT_refresh(bpy.types.Operator):
    """Find cloth pieces (vertex groups "cloth" / "cloth_<name>") and count their vertices"""
    bl_idname = 'hd2dress.refresh'; bl_label = 'Refresh'

    def execute(self, context):
        props = context.scene.hd2dress
        n = ensure_pieces(props)
        gone = [p.name for p in props.pieces if p.name not in all_piece_names()]
        refresh_counts(props)
        status(context, f'{len(props.pieces)} piece(s)' + (f', {n} new' if n else '') + (f'; no vertex group left for {", ".join(gone)}' if gone else ''))
        return {'FINISHED'}


# ======================================================================== operators: check and fix
class HD2DRESS_OT_check(bpy.types.Operator):
    """Check the cloth meshes: bones, UV sets, root weight, face direction, double layers, LOD materials, pins"""
    bl_idname = 'hd2dress.check'; bl_label = 'Check'

    def execute(self, context):
        props = context.scene.hd2dress
        with object_mode():
            ensure_pieces(props); refresh_counts(props)
            res = prep_mod().check_all()
        ui().problems = '\n'.join(f'{lv}\t{t}' for lv, t in res)
        bad = sum(1 for lv, _ in res if lv == 'PROBLEM'); fix = sum(1 for lv, _ in res if lv == 'FIX')
        status(context, 'Check: ' + ('all good' if not bad and not fix else f'{bad} problem(s) to fix by hand, {fix} Fix all can do'))
        return {'FINISHED'}


def _do_fix(context, rest):
    props = context.scene.hd2dress
    msgs = []
    with object_mode():
        n = prep_mod().fix_all(cloth_objects(), rest, msgs.append)
        res = prep_mod().check_all()
    for m in msgs: print('HD2 Dress fix:', m)
    ui().problems = '\n'.join(f'{lv}\t{t}' for lv, t in res)
    status(context, f'Fix all: {n} fix(es) applied' + ('; export the armour patch with HD2SDK again before building' if n else ''))


class HD2DRESS_OT_back_side(bpy.types.Operator):
    """Give the cloth a back side: a reversed copy of every cloth face (same pieces, pins, UVs and material). The colour
    map look draws faces from the front only, so without it the inside of the cloth is invisible (a half skirt seen
    from the front, a cape from behind). Undo-able. Export the armour patch with HD2SDK again afterwards"""
    bl_idname = 'hd2dress.back_side'; bl_label = 'Add back side'; bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        P = prep_mod(); objs = cloth_objects()
        if not objs: self.report({'ERROR'}, 'no cloth pieces yet'); return {'CANCELLED'}
        msgs = []
        with object_mode():
            n = sum(P.add_back_side(o, msgs.append) for o in objs)
        for m in msgs: print('HD2 Dress:', m)
        status(context, f'Back side added on {n} object(s); export the armour patch with HD2SDK again' if n else 'The cloth already has a back side')
        return {'FINISHED'}


def _apply_fit(context):
    props = context.scene.hd2dress; P = prep_mod()
    objs = cloth_objects(); cols = P.load_colliders()
    if not objs: status(context, 'Fit to my model: no cloth pieces yet'); return
    results = []
    with object_mode():
        for o in objs:
            try: results.append(P.fit_body(o, cols, props.fit_share, props.fit_margin))
            except RuntimeError as e: print('HD2 Dress fit:', e)
    parts = sorted({k for r in results for k in r})
    if not parts: status(context, 'Fit to my model: found no body around the colliders (are the body meshes in the scene?)'); return
    lines = []
    for k in parts:
        vals = [r[k] for r in results if k in r]
        for f in ('thick', 'fwd', 'up', 'side'):
            setattr(props, f'fit_{k}_{f}', round(sum(v[f] for v in vals) / len(vals), 3))
        b, a = vals[0]['before'], vals[0]['after']
        name = next(n for kk, n, _ in settings.BODY_PARTS if kk == k)
        lines.append(f'{name}: {getattr(props, f"fit_{k}_thick") * 100:+.1f} cm thick; body through the cloth {b[0]:.0%} -> {a[0]:.0%}')
    ui(context).fit_summary = '\n'.join(lines)
    print('HD2 Dress fit:\n  ' + '\n  '.join(lines))
    status(context, f'Fitted {len(parts)} body parts to your model (values below are editable)')


def ensure_colliders(context, then):
    """The stock body colliders, read once from the game in a separate Blender (~20 s); then(context) when ready."""
    P = prep_mod()
    if P.load_colliders() is not None: then(context); return
    props = context.scene.hd2dress; ui().job_kind = 'Reading the body colliders from the game (one time)'
    def done(rc, lines):
        if jobs.current().cancelled: status(bpy.context, 'cancelled'); return
        if rc or P.load_colliders() is None:
            status(bpy.context, 'could not read the colliders: ' + ' | '.join(jobs.interesting(lines)[-3:])); return
        then(bpy.context)
    jobs.start('colliders', jobs.blender_cmd(os.path.join(tools_dir(), 'hd2dress_cloth.py'), ['colliders', P.colliders_cache_path()]),
               done, job_env(props), os.path.join(cache_dir(), 'colliders.log'))
    status(context, 'Reading the body colliders from the game (one time, ~20 s)...')


def _show_colliders_changed(self, context):
    if self.show_colliders:
        ensure_colliders(context, lambda c: (colliders_view.redraw(), status(c, 'Colliders shown: green = the body part picked below')))
    colliders_view.redraw()


class HD2DRESS_OT_fit_body(bpy.types.Operator):
    """Fit the invisible body colliders to your model: measures your body meshes around each collider and fills in the
    Body fit values (thickness and position per part). Check them and tweak by hand if needed. Undo-able"""
    bl_idname = 'hd2dress.fit_body'; bl_label = 'Fit to my model'; bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ensure_colliders(context, lambda c: (_apply_fit(c), colliders_view.redraw()))
        return {'FINISHED'}


class HD2DRESS_OT_fix(bpy.types.Operator):
    """Apply every automatic fix: add the collision bones the cloth needs (exact game rest pose), 3 UV sets, root in the
    bone palette, cloth faces outward. Undo-able. Re-export the armour patch with HD2SDK afterwards"""
    bl_idname = 'hd2dress.fix'; bl_label = 'Fix all'; bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        P = prep_mod(); objs = cloth_objects()
        if not objs: self.report({'ERROR'}, 'no cloth pieces yet'); return {'CANCELLED'}
        need_rest = any(P.rig_of(o) is not None and P.missing_bones(P.rig_of(o)) for o in objs)
        rest = P.load_rest()
        if need_rest and rest is None:          # read once from the game, in a separate Blender (~20 s)
            props = context.scene.hd2dress; ui().job_kind = 'Reading the diver skeleton from the game (one time)'
            def done(rc, lines):
                r = P.load_rest()
                if jobs.current().cancelled: status(bpy.context, 'cancelled'); return
                if rc or r is None: status(bpy.context, 'could not read the diver skeleton: ' + ' | '.join(jobs.interesting(lines)[-3:])); return
                _do_fix(bpy.context, r)
            jobs.start('skeleton', jobs.blender_cmd(os.path.join(tools_dir(), 'hd2dress_prep.py'), ['--dump-rest', P.rest_cache_path()]),
                       done, job_env(props), os.path.join(cache_dir(), 'skeleton.log'))
            status(context, 'Reading the diver skeleton from the game (one time, ~20 s)...')
            return {'FINISHED'}
        _do_fix(context, rest)
        return {'FINISHED'}


# ======================================================================== operators: settings, build, preview
def _units_ok(objs):
    bad = [o.name for o in objs if settings.unit_hex(o) is None]
    return f'not HD2SDK unit objects (no Z_ObjectID): {", ".join(bad)}' if bad else None


def write_settings(props, path, blend, objs):
    base = os.path.dirname(path)
    keep = props.out_dir
    if not props.out_dir: props.out_dir = default_out(props)       # always record where the build goes
    try: st = settings.to_settings(props, objs, base, blend)
    finally: props.out_dir = keep
    hdr = ('# HD2 Dress engine cloth settings, written by the Blender panel. Build from the command line too:\n'
           '#   blender -b -P tools/hd2dress_cloth.py -- build THIS_FILE.toml [--install]\n'
           '# Every key: examples/engine_cloth_testrig.toml. Paths are relative to this file.')
    open(path, 'w', encoding='utf-8').write(settings.dumps(st, hdr))
    return st


class HD2DRESS_OT_save_settings(bpy.types.Operator):
    """Write the panel's values to the settings file (TOML, next to your .blend): the saved record of this cloth"""
    bl_idname = 'hd2dress.save_settings'; bl_label = 'Save settings'

    def execute(self, context):
        props = context.scene.hd2dress; path = settings_path(props)
        if not path: self.report({'ERROR'}, 'save the .blend first (or choose a settings file)'); return {'CANCELLED'}
        ensure_pieces(props); write_settings(props, path, bpy.data.filepath, cloth_objects())
        if bpy.data.is_dirty:
            self.report({'WARNING'}, 'Saved the settings. Your .blend has unsaved changes: save it too (Ctrl+S), the '
                                     'settings file reads the cloth pieces from the saved .blend')
            status(context, f'saved {os.path.basename(path)}; now save the .blend too (Ctrl+S)')
        else:
            status(context, f'saved {path}')
        return {'FINISHED'}


class HD2DRESS_OT_load_settings(bpy.types.Operator):
    """Load a settings file (TOML) into the panel"""
    bl_idname = 'hd2dress.load_settings'; bl_label = 'Load settings'
    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default='*.toml', options={'HIDDEN'})

    def invoke(self, context, event):
        self.filepath = settings_path(context.scene.hd2dress) or ''
        context.window_manager.fileselect_add(self); return {'RUNNING_MODAL'}

    def execute(self, context):
        props = context.scene.hd2dress
        try: st = tomllib.load(open(self.filepath, 'rb'))
        except Exception as e: self.report({'ERROR'}, f'cannot read {self.filepath}: {e}'); return {'CANCELLED'}
        ensure_pieces(props)
        settings.from_settings(props, st, os.path.dirname(self.filepath), cloth_objects())
        props.settings_file = self.filepath; refresh_counts(props)
        status(context, f'loaded {self.filepath}'); return {'FINISHED'}


class HD2DRESS_OT_use_sdk_patch(bpy.types.Operator):
    """Use the patch HD2SDK has open (the one you export your armour into)"""
    bl_idname = 'hd2dress.use_sdk_patch'; bl_label = 'Use HD2SDK\'s patch'

    def execute(self, context):
        m = sys.modules.get('HD2SDK-CommunityEdition')
        p = getattr(getattr(getattr(m, 'Global_TocManager', None), 'ActivePatch', None), 'Path', '') if m else ''
        if not p: self.report({'ERROR'}, 'HD2SDK has no patch open'); return {'CANCELLED'}
        context.scene.hd2dress.armour_patch = p; status(context, f'armour patch: {p}'); return {'FINISHED'}


def _prepare_job(context, self):
    """Validate, save a copy of the scene and a job settings file. Returns (job dir, toml path, blend copy, objs) or None."""
    props = context.scene.hd2dress
    if jobs.running(): self.report({'ERROR'}, 'a job is running: wait or Cancel'); return None
    flush_edit(); ensure_pieces(props)
    objs = cloth_objects()
    if not objs: self.report({'ERROR'}, 'no cloth pieces yet (1 Cloth pieces)'); return None
    err = _units_ok(objs)
    if err: self.report({'ERROR'}, err); return None
    if not game_dir(props): self.report({'ERROR'}, 'Helldivers 2 data folder not found: set it at the top of the panel'); return None
    name = re.sub(r'[^A-Za-z0-9_]+', '_', props.cloth_name).strip('_') or 'my_cloth'
    jd = cache_dir(name)
    blend = os.path.join(jd, 'scene.blend')
    with object_mode():         # saved from Edit Mode the copy can lose UV data (seen after Fix all added UV sets)
        bpy.ops.wm.save_as_mainfile(filepath=blend, copy=True, check_existing=False)
    toml = os.path.join(jd, 'job.toml')
    return jd, toml, blend, objs


class HD2DRESS_OT_build(bpy.types.Operator):
    """Build the cloth patches (one per game archive that holds your armour unit, + the material). Runs in the background"""
    bl_idname = 'hd2dress.build'; bl_label = 'Build'
    install: BoolProperty(default=False)

    @classmethod
    def description(cls, context, p):
        return ('Build, then copy the patches into the game folder (refuses to overwrite another mod\'s patch_0)' if p.install
                else 'Build the cloth patches into the output folder. Runs in the background')

    def execute(self, context):
        props = context.scene.hd2dress
        if not props.cloth_name.strip(): self.report({'ERROR'}, 'set a cloth name'); return {'CANCELLED'}
        ap = bpy.path.abspath(props.armour_patch)
        if not ap or not os.path.exists(ap): self.report({'ERROR'}, 'choose the armour patch you exported with HD2SDK'); return {'CANCELLED'}
        if props.look_mode == 'CHARACTER' and not (props.color_map and os.path.exists(bpy.path.abspath(props.color_map))):
            self.report({'ERROR'}, '4 Look: choose a colour map (or switch to My own cloth material)'); return {'CANCELLED'}
        r = _prepare_job(context, self)
        if r is None: return {'CANCELLED'}
        jd, toml, blend, objs = r
        write_settings(props, toml, blend, objs)
        sp = settings_path(props)
        if sp: write_settings(props, sp, bpy.data.filepath, objs)        # the saved record, beside the .blend
        out = bpy.path.abspath(props.out_dir) if props.out_dir else default_out(props)
        args = ['build', toml] + (['--install'] if self.install else [])
        p_cloth = props.cloth_name
        ui().job_kind = 'Build + install' if self.install else 'Build'
        def done(rc, lines):
            p = bpy.context.scene.hd2dress
            built = next((l for l in lines if l.startswith('BUILT')), None)
            inst = next((l for l in lines if l.startswith('INSTALLED')), None)
            if jobs.current().cancelled: status(bpy.context, 'Build cancelled'); return
            if rc or not built:
                import re as _re
                clean = [_re.sub(r'\x1b\[[0-9;]*m', '', l) for l in lines]
                err = [l for l in clean if l.startswith(('ERROR:', 'SystemExit', 'MemoryError')) or 'Error:' in l or l.startswith('UNIT ') and 'FAILED' in l
                       or l.startswith(('unit ', 'no vertices', 'settings:', '[cloth]', '[[piece]]', 'refusing', 'mesh name'))]
                tb = [l for l in clean if l.startswith(('Traceback',))]
                log = os.path.join(cache_dir(re.sub(r'[^A-Za-z0-9_]+', '_', p_cloth).strip('_') or 'my_cloth'), 'build.log')
                if err: why = err[-1].strip()
                elif rc and rc < 0 or rc in (137, -9, 9) or not tb:
                    why = f'the build process was stopped without an error (exit {rc}): most likely out of memory'
                else: why = clean[-1].strip()
                status(bpy.context, f'Build FAILED: {why}. Full log: {log}'); print('HD2 Dress build log:', log); return
            ui().last_out = out
            size = sum(os.path.getsize(os.path.join(out, f)) for f in os.listdir(out) if os.path.isfile(os.path.join(out, f))) if os.path.isdir(out) else 0
            if any('texconv' in l and 'failed' in l for l in lines):
                bpy.context.window_manager.popup_menu(lambda m_, c_: m_.label(text='Textures were left uncompressed (the mod works, '
                    'but is larger). Windows: install the Microsoft Visual C++ Redistributable (x64) and build again.'),
                    title='HD2 Dress: texture compression failed', icon='ERROR') if bpy.context.window_manager.windows else None
            status(bpy.context, built.replace(out, 'the output folder') + f' ({size / 1e6:.1f} MB)' + ('; ' + inst.split(' into ')[0] if inst else ''))
        jobs.start('build', jobs.blender_cmd(os.path.join(tools_dir(), 'hd2dress_cloth.py'), args), done, job_env(props),
                   os.path.join(jd, 'build.log'))
        status(context, f'{ui().job_kind} running in the background...')
        return {'FINISHED'}


class HD2DRESS_OT_preview(bpy.types.Operator):
    """Render the look (colour, normal, roughness, weave) on the cloth's UVs in Blender (no game, no physics: the cloth
    hangs in its modelled shape). Runs in the background, opens the pictures when done"""
    bl_idname = 'hd2dress.preview'; bl_label = 'Preview look'

    def execute(self, context):
        props = context.scene.hd2dress
        if props.look_mode != 'CHARACTER' or not props.color_map:
            self.report({'ERROR'}, 'choose a colour map first'); return {'CANCELLED'}
        r = _prepare_job(context, self)
        if r is None: return {'CANCELLED'}
        jd, toml, blend, objs = r
        o = active_mesh(context) if active_mesh(context) in objs else objs[0]
        write_settings(props, toml, blend, objs)
        png = os.path.join(jd, 'preview.png')
        args = ['--settings', toml, '--object', o.name, '--out', png, '--views', 'front,side,back', '--size', str(props.preview_size),
                '--samples', '24']
        ui().job_kind = 'Preview render'
        def done(rc, lines):
            if jobs.current().cancelled: status(bpy.context, 'Preview cancelled'); return
            files = next((l.split()[1:] for l in lines if l.startswith('PREVIEW')), None)
            if rc or not files: status(bpy.context, 'Preview FAILED: ' + ' | '.join(jobs.interesting(lines)[-3:])); return
            imgs = []
            for f in files:              # one image per view, always pointed at THIS render (the folder follows the cloth name)
                name = 'HD2 Dress preview ' + os.path.basename(f).replace('preview_', '').replace('.png', '')
                im = bpy.data.images.get(name)
                if im is None: im = bpy.data.images.load(f); im.name = name
                else: im.filepath = f
                im.reload(); imgs.append(im)
            shown = show_image(imgs[0])
            status(bpy.context, 'Preview done: front, side, back' + (' (switch views in the image editor\'s image list)' if shown
                                                                     else ' (open "HD2 Dress preview" in an Image Editor)'))
        jobs.start('preview', jobs.blender_cmd(os.path.join(tools_dir(), 'hd2dress_preview.py'), args, blend=blend), done,
                   job_env(props), os.path.join(jd, 'preview.log'))
        status(context, 'Preview render running in the background...')
        return {'FINISHED'}


def show_image(im):
    """Open an image in a new window's Image Editor. Called from a timer (no window in the context): borrow one."""
    wm = bpy.context.window_manager
    if not wm.windows: return False                       # background mode
    before = set(wm.windows[:])
    win0 = wm.windows[0]
    area0 = next((a for a in win0.screen.areas if a.type == 'VIEW_3D'), win0.screen.areas[0])
    try:
        with bpy.context.temp_override(window=win0, area=area0):
            bpy.ops.wm.window_new()
    except RuntimeError:
        return False
    win = next((w for w in wm.windows if w not in before), None)
    if win is None: return False
    area = max(win.screen.areas, key=lambda a: a.width * a.height)
    area.type = 'IMAGE_EDITOR'; area.spaces.active.image = im
    return True


class HD2DRESS_OT_browse(bpy.types.Operator):
    """Choose a file or folder (starts next to your .blend, or where the current one is)"""
    bl_idname = 'hd2dress.browse'; bl_label = 'Use this file'
    target: StringProperty(options={'HIDDEN'})
    filepath: StringProperty(subtype='FILE_PATH')
    directory: StringProperty(subtype='DIR_PATH')
    filter_glob: StringProperty(default='*', options={'HIDDEN'})
    filter_image: BoolProperty(default=False, options={'HIDDEN'})
    filter_folder: BoolProperty(default=True, options={'HIDDEN'})

    @classmethod
    def description(cls, context, p): return BROWSE.get(p.target, ('', 'Browse'))[1]

    def invoke(self, context, event):
        props = context.scene.hd2dress; kind = BROWSE[self.target][0]
        cur = bpy.path.abspath(getattr(props, self.target)) if getattr(props, self.target) else ''
        start = (cur if os.path.isdir(cur) else os.path.dirname(cur)) if cur and os.path.exists(os.path.dirname(cur) or cur) else ''
        if not start: start = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.path.expanduser('~')
        if kind == 'IMAGE': self.filter_image = True; self.filter_glob = '*.png;*.jpg;*.jpeg;*.tga;*.tif;*.tiff;*.bmp;*.exr'
        elif kind == 'PATCH': self.filter_glob = '*.patch_*'
        elif kind == 'TOML': self.filter_glob = '*.toml'
        self.directory = start + os.sep
        self.filepath = cur if cur and not os.path.isdir(cur) else os.path.join(start, '')
        context.window_manager.fileselect_add(self); return {'RUNNING_MODAL'}

    def execute(self, context):
        props = context.scene.hd2dress; kind = BROWSE[self.target][0]
        val = self.directory if kind == 'DIR' else self.filepath
        if kind == 'PATCH' and val.endswith(('.gpu_resources', '.stream')): val = val.rsplit('.', 1)[0]
        setattr(props, self.target, val.rstrip('/\\') if kind == 'DIR' else val)
        status(context, f'{BROWSE[self.target][1].replace("Choose ", "")}: {getattr(props, self.target)}')
        return {'FINISHED'}


class HD2DRESS_OT_preview_assets(bpy.types.Operator):
    """Read the Helldiver's skeleton, animations and body colliders from the game files (once, about a minute, in the
    background; cached for every scene)"""
    bl_idname = 'hd2dress.preview_assets'; bl_label = 'Load the Helldiver (once)'

    def execute(self, context):
        props = context.scene.hd2dress
        if not game_dir(props): self.report({'ERROR'}, 'Helldivers 2 data folder not found'); return {'CANCELLED'}
        ui(context).job_kind = 'Loading the Helldiver'
        def done(rc, lines):
            if jobs.current().cancelled: status(bpy.context, 'cancelled'); return
            if rc or not viewer.assets_ready():
                status(bpy.context, 'Loading the Helldiver FAILED: ' + ' | '.join(jobs.interesting(lines)[-3:])); return
            status(bpy.context, 'Helldiver loaded: press Play in Motion preview')
        jobs.start('Loading the Helldiver', jobs.blender_cmd(os.path.join(tools_dir(), 'viewer_assets.py'), [viewer.CACHE]), done,
                   job_env(props), os.path.join(cache_dir(), 'viewer_assets.log'))
        status(context, 'Loading the Helldiver from the game files (about a minute)...')
        return {'FINISHED'}


class HD2DRESS_OT_preview_play(bpy.types.Operator):
    """Play the Helldiver's animation with the cloth simulated live (your mesh is not changed: a preview copy is shown)"""
    bl_idname = 'hd2dress.preview_play'; bl_label = 'Play / Stop'

    def execute(self, context):
        u = ui(context)
        if u.preview_playing:
            u.preview_playing = False
            if context.screen and context.screen.is_animation_playing: bpy.ops.screen.animation_cancel(restore_frame=False)
            viewer.stop(context); viewer.hide_colliders()
            status(context, 'Motion preview stopped (your armour is shown again)')
            return {'FINISHED'}
        if not viewer.assets_ready(): self.report({'ERROR'}, 'press "Load the Helldiver" first'); return {'CANCELLED'}
        if not cloth_objects(): self.report({'ERROR'}, 'no cloth pieces yet (1 Cloth pieces)'); return {'CANCELLED'}
        if context.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
        ensure_pieces(context.scene.hd2dress)
        viewer.start(context); u.preview_playing = True
        if context.screen and not context.screen.is_animation_playing: bpy.ops.screen.animation_play()
        status(context, 'Motion preview playing: change sliders any time; Play / Stop again to end')
        return {'FINISHED'}


class HD2DRESS_OT_preview_reset(bpy.types.Operator):
    """Drop the cloth fresh from its rest shape (use after big slider changes)"""
    bl_idname = 'hd2dress.preview_reset'; bl_label = 'Reset cloth'

    def execute(self, context):
        viewer.reset(); return {'FINISHED'}


class HD2DRESS_OT_cancel(bpy.types.Operator):
    """Stop the background job"""
    bl_idname = 'hd2dress.cancel'; bl_label = 'Cancel'

    def execute(self, context):
        jobs.cancel(); status(context, 'cancelled'); return {'FINISHED'}


class HD2DRESS_OT_open_out(bpy.types.Operator):
    """Open the output folder in your file manager"""
    bl_idname = 'hd2dress.open_out'; bl_label = 'Open output folder'

    def execute(self, context):
        p = ui(context).last_out or default_out(context.scene.hd2dress)
        if not os.path.isdir(p): self.report({'ERROR'}, f'not built yet: {p}'); return {'CANCELLED'}
        bpy.ops.wm.path_open(filepath=p); return {'FINISHED'}


# ======================================================================== panel
def wrap(layout, text, icon='NONE', context=None, indent=True, min_lines=1, max_lines=0):
    """Label that wraps to the sidebar's width (Blender labels never wrap by themselves)."""
    import textwrap
    reg = (context or bpy.context).region
    px = (reg.width if reg else 300) / max(0.5, bpy.context.preferences.view.ui_scale)
    width = max(18, int((px - (44 if icon != 'NONE' else 24)) / 7.4))
    lines = textwrap.wrap(text, width) or ['']
    if max_lines and len(lines) > max_lines: lines = lines[:max_lines - 1] + [lines[max_lines - 1][:max(1, width - 1)] + '…']
    lines += [''] * (min_lines - len(lines))
    col = layout.column(align=True)
    for i, ln in enumerate(lines):
        col.label(text=ln, icon=icon if i == 0 else ('BLANK1' if icon != 'NONE' and indent else 'NONE'))
    return col


def short(name): return name[6:] if name.startswith('cloth_') else name


BROWSE = {'color_map': ('IMAGE', 'Choose the colour map'), 'normal_map': ('IMAGE', 'Choose the normal map'),
          'ao_map': ('IMAGE', 'Choose the AO map'), 'weave_map': ('IMAGE', 'Choose the weave normal map'),
          'armour_patch': ('PATCH', 'Choose the armour patch you exported with HD2SDK'),
          'settings_file': ('TOML', 'Choose the settings file'), 'out_dir': ('DIR', 'Choose the output folder'),
          'game_path': ('DIR', 'Choose the game\'s data folder (…/Helldivers 2/data)')}


def file_field(layout, props, key, label=None, extra=None):
    c = layout.column(align=True)
    if label: c.label(text=label)
    r = c.row(align=True); r.prop(props, key, text='')
    r.operator('hd2dress.browse', text='', icon='FILEBROWSER').target = key
    if extra: extra(r)
    return c


def job_box(layout, kinds):
    """The background job's progress, shown next to the button that started it."""
    u = ui()
    if not jobs.running() or not any(k in u.job_kind for k in kinds): return
    b = layout.box()
    b.label(text=f'{u.job_kind}: {u.job_elapsed:.0f} s', icon='SORTTIME'); b.operator('hd2dress.cancel', icon='CANCEL')
    lines = [x for x in u.job_lines.split('\n') if x]
    if lines: wrap(b, lines[-1][:200])


class HD2DRESS_UL_pieces(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index=0):
        r = layout.row(align=True)
        r.label(text=short(item.name), icon='MOD_CLOTH')
        if item.follow_legs: r.label(text='follows legs')


class HD2DRESS_PT_panel(bpy.types.Panel):
    bl_label = 'HD2 Dress (engine cloth)'; bl_space_type = 'VIEW_3D'; bl_region_type = 'UI'; bl_category = 'HD2 Dress'

    def draw(self, context):
        props = context.scene.hd2dress; u = ui(context); L = self.layout
        box = L.box(); wrap(box, u.status, 'INFO', context, min_lines=3, max_lines=3)     # fixed height: buttons below never jump
        job_box(box, ('Build', 'Preview', 'skeleton'))
        if not game_dir(props):
            w = L.box(); wrap(w, 'Helldivers 2 not found: choose its data folder', 'ERROR', context); file_field(w, props, 'game_path')
        sdk_v = sdk_version()
        if sdk_v is None:
            wrap(L.box(), 'HD2SDK Community Edition is not installed or not enabled: HD2 Dress needs it.', 'ERROR', context)
        elif sdk_v != SDK_TESTED:
            wrap(L.box(), f'HD2SDK {".".join(map(str, sdk_v))} is installed; HD2 Dress was tested with {".".join(map(str, SDK_TESTED))}. '
                          'It may work; if a build fails, mention the version.', 'QUESTION', context)
        self.draw_pieces(context, props, L.box())
        self.draw_check(context, props, L.box())
        self.draw_physics(context, props, L.box())
        # Motion preview (3b): unfinished, hidden until its solver matches the game (viewer.py stays in the repo)
        self.draw_look(context, props, L.box())
        self.draw_build(context, props, L.box())

    def draw_pieces(self, context, props, b):
        r = b.row(); r.label(text='1  Cloth pieces', icon='MOD_CLOTH'); r.operator('hd2dress.refresh', text='', icon='FILE_REFRESH')
        b.template_list('HD2DRESS_UL_pieces', '', props, 'pieces', props, 'piece_index', rows=2)
        edit = context.mode == 'EDIT_MESH'
        if 0 <= props.piece_index < len(props.pieces):
            p = props.pieces[props.piece_index]
            c = b.box(); c.label(text=f'Piece "{short(p.name)}"', icon='MOD_CLOTH')
            if p.counts: wrap(c, 'Vertices: ' + p.counts, context=context)
            c.prop(p, 'follow_legs')
            col = c.column(align=True)
            for k in ('leash', 'stretch', 'bend', 'stiffness', 'mass'): col.prop(p, k)
            r = c.row(align=True); r.enabled = edit
            for act, ic in (('assign', 'ADD'), ('remove', 'REMOVE'), ('select', 'RESTRICT_SELECT_OFF')):
                op = r.operator('hd2dress.piece_edit', text={'assign': 'Add', 'remove': 'Remove', 'select': 'Select'}[act], icon=ic)
                op.piece = p.name; op.action = act
            c.operator('hd2dress.piece_delete', icon='TRASH').piece = p.name
        b.operator('hd2dress.copy_pieces', icon='MOD_MIRROR')
        n = b.box(); n.label(text='New piece', icon='ADD')
        wrap(n, 'In Edit Mode, select the vertices that should move like cloth, name the piece, press New piece.', context=context)
        r = n.row(align=True); r.prop(props, 'new_name', text=''); r.operator('hd2dress.piece_new', text='New piece', icon='ADD')
        pn = b.box(); pn.label(text='Pins (where cloth hangs from)', icon='PINNED')
        if ui(context).pin_counts: wrap(pn, 'Pinned: ' + ui(context).pin_counts, context=context)
        r = pn.row(align=True); r.enabled = edit
        for act, txt in (('assign', 'Pin'), ('remove', 'Unpin'), ('select', 'Select pins')):
            r.operator('hd2dress.pin', text=txt).action = act
        wrap(pn, 'A piece without pins hangs from its top row.', context=context)
        if not edit: wrap(b, 'Tab into Edit Mode on the armour mesh to mark vertices.', 'EDITMODE_HLT', context)

    def draw_check(self, context, props, b):
        b.label(text='2  Check & fix', icon='CHECKMARK')
        r = b.row(align=True); r.operator('hd2dress.check', icon='VIEWZOOM'); r.operator('hd2dress.fix', icon='TOOL_SETTINGS')
        icons = {'PROBLEM': 'ERROR', 'FIX': 'MODIFIER', 'WARNING': 'QUESTION', 'OK': 'CHECKMARK'}
        for line in [x for x in ui(context).problems.split('\n') if x][:14]:
            lv, _, t = line.partition('\t')
            wrap(b, t, icons.get(lv, 'DOT'), context)
        wrap(b, 'After Fix all: export the armour patch with HD2SDK again.', 'EXPORT', context)

    def draw_physics(self, context, props, b):
        b.label(text='3  Physics (whole outfit)', icon='PHYSICS')
        col = b.column(align=True)
        for k in ('wind', 'gravity', 'damping', 'friction', 'radius', 'floor_gap', 'iterations'): col.prop(props, k)
        wrap(b, 'Substeps are fixed at 1 (more draws spikes on cloned divers, a game bug).', 'LOCKED', context)
        lg = b.box(); lg.label(text='Legs')
        lg.prop(props, 'follow_thigh'); lg.prop(props, 'follow_front')
        lg.prop(props, 'planes_on')
        if props.planes_on:
            col = lg.column(align=True); col.prop(props, 'planes_reach'); col.prop(props, 'planes_margin')
        lg.prop(props, 'kneecaps')
        if props.kneecaps: lg.prop(props, 'kneecap_grow')
        self.draw_body_fit(context, props, b.box())
        b.prop(props, 'show_advanced', icon='TRIA_DOWN' if props.show_advanced else 'TRIA_RIGHT', emboss=False)
        if props.show_advanced:
            col = b.column(align=True)
            for k in ('link_passes', 'motion_min', 'motion_max'): col.prop(props, k)

    def draw_body_fit(self, context, props, fb):
        fb.label(text='Body fit (your model vs the standard Helldiver)')
        wrap(fb, 'The cloth collides with invisible shapes around the standard Helldiver, not with your mesh. Fit them to your '
                 'model: thicker if it is wider (the cloth sinks in), thinner if slimmer, longer, or moved.', context=context)
        r = fb.row(align=True); r.operator('hd2dress.fit_body', icon='MOD_SHRINKWRAP')
        r.prop(props, 'show_colliders', toggle=True, icon='HIDE_OFF' if props.show_colliders else 'HIDE_ON')
        r = fb.row(align=True); r.prop(props, 'fit_share'); r.prop(props, 'fit_margin')
        if ui(context).fit_summary:
            for line in ui(context).fit_summary.split('\n'): wrap(fb, line, context=context)
        fb.prop(props, 'fit_part', text='')
        k = props.fit_part; col = fb.column(align=True)
        for f in ('thick', 'len', 'fwd', 'up', 'side'): col.prop(props, f'fit_{k}_{f}')
        changed = [n for kk, n, _ in settings.BODY_PARTS if settings.part_changed(props, kk)]
        if changed: wrap(fb, 'Changed: ' + ', '.join(changed), 'CHECKMARK', context)

    def draw_motion(self, context, props, b):
        b.label(text='3b  Motion preview', icon='PLAY')
        u = ui(context)
        if not viewer.assets_ready():
            wrap(b, 'See the cloth move on the Helldiver\'s own animations. First time: load the Helldiver from the game files.', context=context)
            b.operator('hd2dress.preview_assets', icon='IMPORT'); job_box(b, ('Loading the Helldiver',)); return
        r = b.row(align=True); r.prop(props, 'preview_anim', text=''); r.prop(props, 'preview_speed')
        r = b.row(align=True); r.scale_y = 1.3
        r.operator('hd2dress.preview_play', text='Stop' if u.preview_playing else 'Play', icon='PAUSE' if u.preview_playing else 'PLAY',
                   depress=u.preview_playing)
        r.operator('hd2dress.preview_reset', icon='FILE_REFRESH')
        r = b.row(align=True); r.prop(props, 'preview_breeze', toggle=True, icon='FORCE_WIND'); r.prop(props, 'preview_colliders', toggle=True, icon='MESH_CAPSULE')
        if props.preview_breeze: b.prop(props, 'preview_wind_dir')
        if u.preview_playing: b.label(text=f'{u.preview_ms:.1f} ms per frame', icon='TIME')
        wrap(b, 'An approximation of the game\'s cloth solver: close in feel, not exact. Check the final look in game.', 'INFO', context)

    def draw_look(self, context, props, b):
        b.label(text='4  Look', icon='MATERIAL')
        b.prop(props, 'look_mode', text='')
        if props.look_mode == 'CHARACTER':
            file_field(b, props, 'color_map', 'Colour map')
            file_field(b, props, 'normal_map', 'Normal map (optional)')
            if props.normal_map: b.prop(props, 'normal_flip_green')
            b.prop(props, 'roughness')
            file_field(b, props, 'roughness_map', 'Roughness map (optional)')
            file_field(b, props, 'ao_map', 'AO map (optional)')
            c = b.column(align=True); c.label(text='Cloth material ID (optional)'); c.prop(props, 'material_id', text='')
            b.operator('hd2dress.back_side', icon='MOD_SOLIDIFY')
            wrap(b, 'This look draws the outside only: add a back side if the inside can be seen (Check shows "back side on").', 'INFO', context)
            w = b.box(); w.prop(props, 'weave_on')
            if props.weave_on:
                wrap(w, 'Keep it subtle: folded cloth can go dark.', 'ERROR', context)
                file_field(w, props, 'weave_map', 'Weave normal map')
                col = w.column(align=True)
                for k in ('weave_tiling', 'weave_strength', 'weave_aspect'): col.prop(props, k)
            r = b.row(align=True); r.operator('hd2dress.preview', icon='RENDER_STILL'); r.prop(props, 'preview_size')
            job_box(b, ('Preview',))
        elif props.look_mode == 'KEEP':
            wrap(b, 'The cloth keeps the material its faces use in your armour patch (all its textures and values). '
                    'Export that material with HD2SDK as usual.', 'INFO', context)
            c = b.column(align=True); c.label(text='Cloth material ID (optional)'); c.prop(props, 'material_id', text='')
            b.operator('hd2dress.back_side', icon='MOD_SOLIDIFY')
        else:
            wrap(b, 'The cloth faces must already use a cape-shader material.', 'INFO', context)

    def draw_build(self, context, props, b):
        b.label(text='5  Build', icon='PACKAGE')
        c = b.column(align=True); c.label(text='Cloth name (unique per mod)'); c.prop(props, 'cloth_name', text='')
        c = b.column(align=True); c.label(text='Mod name'); c.prop(props, 'mod_name', text='')
        file_field(b, props, 'armour_patch', 'Armour patch (exported with HD2SDK)',
                   lambda r: r.operator('hd2dress.use_sdk_patch', text='', icon='EYEDROPPER'))
        file_field(b, props, 'out_dir', 'Output folder (optional)')
        c = b.column(align=True); c.label(text='Only these archives (optional)'); c.prop(props, 'archives', text='')
        objs = cloth_objects()
        if objs:
            ub = b.box(); ub.label(text='Units (from HD2SDK objects)')
            P = prep_mod()
            for o in objs:
                c = ub.column(align=True)
                c.label(text=f'{P.label(o)}: unit {settings.unit_hex(o) or "NOT A UNIT"}', icon='MESH_DATA')
                c.label(text='Mesh name (optional, found by itself)'); c.prop(o, 'hd2dress_mesh_name', text='')
        file_field(b, props, 'settings_file', 'Settings file (optional)')
        r = b.row(align=True); r.operator('hd2dress.save_settings', icon='FILE_TICK'); r.operator('hd2dress.load_settings', icon='FILE_FOLDER')
        r = b.row(align=True); r.scale_y = 1.4
        r.operator('hd2dress.build', text='Build', icon='PACKAGE').install = False
        r.operator('hd2dress.build', text='Build + install', icon='IMPORT').install = True
        job_box(b, ('Build',))
        b.operator('hd2dress.open_out', icon='FILE_FOLDER')


CLASSES = (HD2DressPiece, HD2DressUI, HD2DressProps, HD2DRESS_OT_piece_new, HD2DRESS_OT_piece_edit, HD2DRESS_OT_piece_delete, HD2DRESS_OT_pin,
           HD2DRESS_OT_copy_pieces, HD2DRESS_OT_refresh, HD2DRESS_OT_check, HD2DRESS_OT_fix, HD2DRESS_OT_back_side, HD2DRESS_OT_fit_body, HD2DRESS_OT_save_settings, HD2DRESS_OT_load_settings,
           HD2DRESS_OT_use_sdk_patch, HD2DRESS_OT_build, HD2DRESS_OT_preview, HD2DRESS_OT_browse, HD2DRESS_OT_preview_assets, HD2DRESS_OT_preview_play, HD2DRESS_OT_preview_reset, HD2DRESS_OT_cancel, HD2DRESS_OT_open_out,
           HD2DRESS_UL_pieces, HD2DRESS_PT_panel)


@bpy.app.handlers.persistent
def _on_load(*_):
    bpy.app.timers.register(_auto_refresh, first_interval=0.5)


def _auto_refresh():
    """Pieces already in the file show up without pressing Refresh."""
    try:
        sc = bpy.context.scene
        if sc is not None and hasattr(sc, 'hd2dress'):
            ensure_pieces(sc.hd2dress); refresh_counts(sc.hd2dress)
    except Exception as e:
        print('HD2 Dress: auto refresh failed:', e)
    return None


def hook_sdk_export():
    """HD2SDK's unit export treats EVERY vertex group as a bone: it stops on our cloth_* / pin groups ("not a valid vertex
    group"), and its limit-to-4-weights step counts them too. It exports a throwaway copy of the object made by
    stingray.unit.duplicate: drop our groups from that copy. The author's object keeps them. Idempotent; re-hooks
    after HD2SDK is reloaded. Returns True when hooked."""
    um = sys.modules.get('HD2SDK-CommunityEdition.stingray.unit')
    f = getattr(um, 'duplicate', None)
    if f is None: return False
    if getattr(f, '_hd2dress', False): return True
    def duplicate(obj, *a, **k):
        c = f(obj, *a, **k)
        try:
            if getattr(c, 'type', '') == 'MESH' and c.data is not getattr(obj, 'data', None):
                for g in [g for g in c.vertex_groups if g.name in ('cloth', 'pin') or g.name.startswith('cloth_')]:
                    c.vertex_groups.remove(g)
        except Exception as e: print('HD2 Dress: could not drop cloth groups from the export copy:', e)
        return c
    duplicate._hd2dress = True; duplicate._orig = f; um.duplicate = duplicate
    print('HD2 Dress: HD2SDK export hooked (cloth and pin groups are left out of the exported unit)')
    return True


def _hook_timer():
    hook_sdk_export()
    return 5.0


def register():
    colliders_view.register()
    for c in CLASSES: bpy.utils.register_class(c)
    bpy.types.Scene.hd2dress = bpy.props.PointerProperty(type=HD2DressProps)
    bpy.types.WindowManager.hd2dress_ui = bpy.props.PointerProperty(type=HD2DressUI)
    if _on_load not in bpy.app.handlers.load_post: bpy.app.handlers.load_post.append(_on_load)
    if _frame not in bpy.app.handlers.frame_change_post: bpy.app.handlers.frame_change_post.append(_frame)
    bpy.app.timers.register(_auto_refresh, first_interval=1.0)
    hook_sdk_export(); bpy.app.timers.register(_hook_timer, first_interval=2.0, persistent=True)
    bpy.types.Object.hd2dress_mesh_name = StringProperty(name='Mesh name', default='',
        description='The mesh node name in the unit. Empty = looked up from HD2SDK\'s name list (works for game armour)')


@bpy.app.handlers.persistent
def _frame(scene, depsgraph=None):
    try:
        viewer.drive(scene, depsgraph or bpy.context.evaluated_depsgraph_get())
    except Exception as e:
        import traceback; traceback.print_exc()
        bpy.context.window_manager.hd2dress_ui.preview_playing = False
        bpy.context.window_manager.hd2dress_ui.status = f'Motion preview stopped: {e}'


def unregister():
    colliders_view.unregister()
    if bpy.app.timers.is_registered(_hook_timer): bpy.app.timers.unregister(_hook_timer)
    um = sys.modules.get('HD2SDK-CommunityEdition.stingray.unit')
    if um is not None and getattr(um.duplicate, '_hd2dress', False): um.duplicate = um.duplicate._orig
    if _frame in bpy.app.handlers.frame_change_post: bpy.app.handlers.frame_change_post.remove(_frame)
    if _on_load in bpy.app.handlers.load_post: bpy.app.handlers.load_post.remove(_on_load)
    if hasattr(bpy.types.WindowManager, 'hd2dress_ui'): del bpy.types.WindowManager.hd2dress_ui
    if hasattr(bpy.types.Object, 'hd2dress_mesh_name'): del bpy.types.Object.hd2dress_mesh_name
    del bpy.types.Scene.hd2dress
    for c in reversed(CLASSES): bpy.utils.unregister_class(c)
