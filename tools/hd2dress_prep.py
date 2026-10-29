"""HD2 Dress engine cloth: prepare an author's Blender scene for cloth (run BEFORE exporting the patch with HD2SDK).

Command line (saves a COPY, the original file is never changed):
    blender -b MY_ARMOUR.blend -P tools/hd2dress_prep.py -- [--objects Obj1,Obj2] [--out OUT.blend] [--check]
    blender -b -P tools/hd2dress_prep.py -- --dump-rest REST.json      (diver skeleton rest pose from the game)
The Blender add-on imports this file and calls the same functions on the open scene.

Cloth vertices are the vertex groups named "cloth" or "cloth_<piece>" (one group per cloth piece). For every mesh
object that has one:
  1. adds the collision bones the cloth needs to the object's armature if they are missing (knees, feet, spine,
     chest, neck, head, clavicles, shoulders, elbows), with the exact rest pose of the game's own diver skeleton
     (a different roll would rotate everything driven by that bone),
  2. makes sure the mesh has 3 UV sets (the cape and the cloth render copy use UV0 = UV1 = UV2),
  3. puts 'root' in the mesh's bone palette (one cloth vertex gets a 0.001 'root' weight), needed by the
     character-shader look,
  4. turns the cloth faces outward if most of them point inward (the inside colour would show outside),
  5. moves the mesh's node to the origin when the unit carries the mesh on a moved node (many armours do, e.g.
     RS-100): the cloth physics runs at the node-less position, so the cloth would hang off the body (2026-10-22),
  6. checks and reports: a double cloth layer (z-fighting squares), a single-point UV map, lower LODs using the
     cloth's material (garbage in the armory/loadout preview), pins outside the cloth."""
import bpy, sys, os, json

# bone, parent: the collision bones of the stock cape cloth that armour units often lack
CLOTH_BONES = [('r_knee', 'r_thigh'), ('r_foot', 'r_knee'), ('l_knee', 'l_thigh'), ('l_foot', 'l_knee'), ('spine1', 'hips'),
               ('spine2', 'spine1'), ('chest', 'spine2'), ('neck', 'chest'), ('head', 'neck'),
               ('l_clavicle', 'chest'), ('r_clavicle', 'chest'), ('l_shoulder', 'l_clavicle'), ('r_shoulder', 'r_clavicle'),
               ('l_elbow', 'l_shoulder'), ('r_elbow', 'r_shoulder')]
PIN_GROUP = 'pin'
LOOK = None          # the panel's look ('CHARACTER' colour map or 'KEEP' own material: one-sided, a back side is allowed)


def is_cloth_group(name): return name == 'cloth' or name.startswith('cloth_')


def cloth_groups(o): return [g for g in o.vertex_groups if is_cloth_group(g.name)] if o.type == 'MESH' else []


def cloth_objects(): return [o for o in bpy.data.objects if o.type == 'MESH' and cloth_groups(o)]


def group_verts(o, name, wmin=0.5):
    vg = o.vertex_groups.get(name)
    if vg is None: return set()
    gi = vg.index
    return {v.index for v in o.data.vertices if any(g.group == gi and g.weight > wmin for g in v.groups)}


def cloth_verts(o):
    out = set()
    for g in cloth_groups(o): out |= group_verts(o, g.name)
    return out


def label(o):
    """Short name for messages: the body type HD2SDK stored (Slim / Stocky), else the object name."""
    bt = str(o.get('Z_CustomizationBodyType', ''))
    return bt.rsplit('_', 1)[-1] if bt.startswith('HelldiverCustomizationBodyType_') else o.name


def rig_of(o): return next((md.object for md in o.modifiers if md.type == 'ARMATURE' and md.object), None)


def missing_bones(rig): return [(n, p) for n, p in CLOTH_BONES if n not in rig.data.bones]


# ------------------------------------------------------------------ the diver skeleton's rest pose (read from the game)
def rest_cache_path():
    d = os.path.join(os.path.expanduser('~'), '.cache', 'hd2-dress'); os.makedirs(d, exist_ok=True)
    return os.path.join(d, 'diver_rest.json')


def load_rest():
    """{bone: (4x4 world matrix as nested lists, length)} from the cache, or None."""
    try: return {k: (v[0], v[1]) for k, v in json.load(open(rest_cache_path())).items()}
    except (OSError, ValueError): return None


def diver_rest_from_game():
    """Rest matrices (world) and lengths of the full diver skeleton, from the stock cape unit in the game. Loads an
    archive into HD2SDK: run it in a separate Blender (--dump-rest), not in the author's session."""
    import addon_utils
    addon_utils.enable('HD2SDK-CommunityEdition'); m = sys.modules['HD2SDK-CommunityEdition']
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from hd2_paths import game_data
    G = game_data()
    m.Global_gamepath = G; sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(G)
    before = set(bpy.data.objects)
    TM = m.Global_TocManager; TM.LoadArchive(G + '18235e0c9ec0e636', True, False)
    st = bpy.context.scene.Hd2ToolPanelSettings; keep = (st.ImportLods, st.ImportMaterials)
    st.ImportLods = False; st.ImportMaterials = False
    TM.Load(0x3c33cf10a26cbb3e, m.UnitID)
    st.ImportLods, st.ImportMaterials = keep
    new = [o for o in bpy.data.objects if o not in before]
    arm = next(o for o in new if o.type == 'ARMATURE')
    rest = {b.name: ([list(r) for r in (arm.matrix_world @ b.matrix_local)], b.length) for b in arm.data.bones}
    for o in new: bpy.data.objects.remove(o, do_unlink=True)
    return rest


