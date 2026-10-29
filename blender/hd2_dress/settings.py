"""Panel values <-> the build tool's TOML settings file (tools/hd2dress_cloth.py). The TOML stays the saved record:
the same file builds from the command line, and Load settings brings it back into the panel."""
import bpy, os, math

# panel defaults = the values tested in game (docs/ENGINE_CLOTH_VALUES.md, test rig 2026-10-18)
PIECE_KEYS = ('mass', 'stiffness', 'leash', 'stretch', 'bend')
SIM_KEYS = {'gravity': 'gravity', 'damping': 'damping', 'iterations': 'iterations', 'link_passes': 'link_passes',
            'radius': 'radius', 'friction': 'friction', 'landscape_radius': 'floor_gap', 'wind': 'wind'}
PIN_GROUP = 'pin'
# body fit: (key, label, bones). Pairs are mirrored (sideways = outward).
BODY_PARTS = [('hips', 'Hips', ['hips']), ('spine', 'Lower back', ['spine1']), ('thighs', 'Thighs', ['l_thigh', 'r_thigh']),
              ('shins', 'Knees and shins', ['l_knee', 'r_knee']), ('feet', 'Feet', ['l_foot', 'r_foot']), ('head', 'Head', ['head']),
              ('shoulders', 'Shoulders', ['l_clavicle', 'r_clavicle']), ('upperarms', 'Upper arms', ['l_shoulder', 'r_shoulder']),
              ('forearms', 'Forearms', ['l_elbow', 'r_elbow']), ('hands', 'Hands', ['l_hand', 'r_hand']),
              ('chest', 'Chest', [])]          # chest: two added capsules (collision.chest), see gen_engine_cloth


def part_changed(props, k):
    return (abs(getattr(props, f'fit_{k}_thick')) > 1e-6 or abs(getattr(props, f'fit_{k}_len') - 1) > 1e-6 or
            any(abs(getattr(props, f'fit_{k}_{f}')) > 1e-6 for f in ('fwd', 'up', 'side')))


def toml_value(v):
    if isinstance(v, bool): return 'true' if v else 'false'
    if isinstance(v, int): return str(v)
    if isinstance(v, float):
        r = round(v, 6)
        return repr(float(r)) if math.isfinite(r) else '0.0'
    if isinstance(v, str): return '"' + v.replace('\\', '\\\\').replace('"', '\\"') + '"'
    if isinstance(v, (list, tuple)): return '[' + ', '.join(toml_value(x) for x in v) + ']'
    if isinstance(v, dict): return '{ ' + ', '.join(f'{k} = {toml_value(x)}' for k, x in v.items()) + ' }'
    raise TypeError(f'cannot write {v!r}')


def dumps(st, header=''):
    out = [header] if header else []
    for k, v in st.items():
        if not isinstance(v, dict) and not (isinstance(v, list) and v and isinstance(v[0], dict)): out.append(f'{k} = {toml_value(v)}')
    for k, v in st.items():
        if isinstance(v, dict):
            out.append(f'\n[{k}]'); out += [f'{a} = {toml_value(b)}' for a, b in v.items()]
    for k, v in st.items():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            for e in v:
                out.append(f'\n[[{k}]]'); out += [f'{a} = {toml_value(b)}' for a, b in e.items()]
    return '\n'.join(out) + '\n'


def rel_path(p, base):
    p = bpy.path.abspath(p) if p else ''
    if not p: return ''
    try: return os.path.relpath(p, base).replace('\\', '/')
    except ValueError: return p                          # another drive (Windows)


def unit_hex(o):
    try: return f'{int(str(o["Z_ObjectID"])):016x}'
    except (KeyError, ValueError): return None


