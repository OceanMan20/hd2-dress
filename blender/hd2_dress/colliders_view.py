"""Show colliders: draws the cloth's body colliders (the stock cape capsules on the author's rig, with Body fit,
kneecaps and the chest colliders applied exactly like the build does) as outlines in the 3D viewport. Live: the
drawing reads the panel values on every redraw. Nothing is added to the scene or saved in the .blend."""
import bpy, math
from mathutils import Matrix, Vector

MIN_RADIUS = 0.005                       # as gen_engine_cloth
_handle = None
COLOR_PART = (0.25, 1.0, 0.35, 0.95)     # the body part picked in Body fit
COLOR_OTHER = (1.0, 0.55, 0.15, 0.55)


def part_of_bone():
    from . import settings
    return {b: k for k, _, bones in settings.BODY_PARTS for b in bones}


def capsules(props, rig, colliders):
    """[(part, A, B, radius)] in world space, as the build will place them."""
    from . import settings
    parts = part_of_bone()
    out = []
    body = {}
    for c in colliders:
        bone = c['bone']
        if bone.startswith('attach_') or bone in ('l_hand', 'r_hand'): continue      # hands are opt-in (settings file)
        b = rig.data.bones.get(bone)
        if b is None: continue
        W = Matrix(rig.matrix_world @ b.matrix_local).transposed()                     # Stingray rows
        Off = Matrix([c['off'][i * 4:i * 4 + 4] for i in range(4)])
        M = Off @ W
        def world(p): return (Vector((p[0], p[1], p[2], 1.0)) @ M).xyz
        k = parts.get(bone)
        th = getattr(props, f'fit_{k}_thick', 0.0) if k else 0.0
        ln = getattr(props, f'fit_{k}_len', 1.0) if k else 1.0
        mv = Vector((0, 0, 0))
        if k:
            sign = -1.0 if bone.startswith('l_') else 1.0
            mv = Vector((getattr(props, f'fit_{k}_side') * sign, getattr(props, f'fit_{k}_fwd'), getattr(props, f'fit_{k}_up')))
        if bone in body: continue                                                        # first capsule of a bone = body
        a, e = Vector(c['start']), Vector(c['end']); mid = (a + e) / 2
        a, e = mid + (a - mid) * ln, mid + (e - mid) * ln
        r = max(MIN_RADIUS, c['radius'] + th)
        body[bone] = (c, M, r)
        out.append((k, world(a) + mv, world(e) + mv, r))
        if props.kneecaps and bone in ('l_knee', 'r_knee'):                              # collision.extra, along bone x
            s0 = c['start']
            out.append((k, world((-0.05, s0[1], s0[2])) + mv, world((0.05, s0[1], s0[2])) + mv, r + props.kneecap_grow))
    if settings.part_changed(props, 'chest') and rig.data.bones.get('chest'):            # collision.chest
        Wc = Matrix(rig.matrix_world @ rig.data.bones['chest'].matrix_local).transposed()
        base = Wc[3].xyz
        r = max(MIN_RADIUS, 0.07 + props.fit_chest_thick); half = 0.02 * props.fit_chest_len
        for side in (-1.0, 1.0):
            cen = Vector((side * (0.075 + props.fit_chest_side), base.y + 0.11 + props.fit_chest_fwd, base.z - 0.06 + props.fit_chest_up))
            out.append(('chest', cen + Vector((0, 0, half)), cen - Vector((0, 0, half)), r))
    return out


def capsule_lines(A, B, r, seg=24):
    """Line segment pairs outlining a capsule: end rings, 4 side lines, 2 arcs over each end."""
    u = B - A; L = u.length
    u = u.normalized() if L > 1e-9 else Vector((0, 0, 1))
    v = u.orthogonal().normalized(); w = u.cross(v)
    pts = []
    def ring(c):
        for i in range(seg):
            a0, a1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
            pts.extend([c + (v * math.cos(a0) + w * math.sin(a0)) * r, c + (v * math.cos(a1) + w * math.sin(a1)) * r])
    ring(A); ring(B)
    for k in range(4):
        d = (v * math.cos(k * math.pi / 2) + w * math.sin(k * math.pi / 2)) * r
        pts.extend([A + d, B + d])
    for c, s in ((A, -1), (B, 1)):
        for ax in (v, w):
            for i in range(seg // 2):
                a0, a1 = math.pi * i / (seg // 2), math.pi * (i + 1) / (seg // 2)
                pts.extend([c + (ax * math.cos(a0) + u * s * math.sin(a0)) * r, c + (ax * math.cos(a1) + u * s * math.sin(a1)) * r])
    return pts


def _rigs(prep):
    seen, out = set(), []
    for o in prep.cloth_objects():
        if not o.visible_get(): continue
        rig = prep.rig_of(o)
        if rig is not None and rig.name not in seen: seen.add(rig.name); out.append(rig)
    return out


def _draw():
    try:
        sc = bpy.context.scene; props = getattr(sc, 'hd2dress', None)
        if props is None or not props.show_colliders: return
        from . import prep_mod
        P = prep_mod(); cols = P.load_colliders()
        if not cols: return
        import gpu
        from gpu_extras.batch import batch_for_shader
        hi, lo = [], []
        for rig in _rigs(P):
            for k, A, B, r in capsules(props, rig, cols):
                (hi if k == props.fit_part else lo).extend(capsule_lines(A, B, r))
        sh = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        reg = bpy.context.region
        gpu.state.blend_set('ALPHA'); gpu.state.depth_test_set('NONE')
        for pts, col, wd in ((lo, COLOR_OTHER, 1.2), (hi, COLOR_PART, 2.2)):
            if not pts: continue
            batch = batch_for_shader(sh, 'LINES', {'pos': pts})
            sh.uniform_float('viewportSize', (reg.width, reg.height)); sh.uniform_float('lineWidth', wd)
            sh.uniform_float('color', col); batch.draw(sh)
        gpu.state.blend_set('NONE')
    except Exception as e:                                # never break the viewport
        print('HD2 Dress: collider drawing failed:', e)


def redraw(self=None, context=None):
    for win in bpy.context.window_manager.windows:
        for a in win.screen.areas:
            if a.type == 'VIEW_3D': a.tag_redraw()


def register():
    global _handle
    if _handle is None: _handle = bpy.types.SpaceView3D.draw_handler_add(_draw, (), 'WINDOW', 'POST_VIEW')


def unregister():
    global _handle
    if _handle is not None: bpy.types.SpaceView3D.draw_handler_remove(_handle, 'WINDOW'); _handle = None