# ------------------------------------------------------------------ fixes
def add_bones(rig, rest, say):
    import mathutils
    missing = missing_bones(rig)
    if not missing: return 0
    prev_active, prev_mode = bpy.context.view_layer.objects.active, bpy.context.mode
    if bpy.context.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
    hidden = rig.hide_get(); rig.hide_set(False)
    bpy.context.view_layer.objects.active = rig; rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    inv = rig.matrix_world.inverted()
    for name, parent in missing:
        M, length = rest[name]
        eb = rig.data.edit_bones.new(name); eb.length = length; eb.matrix = inv @ mathutils.Matrix(M); eb.length = length
        eb.parent = rig.data.edit_bones.get(parent)
    bpy.ops.object.mode_set(mode='OBJECT')
    rig.hide_set(hidden); bpy.context.view_layer.objects.active = prev_active
    say(f'{rig.name}: added bones {", ".join(n for n, _ in missing)}')
    return len(missing)


def three_uvs(o, say):
    me = o.data
    if not me.uv_layers: return 0
    added = 0
    while len(me.uv_layers) < 3:
        src = me.uv_layers[0]; nl = me.uv_layers.new(name=f'UVMap.{len(me.uv_layers):03d}')
        for i, d in enumerate(src.data): nl.data[i].uv = d.uv
        added += 1
    if added: say(f'{o.name}: added {added} UV set(s) (copies of UV0)')
    return added


def has_root_weight(o):
    vg = o.vertex_groups.get('root')
    return bool(vg) and any(g.group == vg.index and g.weight > 0 for v in o.data.vertices for g in v.groups)


def root_in_palette(o, say):
    if has_root_weight(o): return 0
    cv = sorted(cloth_verts(o))
    if not cv: return 0
    vg = o.vertex_groups.get('root') or o.vertex_groups.new(name='root')
    vg.add([cv[0]], 0.001, 'REPLACE')
    say(f'{o.name}: vertex {cv[0]} got a 0.001 root weight (root now in the bone palette)')
    return 1


def cloth_faces(o, cv=None):
    cv = cloth_verts(o) if cv is None else cv
    return [f for f in o.data.polygons if all(i in cv for i in f.vertices)]


def inward_count(o, faces):
    """faces whose normal points toward the body's vertical axis (through the object's origin)"""
    return sum(1 for f in faces if f.normal.x * f.center.x + f.normal.y * f.center.y < 0)


def is_ours(name): return is_cloth_group(name) or name == PIN_GROUP


def twin_faces(o, faces):
    """indices of cloth faces that have a reversed copy on the same vertices positions (a back side)"""
    me = o.data; key = {}
    for f in faces: key.setdefault(tuple(sorted(tuple(round(c, 4) for c in me.vertices[i].co) for i in f.vertices)), []).append(f)
    out = set()
    for fs in key.values():
        for a in fs:
            if any(a.normal.dot(b.normal) < -0.5 for b in fs if b is not a): out.add(a.index)
    return out


def thick_layer_count(o, faces, gap=0.012):
    """cloth faces with ANOTHER cloth face just behind them, facing the other way, on separate vertices (a Solidify-style
    inner wall). Those are two cloth sheets that simulate apart and cross through each other."""
    from mathutils.bvhtree import BVHTree
    me = o.data; tw = twin_faces(o, faces); fl = [f for f in faces if f.index not in tw]
    if len(fl) < 2: return 0
    tree = BVHTree.FromPolygons([v.co for v in me.vertices], [list(f.vertices) for f in fl])
    n = 0
    for k, f in enumerate(fl):
        hit = tree.ray_cast(f.center - f.normal * 1e-4, -f.normal, gap)
        if hit[2] is not None and hit[2] != k and fl[hit[2]].normal.dot(f.normal) < -0.5 and not set(fl[hit[2]].vertices) & set(f.vertices):
            n += 1
    return n


def has_back_side(o):
    faces = cloth_faces(o)
    return bool(faces) and len(twin_faces(o, faces)) >= len(faces) * 0.5


def add_back_side(o, say):
    """Give every cloth face a reversed copy (same vertex groups, UVs and material): the inside of the cloth then
    shows with one-sided materials (the colour map look). Front and back share the same cloth points."""
    faces = cloth_faces(o)
    if not faces: return 0
    tw = twin_faces(o, faces); todo = {f.index for f in faces} - tw
    if not todo: return 0
    import bmesh
    bm = bmesh.new(); bm.from_mesh(o.data); bm.faces.ensure_lookup_table()
    res = bmesh.ops.duplicate(bm, geom=[bm.faces[i] for i in sorted(todo)])
    new_faces = [g for g in res['geom'] if isinstance(g, bmesh.types.BMFace)]
    bmesh.ops.reverse_faces(bm, faces=new_faces)
    bm.to_mesh(o.data); bm.free(); o.data.update()
    say(f'{label(o)}: added a back side ({len(new_faces)} faces)')
    return 1