def to_settings(props, objs, base, blend):
    """objs: the cloth objects (each an HD2SDK unit). base: folder the paths are written relative to."""
    from . import prep_mod
    P = prep_mod()
    st = {'name': props.mod_name or props.cloth_name, 'cloth_name': props.cloth_name,
          'armour_patch': rel_path(props.armour_patch, base), 'blend': rel_path(blend, base)}
    if props.out_dir: st['out'] = rel_path(props.out_dir, base)
    arcs = [a.strip() for a in props.archives.replace(';', ',').split(',') if a.strip()]
    if arcs: st['archives'] = arcs
    units = []
    for o in objs:
        u = {'id': unit_hex(o), 'object': o.name}
        if o.hd2dress_mesh_name.strip(): u['mesh_name'] = o.hd2dress_mesh_name.strip()
        units.append(u)
    st['unit'] = units
    st['cloth'] = {'pin_group': PIN_GROUP}
    if props.look_mode == 'CHARACTER': st['cloth']['allow_double_layer'] = True     # one-sided: a back side is wanted, no flicker
    st['sim'] = {k: getattr(props, a) for k, a in SIM_KEYS.items()}
    st['sim']['substeps'] = 1
    st['follow'] = {'thigh': props.follow_thigh, 'front': props.follow_front}
    st['motion'] = {'minTranslationSpeed': props.motion_min, 'maxTranslationSpeed': props.motion_max,
                    'minRotationSpeed': 90.0, 'maxRotationSpeed': 360.0}
    st['planes'] = {'enabled': props.planes_on, 'reach': props.planes_reach, 'margin': props.planes_margin}
    col = {}
    if props.kneecaps:
        k = {'start': -0.05, 'end': 0.05, 'grow': props.kneecap_grow}
        col['extra'] = {'l_knee': dict(k), 'r_knee': dict(k)}
    grow, length, move = {}, {}, {}                 # body fit: colliders shaped like the author's model
    for k, _, bones in BODY_PARTS:
        th, ln = getattr(props, f'fit_{k}_thick'), getattr(props, f'fit_{k}_len')
        fw, up, sd = (getattr(props, f'fit_{k}_{f}') for f in ('fwd', 'up', 'side'))
        for b in bones:
            if abs(th) > 1e-6: grow[b] = round(th, 4)
            if abs(ln - 1) > 1e-6: length[b] = round(ln, 4)
            if abs(fw) + abs(up) + abs(sd) > 1e-6:
                sign = -1.0 if b.startswith('l_') else 1.0          # +X = right; a left part moves outward to -X
                move[b] = [round(sd * sign, 4), round(fw, 4), round(up, 4)]
    if grow: col['grow'] = grow
    if length: col['length'] = length
    if move: col['offset'] = move
    if part_changed(props, 'chest'):
        col['chest'] = {'grow': round(props.fit_chest_thick, 4), 'length': round(props.fit_chest_len, 4),
                        'offset': [round(props.fit_chest_side, 4), round(props.fit_chest_fwd, 4), round(props.fit_chest_up, 4)]}
    if col: st['collision'] = col
    if props.look_mode == 'KEEP':
        lk = {'shader': 'character', 'keep_material': True}
        if props.material_id.strip().isdigit(): lk['material_id'] = int(props.material_id.strip())
        st['look'] = lk
    if props.look_mode == 'CHARACTER':
        lk = {'shader': 'character', 'color': rel_path(props.color_map, base), 'roughness': props.roughness}
        if props.roughness_map: lk['roughness_map'] = rel_path(props.roughness_map, base)
        if props.normal_map: lk['normal'] = rel_path(props.normal_map, base)
        if props.normal_flip_green: lk['normal_flip_green'] = True
        if props.ao_map: lk['ao'] = rel_path(props.ao_map, base)
        if props.material_id.strip().isdigit(): lk['material_id'] = int(props.material_id.strip())
        if props.weave_on and props.weave_map:
            lk.update(weave=rel_path(props.weave_map, base), weave_tiling=props.weave_tiling,
                      weave_strength=props.weave_strength, weave_aspect=props.weave_aspect)
        st['look'] = lk
    pieces, seen = [], set()
    for o in objs:
        for g in P.cloth_groups(o):
            if g.name in seen: continue
            seen.add(g.name)
            pc = piece_props(props, g.name)
            e = {'group': g.name, 'follow_legs': pc.follow_legs if pc else False}
            for k in PIECE_KEYS: e[k] = getattr(pc, k) if pc else getattr(PIECE_DEFAULTS, k)
            pieces.append(e)
    st['piece'] = pieces
    return st


class _Defaults:
    mass, stiffness, leash, stretch, bend = 0.004, 1.0, 1.0, 0.6, 0.24
PIECE_DEFAULTS = _Defaults()


def piece_props(props, group):
    return next((p for p in props.pieces if p.name == group), None)