def face_outward(o, say):
    faces = cloth_faces(o)
    tw = twin_faces(o, faces); faces = [f for f in faces if f.index not in tw]   # a back side stays as it is
    if not faces or inward_count(o, faces) <= len(faces) * 0.5: return 0
    import bmesh
    bm = bmesh.new(); bm.from_mesh(o.data); bm.faces.ensure_lookup_table()
    idx = {f.index for f in faces}
    bmesh.ops.reverse_faces(bm, faces=[f for f in bm.faces if f.index in idx])
    bm.to_mesh(o.data); bm.free(); o.data.update()
    say(f'{o.name}: turned {len(faces)} cloth faces outward')
    return 1


# ------------------------------------------------------------------ the mesh's node (HD2SDK unit data)
# A unit stores each mesh relative to its own node (MeshInfo.TransformIndex). HD2SDK imports the object AT that node
# and exports the vertices as they are, so the node stays wherever the original unit had it. The game draws the cloth
# through that node too, but the cloth physics (pins, body colliders) works in the unit's space: on a moved node the
# skirt simulates that far away from the body and hangs through it. The fix: bake the node into the mesh and put the
# node at the origin (same look in game, now the physics lines up). HD2SDK re-reads the unit from its patch bytes on
# every export, so the node is reset in those bytes.
def _sdk(): return sys.modules.get('HD2SDK-CommunityEdition')


def _unit_entries(uid):
    """Every copy of the unit HD2SDK has in memory: its archives and patches. HD2SDK's unit export rebuilds the unit from
    the ARCHIVE copy (GetEntryByLoadArchive), the game's own unit, so that copy matters most."""
    m = _sdk(); tm = getattr(m, 'Global_TocManager', None) if m else None
    if tm is None: return []
    out = []
    for kw in (dict(IgnorePatch=True), dict(IgnorePatch=False)):   # what HD2SDK's export reads (loads it if needed)
        try:
            e = tm.GetEntry(uid, m.UnitID, SearchAll=True, **kw)
            if e is not None and e not in out: out.append(e)
        except Exception: pass
    for arc in list(getattr(tm, 'LoadedArchives', [])) + list(getattr(tm, 'SearchArchives', [])) + list(getattr(tm, 'Patches', [])):
        e = getattr(arc, 'TocDict', {}).get(m.UnitID, {}).get(uid)
        if e is not None and e not in out: out.append(e)
    return out


def _uid(o):
    try: return int(o.get('Z_SwapID') or o['Z_ObjectID'])
    except (KeyError, ValueError, TypeError): return None


def mesh_node(o):
    """(node index, 4x4 world matrix as rows, unit data) of the object's mesh node, or None when HD2SDK has not loaded
    the unit (open the patch in HD2SDK)."""
    uid = _uid(o); ents = _unit_entries(uid) if uid is not None else []
    if not ents or 'MeshInfoIndex' not in o: return None
    e = ents[-1]
    try:
        if not e.IsLoaded: e.Load(False, False)
        md = e.LoadedData; tix = md.MeshInfoArray[int(o['MeshInfoIndex'])].TransformIndex
        return tix, [list(md.TransformInfo.TransformMatrices[tix].v[r * 4:r * 4 + 4]) for r in range(4)], md
    except Exception as x:
        print('HD2 Dress: could not read the unit node of', o.name, repr(x)); return None


def _is_identity(rows, tol=1e-5):
    return all(abs(rows[r][c] - (1.0 if r == c else 0.0)) < tol for r in range(4) for c in range(4))


def _blender_matrix(rows):
    from mathutils import Matrix
    return Matrix(rows).transposed()            # Stingray rows (translation in row 3) -> Blender columns


def node_offset_checks(o):
    L = label(o); mb = o.matrix_basis
    ident_obj = all(abs(mb[r][c] - (1.0 if r == c else 0.0)) < 1e-5 for r in range(4) for c in range(4))
    n = mesh_node(o)
    if n is None:
        if not ident_obj:
            return [('WARNING', f'{L}: the object is moved/rotated/scaled. If HD2SDK has not loaded this unit, open its '
                                'patch in HD2SDK and Check again (a moved mesh node makes the cloth hang off the body)')]
        return []
    tix, rows, md = n
    if _is_identity(rows):
        if not ident_obj:
            return [('WARNING', f'{L}: the object is moved in Blender, but HD2SDK ignores object position on export. '
                                'Apply it (Ctrl+A, All Transforms) if you meant to move the mesh')]
        return []
    off = ', '.join(f'{x:.2f}' for x in rows[3][:3])
    if ident_obj or _matrix_close(mb, _blender_matrix(rows)):
        return [('FIX', f'{L}: the unit keeps this mesh on a moved node ({off} m): the cloth would hang off the body')]
    return [('PROBLEM', f'{L}: the unit keeps this mesh on a moved node ({off} m) and the object was moved by hand too: '
                        'reset the object (Alt+G, Alt+R, Alt+S) and run Fix all')]


def _matrix_close(a, b, tol=1e-4):
    return all(abs(a[r][c] - b[r][c]) < tol for r in range(4) for c in range(4))


def _reset_node_bytes(e, tix):
    """Set node tix's world matrix to identity (and its local transform to match) in the unit's TOC bytes."""
    import struct, numpy as np
    if not e.IsLoaded: e.Load(False, False)
    md = e.LoadedData; ti = md.TransformInfo; off = md.TransformInfoOffset
    b = bytearray(e.TocData); N = struct.unpack_from('<I', b, off)[0]
    if N != ti.NumTransforms: raise RuntimeError(f'unexpected unit layout (transform count {N} != {ti.NumTransforms})')
    par = ti.TransformEntries[tix].ParentBone
    if any(t.ParentBone == tix for i, t in enumerate(ti.TransformEntries) if i != tix):
        raise RuntimeError('other nodes hang from this mesh node; not moving it')
    Pw = np.array(ti.TransformMatrices[par].v, dtype=np.float64).reshape(4, 4) if par != tix else np.eye(4)
    Lm = np.linalg.inv(Pw)                       # local @ parent_world = identity
    S = np.linalg.norm(Lm[:3, :3], axis=1); R = Lm[:3, :3] / S[:, None]
    struct.pack_into('<9f', b, off + 16 + tix * 64, *R.ravel())
    struct.pack_into('<3f', b, off + 16 + tix * 64 + 36, *Lm[3, :3])
    struct.pack_into('<3f', b, off + 16 + tix * 64 + 48, *S)
    struct.pack_into('<16f', b, off + 16 + N * 64 + tix * 64, *np.eye(4).ravel())
    e.TocData = bytes(b)
    e.Load(True, False)                          # re-read so HD2SDK's loaded copy matches the bytes


def _bone_hash(name):
    """HD2SDK names bones by name or by their murmur32 hash in decimal."""
    if name.isdigit(): return int(name)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from gen_engine_cloth import h32
    return h32(name)


def _reset_node_bone(rig, node_hash, say):
    """HD2SDK writes every armature edit bone back into the unit's nodes on export: put the mesh node's bone at the
    origin too, or the export restores the old node position."""
    from mathutils import Matrix
    names = [b.name for b in rig.data.bones if _bone_hash(b.name) == node_hash]
    if not names: return 0
    prev_active = bpy.context.view_layer.objects.active
    if bpy.context.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
    hidden = rig.hide_get(); rig.hide_set(False)
    bpy.context.view_layer.objects.active = rig; rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    for n in names:
        eb = rig.data.edit_bones[n]; length = eb.length or 0.1
        eb.matrix = rig.matrix_world.inverted() @ Matrix.Identity(4); eb.length = length
    bpy.ops.object.mode_set(mode='OBJECT')
    rig.hide_set(hidden); bpy.context.view_layer.objects.active = prev_active
    say(f'{rig.name}: moved node bone {", ".join(names)} to the origin')
    return len(names)


def fix_node_offset(o, say):
    """Bake the mesh node into the mesh (all of the unit's objects on that node) and move the node to the origin."""
    n = mesh_node(o)
    if n is None or _is_identity(n[1]): return 0
    from mathutils import Matrix
    tix, rows, md = n
    M = _blender_matrix(rows); uid = _uid(o)
    on_node = {k for k, mi in enumerate(md.MeshInfoArray) if mi.TransformIndex == tix}
    objs = [x for x in bpy.data.objects if x.type == 'MESH' and _uid(x) == uid and int(x.get('MeshInfoIndex', -1)) in on_node]
    bake = [x for x in objs if _matrix_close(x.matrix_basis, M)]
    hand = [x.name for x in objs if x not in bake and not _matrix_close(x.matrix_basis, Matrix.Identity(4))]
    if hand: raise RuntimeError(f'{", ".join(hand)}: moved by hand as well as on a moved node; reset the object first')
    for e in _unit_entries(uid): _reset_node_bytes(e, tix)          # first: it can refuse, the bake cannot
    for x in bake:
        x.data.transform(x.matrix_basis, shape_keys=True); x.matrix_basis = Matrix.Identity(4); x.data.update()
    node_hash = md.TransformInfo.NameHashes[tix]
    for rig in {rig_of(x) for x in objs} - {None}: _reset_node_bone(rig, node_hash, say)
    say(f'{label(o)}: moved the mesh node to the origin (baked {", ".join(f"{v:.2f}" for v in rows[3][:3])} m into '
        f'{len(bake)} object(s)); export the patch with HD2SDK before building')
    return 1


# ------------------------------------------------------------------ body fit from the author's model (Fit to my model)
# The cloth collides with the stock cape's capsules (sized for the standard diver), not with the mesh. Fit: for each
# capsule, the author's body vertices weighted mostly to that bone; centre the capsule on them (move) and set its
# radius so the capsule surface reaches the given share of them (thickness). Pairs are averaged (the build mirrors).
FIT_PARTS = {'hips': ['hips'], 'spine': ['spine1'], 'thighs': ['l_thigh', 'r_thigh'], 'shins': ['l_knee', 'r_knee'],
             'feet': ['l_foot', 'r_foot'], 'head': ['head'], 'shoulders': ['l_clavicle', 'r_clavicle'],
             'upperarms': ['l_shoulder', 'r_shoulder'], 'forearms': ['l_elbow', 'r_elbow'], 'hands': ['l_hand', 'r_hand']}
FIT_MIN_VERTS = 40


def colliders_cache_path():
    d = os.path.join(os.path.expanduser('~'), '.cache', 'hd2-dress'); os.makedirs(d, exist_ok=True)
    return os.path.join(d, 'colliders.json')