def from_settings(props, st, base, objs):
    """Load a settings dict into the panel (and the pieces' settings into every object that has those groups)."""
    ab = lambda p: p if not p or os.path.isabs(os.path.expanduser(p)) else os.path.normpath(os.path.join(base, p))
    props.cloth_name = st.get('cloth_name', props.cloth_name)
    props.mod_name = st.get('name', '')
    props.armour_patch = ab(os.path.expanduser(st.get('armour_patch', '')))
    props.out_dir = ab(os.path.expanduser(st['out'])) if 'out' in st else ''
    props.archives = ', '.join(st.get('archives', []))
    sim = st.get('sim', {})
    for k, a in SIM_KEYS.items():
        if k in sim: setattr(props, a, type(getattr(props, a))(sim[k]))
    f = st.get('follow', {})
    if 'thigh' in f: props.follow_thigh = float(f['thigh'])
    if 'front' in f: props.follow_front = bool(f['front'])
    mo = st.get('motion', {})
    if 'minTranslationSpeed' in mo: props.motion_min = float(mo['minTranslationSpeed'])
    if 'maxTranslationSpeed' in mo: props.motion_max = float(mo['maxTranslationSpeed'])
    pl = st.get('planes')
    props.planes_on = bool(pl and pl.get('enabled', True))
    if pl:
        props.planes_reach = float(pl.get('reach', props.planes_reach)); props.planes_margin = float(pl.get('margin', 0.0))
    cl = st.get('collision', {}); gr, ln, mv = cl.get('grow', {}), cl.get('length', {}), cl.get('offset', {})
    ch = cl.get('chest') or {}
    props.fit_chest_thick = float(ch.get('grow', 0.0)); props.fit_chest_len = float(ch.get('length', 1.0))
    o = ch.get('offset', [0.0, 0.0, 0.0]); props.fit_chest_side, props.fit_chest_fwd, props.fit_chest_up = (float(x) for x in o)
    for k, _, bones in BODY_PARTS:
        if not bones: continue
        b = bones[-1]                                # the right / centre bone carries the values (pairs are mirrored)
        setattr(props, f'fit_{k}_thick', float(gr.get(b, 0.0))); setattr(props, f'fit_{k}_len', float(ln.get(b, 1.0)))
        o = mv.get(b, [0.0, 0.0, 0.0])
        setattr(props, f'fit_{k}_side', float(o[0])); setattr(props, f'fit_{k}_fwd', float(o[1])); setattr(props, f'fit_{k}_up', float(o[2]))
    ex = st.get('collision', {}).get('extra', {})
    props.kneecaps = 'l_knee' in ex or 'r_knee' in ex
    if props.kneecaps: props.kneecap_grow = float((ex.get('l_knee') or ex.get('r_knee')).get('grow', 0.03))
    lk = st.get('look')
    if lk and lk.get('keep_material'):
        props.look_mode = 'KEEP'; props.material_id = str(lk['material_id']) if 'material_id' in lk else ''
    elif lk and lk.get('shader', 'character') == 'character':
        props.look_mode = 'CHARACTER'
        props.color_map = ab(lk.get('color', '')); props.normal_map = ab(lk.get('normal', ''))
        props.normal_flip_green = bool(lk.get('normal_flip_green', False)); props.ao_map = ab(lk.get('ao', ''))
        props.roughness = float(lk.get('roughness', 0.7))
        props.roughness_map = ab(lk.get('roughness_map', ''))
        props.material_id = str(lk['material_id']) if 'material_id' in lk else ''
        props.weave_on = bool(lk.get('weave')); props.weave_map = ab(lk.get('weave', ''))
        props.weave_tiling = float(lk.get('weave_tiling', 40.0)); props.weave_strength = float(lk.get('weave_strength', 0.2))
        props.weave_aspect = float(lk.get('weave_aspect', 1.0))
    else:
        props.look_mode = 'OWN'
    by_id = {u.get('object'): u for u in st.get('unit', [])}
    for o in objs:
        u = by_id.get(o.name)
        if u and u.get('mesh_name'): o.hd2dress_mesh_name = u['mesh_name']
    for e in st.get('piece', []):
        if not e.get('group'): continue
        pc = piece_props(props, e['group'])
        if pc is None: pc = props.pieces.add(); pc.name = e['group']
        pc.follow_legs = bool(e.get('follow_legs', False))
        for k in PIECE_KEYS:
            if k in e: setattr(pc, k, float(e[k]))