def load_colliders():
    try: return json.load(open(colliders_cache_path()))
    except (OSError, ValueError): return None


def body_type(o):
    import re
    m_ = re.search(r'_(Slim|Stocky|Any)_', o.name)
    return m_.group(1) if m_ else None


def body_objects(cloth_obj):
    """The author's model for the cloth object's body type: every HD2SDK mesh (LOD0) of that body type (or 'Any')."""
    bt = body_type(cloth_obj)
    out = []
    for o in bpy.data.objects:
        if o.type != 'MESH' or 'Z_ObjectID' not in o or is_lower_lod(o) or len(o.data.vertices) < 3: continue
        b = body_type(o)
        if bt and b not in (bt, 'Any', None): continue
        out.append(o)
    return out


def body_points(objs):
    """{bone: Nx3 world points} of the body vertices (cloth vertices left out), by their strongest bone weight."""
    import numpy as np
    pts = {}
    for o in objs:
        cv = cloth_verts(o) if cloth_groups(o) else set()
        names = {g.index: g.name for g in o.vertex_groups if not is_ours(g.name)}
        Mw = o.matrix_world
        for v in o.data.vertices:
            if v.index in cv: continue
            best = max(((g.weight, names[g.group]) for g in v.groups if g.group in names), default=None)
            if best is None or best[0] < 0.5: continue
            pts.setdefault(best[1], []).append(tuple(Mw @ v.co))
    return {k: np.array(v) for k, v in pts.items()}


def capsules_world(rig, colliders):
    """[(bone, A, B, radius)] in world space at rest, from the stock capsules and the author's rig."""
    import numpy as np
    out = []
    for c in colliders:
        b = rig.data.bones.get(c['bone'])
        if b is None or c['bone'].startswith('attach_'): continue
        W = np.array(rig.matrix_world @ b.matrix_local).T          # Blender columns -> Stingray rows (as HD2SDK exports)
        Off = np.array(c['off']).reshape(4, 4)
        A = (np.append(c['start'], 1.0) @ Off @ W)[:3]; B = (np.append(c['end'], 1.0) @ Off @ W)[:3]
        out.append((c['bone'], A, B, c['radius']))
    return out


def _seg_dist(P, A, B):
    import numpy as np
    u = B - A; L2 = max(float(u @ u), 1e-12)
    t = np.clip((P - A) @ u / L2, 0.0, 1.0)
    return P - (A + t[:, None] * u)


FIT_REACH = 0.12          # body points farther than the stock radius + this from a capsule belong to something else
FIT_NO_UP = {'hips', 'spine1', 'l_clavicle', 'r_clavicle', 'head'}   # body continues above/below: the centre is not the capsule's


FIT_SLICE_ALL = {'hips', 'spine1'}   # the waist: measured from the whole body slice, whatever bone it is weighted to
FIT_SLICE = 0.06          # horizontal capsules: only the body slice this close to the capsule's height (m)


def near_points(P, A, B, r0, sliced=False):
    import numpy as np
    keep = np.linalg.norm(_seg_dist(P, A, B), axis=1) < r0 + FIT_REACH
    if sliced: keep &= np.abs(P[:, 2] - (A[2] + B[2]) / 2) < FIT_SLICE
    return P[keep]


def fit_capsule(P, A, B, r0, share=0.8, margin=0.0, no_up=False):
    """(move xyz, new radius) for one capsule from its body points P."""
    import numpy as np
    D = _seg_dist(P, A, B)
    move = D.mean(axis=0)                                    # the body's centre relative to the capsule axis
    if no_up: move[2] = 0.0
    d = np.linalg.norm(_seg_dist(P, A + move, B + move), axis=1)
    return move, float(np.quantile(d, share)) + margin


def fit_report(P, A, B, r, cloth_radius=0.025):
    """(share of body points that would poke through the cloth, median gap between capsule and body)"""
    import numpy as np
    d = np.linalg.norm(_seg_dist(P, A, B), axis=1)
    return float((d > r + cloth_radius).mean()), float(np.median(r - d))


def fit_body(cloth_obj, colliders, share=0.8, margin=0.0):
    """{part: dict(thick, fwd, up, side, n, before, after)} for the parts with enough body vertices."""
    import numpy as np
    rig = rig_of(cloth_obj)
    if rig is None: raise RuntimeError(f'{cloth_obj.name}: no armature')
    caps = {}
    for bone, A, B, r in capsules_world(rig, colliders): caps.setdefault(bone, (A, B, r))   # body capsule = first
    pts = body_points(body_objects(cloth_obj))
    import numpy as np
    allp = np.concatenate([v for v in pts.values() if len(v)]) if pts else np.zeros((0, 3))
    res = {}
    for part, bones in FIT_PARTS.items():
        vals = []
        for b in bones:
            if b not in caps: continue
            A, B, r0 = caps[b]
            # horizontal capsules: the whole body slice at their height (the waist is weighted to several bones)
            P = near_points(allp if b in FIT_SLICE_ALL else pts.get(b, np.zeros((0, 3))), A, B, r0, b in FIT_NO_UP)
            if len(P) < FIT_MIN_VERTS: continue
            mv, r = fit_capsule(P, A, B, r0, share, margin, b in FIT_NO_UP)
            side = mv[0] * (-1.0 if b.startswith('l_') else 1.0) if len(bones) == 2 else mv[0]
            vals.append(dict(thick=r - r0, fwd=mv[1], up=mv[2], side=side, n=len(P),
                             before=fit_report(P, A, B, r0), after=fit_report(P, A + mv, B + mv, r)))
        if not vals: continue
        avg = {k: float(np.mean([v[k] for v in vals])) for k in ('thick', 'fwd', 'up', 'side')}
        avg['thick'] = float(np.clip(avg['thick'], -0.25, 0.3))
        for k in ('fwd', 'up', 'side'): avg[k] = float(np.clip(avg[k], -0.3, 0.3))
        avg.update(n=sum(v['n'] for v in vals), before=vals[0]['before'], after=vals[0]['after'])
        res[part] = avg
    return res


def cloth_inside_colliders(o):
    """(free cloth vertices starting inside a collider, free total, 'worst colliders') or None. Uses the panel's Body fit
    values when the add-on is loaded (colliders_view), else the stock sizes. Needs the collider cache."""
    import numpy as np
    cols = load_colliders(); rig = rig_of(o)
    if not cols or rig is None: return None
    try:
        cv_mod = sys.modules.get('hd2_dress.colliders_view')
        props = getattr(bpy.context.scene, 'hd2dress', None)
        caps = cv_mod.capsules(props, rig, cols) if cv_mod and props else [(b, A, B, r) for b, A, B, r in capsules_world(rig, cols)]
    except Exception: caps = [(b, A, B, r) for b, A, B, r in capsules_world(rig, cols)]
    cv = cloth_verts(o); pins = group_verts(o, PIN_GROUP)
    free = [i for i in cv if i not in pins]
    if not free: return None
    V = np.array([tuple(o.matrix_world @ o.data.vertices[i].co) for i in free])
    hit = np.zeros(len(V), bool); per = {}
    need = max(50, int(0.03 * len(V)))      # as the build's auto fit: a few points resting on a collider are normal
    for k, A, B, r in caps:
        A, B = np.array(A, float), np.array(B, float); u = B - A; L2 = max(float(u @ u), 1e-12)
        t = np.clip((V - A) @ u / L2, 0, 1); d = np.linalg.norm(V - (A + t[:, None] * u), axis=1)
        h = d < r - 0.005
        if int(h.sum()) >= need: hit |= h; per[k or '?'] = per.get(k or '?', 0) + int(h.sum())
    n = int(hit.sum())
    if not n: return None
    worst = ', '.join(f'{k} {v}' for k, v in sorted(per.items(), key=lambda x: -x[1])[:3])
    return n, len(V), worst


# ------------------------------------------------------------------ checks: (level, text); level PROBLEM | WARNING | OK
def checks(o):
    out = []; me = o.data; L = label(o)
    cv = cloth_verts(o)
    faces = cloth_faces(o, cv)
    if not faces:
        return [('PROBLEM', f'{L}: no whole faces in any cloth piece (a piece needs complete faces)')]
    rig = rig_of(o)
    if rig is None: out.append(('PROBLEM', f'{L}: no Armature modifier (the HD2SDK rig is missing)'))
    else:
        mb = missing_bones(rig)
        if mb: out.append(('FIX', f'{L}: {len(mb)} collision bones missing ({", ".join(n for n, _ in mb[:3])}, ...)'))
        if 'hips' not in rig.data.bones: out.append(('PROBLEM', f'{L}: the rig has no hips bone'))
    key = {}
    for f in faces: key.setdefault(tuple(sorted(tuple(round(c, 4) for c in me.vertices[i].co) for i in f.vertices)), []).append(f.normal.copy())
    doubled = sum(1 for ns in key.values() if len(ns) > 1 and any(a.dot(b) < -0.5 for a in ns for b in ns))
    if doubled and LOOK not in ('CHARACTER', 'KEEP'):
        out.append(('PROBLEM', f'{L}: {doubled} cloth faces have a reversed copy on top: the cape-shader look draws both sides '
                               'already, two layers flicker. Delete the back layer'))
    elif doubled and doubled < len(faces) * 0.5:
        out.append(('WARNING', f'{L}: only part of the cloth has a back side ({doubled} of {len(faces)} faces): press Add back side again'))
    thick = thick_layer_count(o, faces)
    if thick > len(faces) * 0.3:
        out.append(('PROBLEM', f'{L}: the cloth is two separate layers a few mm apart ({thick} faces have another layer just '
                               'behind them, e.g. Solidify): they simulate apart and show through each other. Delete the inner '
                               'layer, then use 4 Look > Add back side to show the inside'))
    tw = twin_faces(o, faces); single = [f for f in faces if f.index not in tw]     # a back side faces inward on purpose
    inward = inward_count(o, single)
    if single and inward > len(single) * 0.5: out.append(('FIX', f'{L}: {inward} of {len(single)} cloth faces point inward'))
    if not me.uv_layers: out.append(('PROBLEM', f'{L}: no UV map: unwrap the cloth'))
    else:
        uv = me.uv_layers[0].data
        us = {(round(uv[li].uv[0], 3), round(uv[li].uv[1], 3)) for f in faces for li in f.loop_indices}
        if len(us) < 4: out.append(('PROBLEM', f'{L}: the cloth uses {len(us)} UV point(s): unwrap it'))
        if len(me.uv_layers) < 3: out.append(('FIX', f'{L}: {len(me.uv_layers)} UV set(s), the cloth needs 3'))
    if not has_root_weight(o): out.append(('FIX', f'{L}: root is not in the bone palette'))
    # materials: the build gives ONE material the cloth look; cloth faces on another material draw nothing in game
    slot = lambda f: (o.material_slots[f.material_index].material.name if f.material_index < len(o.material_slots)
                      and o.material_slots[f.material_index].material else '(none)')
    cmats = {}
    for f in faces: cmats[slot(f)] = cmats.get(slot(f), 0) + 1
    if len(cmats) > 1:
        main = max(cmats, key=cmats.get)
        out.append(('PROBLEM', f'{L}: cloth faces use {len(cmats)} materials; only "{main}" becomes cloth, the other '
                               f'{sum(cmats.values()) - cmats[main]} faces would be invisible in game: give them all one material'))
    fs = {f.index for f in faces}
    shared = sum(1 for f in me.polygons if f.index not in fs and slot(f) in cmats)
    if shared: out.append(('WARNING', f'{L}: {shared} armour faces also use the cloth material "{max(cmats, key=cmats.get)}": '
                                      'they get the cloth look too (give them their own material)'))
    # closed shapes: cloth needs an open sheet with an edge to hang from
    for g in cloth_groups(o):
        gv = group_verts(o, g.name)
        if not gv: out.append(('WARNING', f'{L}: piece "{g.name}" has no vertices')); continue
        edges = {}
        for f in faces:
            if not all(i in gv for i in f.vertices): continue
            vs = list(f.vertices)
            for a, b in zip(vs, vs[1:] + vs[:1]): k = (min(a, b), max(a, b)); edges[k] = edges.get(k, 0) + 1
        if edges and not any(n == 1 for n in edges.values()):
            out.append(('WARNING', f'{L}: piece "{g.name}" is a closed shape (no open edge). Cloth is a sheet: a closed '
                                   'shell collapses in game. Use only the hanging part'))
    pins = group_verts(o, PIN_GROUP)
    if pins - cv: out.append(('WARNING', f'{L}: {len(pins - cv)} pinned vertices are not in any cloth piece (ignored)'))
    # the game draws a mesh that carries cloth with ONE material: its first (2026-10-24, a tester (SA-7 cloak)'s torso: body + cloak, the
    # cloak showed the body texture; swapping the order fixed the cloak and broke the body)
    used = sorted({f.material_index for f in me.polygons})
    if len(used) > 1:
        out.append(('PROBLEM', f'{L}: this mesh uses {len(used)} materials, but in game a mesh with cloth is drawn with ONE '
                               '(its first): the other faces get the wrong texture. Put the cloth on a unit of its own (for '
                               'example an unused Accessory unit) with one material'))
    inside = cloth_inside_colliders(o)
    if inside:
        n, total, worst = inside
        out.append(('WARNING', f'{L}: {n} of {total} free cloth points start inside the body colliders ({worst}). The build '
                               'shrinks those colliders so the cloth starts outside (the body may poke through there); '
                               'Fit to my model (3 Physics) fits them to your body instead'))
    if 'Z_ObjectID' not in o: out.append(('PROBLEM', f'{L}: not an HD2SDK unit object (no Z_ObjectID)'))
    else: out += node_offset_checks(o)
    if not any(lv in ('PROBLEM', 'FIX') for lv, _ in out):
        out.append(('OK', f'{L}: {len(faces)} cloth faces, {len(cloth_groups(o))} piece(s), {len(pins & cv)} pins'
                          + (', back side on' if doubled else '')))
    return out


def is_lower_lod(o): n = o.name.lower(); return '_lod' in n and not n.endswith('lod0')


def _custom(o, k): return str(o.get('Z_Customization' + k, ''))


def same_piece_other_body(o, ref):
    """o is the same armour piece as ref (slot and piece type) on ANOTHER body type (not 'Any')."""
    return (_custom(o, 'Slot') == _custom(ref, 'Slot') and _custom(o, 'PieceType') == _custom(ref, 'PieceType')
            and _custom(o, 'BodyType') != _custom(ref, 'BodyType') and not _custom(o, 'BodyType').endswith('_Any'))


def unit_siblings(objs):
    """The same armour piece (slot + piece type) on the OTHER body types than the cloth objects' (LOD0 meshes):
    e.g. the Slim and Stocky skirt when the cloth is on Brawny. Other meshes of the slot (undergarment, accessory) are not."""
    bodies = {_custom(o, 'BodyType') for o in objs}
    return [o for o in bpy.data.objects if o.type == 'MESH' and o not in objs and 'Z_ObjectID' in o and not is_lower_lod(o)
            and _custom(o, 'BodyType') not in bodies and any(same_piece_other_body(o, ref) for ref in objs)]


def copy_pieces(src, dst, say, max_dist=0.03):
    """Copy every cloth piece and the pins from one body's mesh to another (slim <-> stocky): each vertex of dst takes
    the groups of the nearest src vertex within max_dist (m). Returns {group: vertices assigned}."""
    import mathutils
    sv = src.data.vertices
    kd = mathutils.kdtree.KDTree(len(sv))
    for v in sv: kd.insert(v.co, v.index)
    kd.balance()
    names = [g.name for g in cloth_groups(src)] + ([PIN_GROUP] if PIN_GROUP in src.vertex_groups else [])
    members = {n: group_verts(src, n) for n in names}
    out = {}
    for n in names:
        tg = dst.vertex_groups.get(n) or dst.vertex_groups.new(name=n)
        hit = []
        for v in dst.data.vertices:
            co, i, d = kd.find(v.co)
            if i is not None and d <= max_dist and i in members[n]: hit.append(v.index)
        hit = _drop_strays(dst, hit, max(3, len(members[n]) // 10)) if n != PIN_GROUP else hit
        tg.remove([v.index for v in dst.data.vertices])
        if hit: tg.add(hit, 1.0, 'REPLACE')
        out[n] = len(hit)
        say(f'{label(dst)}: {n} {len(hit)} vertices (from {label(src)} {len(members[n])})')
    return out


def _drop_strays(o, idx, min_size):
    """Keep only clumps of the chosen vertices (connected by mesh edges among themselves) with at least min_size
    vertices: armour vertices that happen to sit near the source piece come along in small clumps."""
    sel = set(idx); nb = {i: [] for i in sel}
    for e in o.data.edges:
        a, b = e.vertices
        if a in sel and b in sel: nb[a].append(b); nb[b].append(a)
    keep, seen = [], set()
    for i in sel:
        if i in seen: continue
        comp, stack = [], [i]; seen.add(i)
        while stack:
            j = stack.pop(); comp.append(j)
            for k in nb[j]:
                if k not in seen: seen.add(k); stack.append(k)
        if len(comp) >= min_size: keep += comp
    return sorted(keep)


def piece_coverage(objs):
    """Pieces that exist on some body types but not others (the other body would get no cloth there)."""
    out = []
    others = sorted({label(o) for o in unit_siblings(objs)})
    if others:
        on = ', '.join(sorted({label(o) for o in objs}))
        out.append(('WARNING', f'the cloth is only on {on}: {" and ".join(others)} {"gets" if len(others) == 1 else "get"} no cloth. Fine if that is what you '
                               'want; for the other bodies too press "Copy pieces to the other body"'))
    if len(objs) < 2: return out
    names = {g.name for o in objs for g in cloth_groups(o)}
    for n in sorted(names):
        missing = [label(o) for o in objs if n not in o.vertex_groups]
        if missing:
            out.append(('WARNING', f'piece "{n}" is missing on {", ".join(missing)}: that body gets no cloth there'))
    return out


def lod_checks(objs):
    out = []
    mats = {s.material.name for o in objs for s in o.material_slots if s.material}
    for o in bpy.data.objects:
        if o.type != 'MESH' or o in objs or '_lod' not in o.name.lower() or o.name.lower().endswith('lod0'): continue
        if any(s.material and s.material.name in mats for s in o.material_slots):
            out.append(('PROBLEM', f'{o.name}: this lower LOD uses the cloth material: give it a normal material (or no LODs)'))
    return out


def check_all(objs=None):
    objs = cloth_objects() if objs is None else objs
    if not objs: return [('PROBLEM', 'no mesh has a cloth piece yet (vertex group "cloth" or "cloth_<name>")')]
    return [c for o in objs for c in checks(o)] + piece_coverage(objs) + lod_checks(objs)


def fix_all(objs, rest, say):
    """Apply every automatic fix. rest = load_rest() (needed only when bones are missing). Returns the number of fixes."""
    n = 0
    for o in objs:
        rig = rig_of(o)
        if rig is not None and missing_bones(rig):
            if rest is None: raise RuntimeError('the diver skeleton is not cached yet (run --dump-rest)')
            n += add_bones(rig, rest, say)
    for o in objs:
        n += three_uvs(o, say) + root_in_palette(o, say) + face_outward(o, say)
    for o in objs:
        n += fix_node_offset(o, say)
    return n


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    def opt(name, default=None): return args[args.index(name) + 1] if name in args else default
    if '--dump-rest' in args:
        path = opt('--dump-rest'); json.dump(diver_rest_from_game(), open(path, 'w')); print('REST', path); sys.exit(0)
    names = [x for x in (opt('--objects') or '').split(',') if x]
    objs = [bpy.data.objects[n] for n in names] if names else cloth_objects()
    def say(s): print('PREP', s)
    if not objs: raise SystemExit('no mesh object has a cloth vertex group ("cloth" or "cloth_<piece>"; or use --objects)')
    if '--check' not in args:
        SRC = bpy.data.filepath
        OUT = opt('--out') or (os.path.splitext(SRC)[0] + '_hd2dress.blend' if SRC else None)
        if not OUT: raise SystemExit('open your .blend (blender -b FILE.blend -P ...) or pass --out')
        if SRC and os.path.abspath(OUT) == os.path.abspath(SRC): raise SystemExit('--out must not be the original file')
        rest = load_rest()
        if rest is None and any(rig_of(o) and missing_bones(rig_of(o)) for o in objs):
            rest = diver_rest_from_game(); json.dump(rest, open(rest_cache_path(), 'w'))
        fix_all(objs, rest, say)
    for lv, txt in check_all(objs): say(f'{lv}: {txt}')
    if '--check' not in args:
        bpy.ops.wm.save_as_mainfile(filepath=OUT, copy=True)
        say(f'saved {OUT} (the original is unchanged). Next: export the patch with HD2SDK as usual, then build the cloth.')
