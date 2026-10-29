#!/usr/bin/env python3
"""HD2 Dress engine-cloth generator: builds a game cloth resource for one mesh of a unit.
Normally used through tools/hd2dress_cloth.py (settings file -> patches); spec_from_settings() maps the
settings file onto the spec below, DEFAULTS holds the tested values.

Uses the stock cape cloth as the TEMPLATE (Havok types, collidables, settings, operator chain) and
replaces everything mesh-specific. Pure data in, bytes out; every piece is plain and editable:

    python3 tools/gen_engine_cloth.py UNITS.json UNIT_HEX SPEC.json OUT.bin

UNITS.json  from tools/export_unit_mesh.py (nodes, world matrices, the mesh in GPU vertex order)
SPEC.json   what to simulate and how (see testrig_spec() for the test rig):
  mesh_name        the mesh node name (murmur32 must equal the mesh id in the unit)
  cloth_name       name of the cloth data (its hash is the resource's variant key)
  cloth_material   index of the material range whose vertices are cloth (the rest is skinned)
  bones            transform set: unit node names the cloth reads (first must be 'skeleton')
  pin_height       particles at/above this height (mesh space z) are pinned to their skin bone
  groups           per cloth island ("strip"): match by angle, settings: mass, stiffness, leash
  sim              gravity, damping, substeps, iterations, particle radius, friction

Self-checks before writing (a bad cloth froze the game once): counts, index ranges, name hashes."""
import json, math, struct, sys
import numpy as np
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # (rsplit('/') broke on Windows paths)
from havok_model import Model, Struct, Ref, ArrayRef
from havok_cloth import pv_pack, deformer_build
from havok_writer import spans_of

TEMPLATE = os.path.join(os.path.expanduser('~'), '.cache', 'hd2-dress', 'cloth', '18235e0c9ec0e636_3c33cf10a26cbb3e_main.bin')   # fallback only
TEMPLATE_BYTES = None          # set by the builder (read from the game: stock cape cloth 18235e0c9ec0e636 / 3c33cf10a26cbb3e)
MIN_RADIUS = 0.005             # body fit can shrink a collider this far (2026-10-23: slim models need near-zero hips)
TEMPLATE_ARCHIVE, TEMPLATE_ID, CLOTH_TYPE = '18235e0c9ec0e636', 0x3c33cf10a26cbb3e, 0xd7014a50477953e0

# Every collision bone the template cape has a shape for, in transform-set order. A garment uses the ones its
# unit contains (armour units often lack knees/feet/upper body: add them to the unit, see the guide).
ALL_BONES = ['skeleton', 'root', 'hips', 'r_thigh', 'r_knee', 'r_foot', 'l_thigh', 'l_knee', 'l_foot', 'spine1',
             'spine2', 'chest', 'neck', 'head', 'l_clavicle', 'r_clavicle', 'l_shoulder', 'r_shoulder', 'l_elbow', 'r_elbow']
HAND_BONES = ['l_hand', 'r_hand']          # template capsules too; only with collision.hands = true
# The game simulates these (the cape's bones, a chain down the back); on the ship they swing in the breeze. Cloth that
# follows them (piece setting 'cape_follow', EXPERIMENTAL: added copies do not get the cape's flap). Unit must have them.
CAPE_BONES = [f'cape{i}' for i in range(1, 9)]

# Tested defaults (docs/ENGINE_CLOTH_VALUES.md): floor skirt on the B-01 test rig, 2026-10-18.
DEFAULTS = dict(
    sim=dict(gravity=9.81, damping=0.7, substeps=1, iterations=4, link_passes=3, radius=0.02, friction=0.8, landscape_radius=0.07, wind=1.0),   # substeps>1 = engine bug (spikes on cloned divers)
    part=dict(mass=0.004, stiffness=1.0, leash=0.55, stretch=0.60, bend=0.8, inward=None, cape_follow=0.0, cape_follow_leash=0.15, cape_follow_back_only=True),
    follow=dict(thigh=0.6, front=True),
    motion=dict(minTranslationSpeed=0.5, maxTranslationSpeed=2.0, minRotationSpeed=90.0, maxRotationSpeed=360.0),
    pin_tolerance=0.002,
    bone_planes=None)


def spec_from_settings(st, unit_entry, unit_data):
    """Settings file (dict from TOML) + one [[unit]] entry + exported unit data -> generator spec.
    Missing values fall back to DEFAULTS. Unknown keys are refused (typos would silently do nothing)."""
    known = {'name', 'cloth_name', 'armour_patch', 'blend', 'archives', 'unit', 'cloth', 'sim', 'part', 'parts', 'piece',
             'follow', 'motion', 'collision', 'out', 'planes', 'look'}
    bad = set(st) - known
    if bad: raise SystemExit(f'unknown settings: {sorted(bad)} (known: {sorted(known)})')
    def sect(name, allowed):
        d = dict(DEFAULTS.get(name, {})); d.update(st.get(name, {}))
        badk = set(d) - set(allowed)
        if badk: raise SystemExit(f'unknown keys in [{name}]: {sorted(badk)}')
        return d
    sim = sect('sim', DEFAULTS['sim']); part = sect('part', DEFAULTS['part'])
    follow = sect('follow', DEFAULTS['follow']); motion = sect('motion', DEFAULTS['motion'])
    cloth = st.get('cloth', {})
    have = set(unit_data['nodes']['hashes'])
    bones = unit_entry.get('bones') or cloth.get('bones') or [b for b in ALL_BONES if h32(b) in have]
    if st.get('collision', {}).get('hands') and not (unit_entry.get('bones') or cloth.get('bones')):
        # opt-in (2026-10-23): the template cape also has hand capsules; hands push the cloth (fists on a chest piece)
        miss = [b for b in HAND_BONES if h32(b) not in have]
        if miss: raise SystemExit(f"collision.hands: the unit has no {', '.join(miss)} bone (add them to its armature)")
        bones = bones + HAND_BONES
    windy = any(float(pc.get('cape_follow', 0) or 0) > 0 for pc in st.get('piece', [])) or float(st.get('part', {}).get('cape_follow', 0) or 0) > 0
    if windy:
        missing = [b for b in CAPE_BONES if h32(b) not in have]
        if missing: raise SystemExit(f"unit {unit_entry['id']}: cape_follow needs the cape bones {missing} in the unit (Fix all adds them)")
        bones = bones + [b for b in CAPE_BONES if b not in bones]
    for b in ('skeleton', 'hips'):
        if b not in bones: raise SystemExit(f"unit {unit_entry['id']}: bone '{b}' missing (needed by every cloth)")
    groups = [dict(part, **{k: v for k, v in p.items()}) for p in st.get('parts', [])]
    for g in groups:
        if 'angle' not in g: raise SystemExit('[[parts]] entries need an angle (degrees around the body, 0 = front)')
    # [[piece]]: a named cloth piece = a vertex group in the .blend with its own settings (positions filled by the builder)
    pieces = []
    for pc in st.get('piece', []):
        badk = set(pc) - set(DEFAULTS['part']) - {'group', 'follow_legs'}
        if badk: raise SystemExit(f'unknown keys in [[piece]]: {sorted(badk)}')
        if 'group' not in pc: raise SystemExit('[[piece]] entries need group = "the vertex group name"')
        pieces.append({**part, 'follow_legs': False, **pc})
    spec = dict(mesh_name=unit_entry['mesh_name'], cloth_name=st['cloth_name'], bones=bones,
                groups=groups or [dict(part, angle=0)], ring_part=dict(part, angle=None), sim=sim,
                pin_tolerance=cloth.get('pin_tolerance', DEFAULTS['pin_tolerance']),
                transfer_motion=motion, collision_grow=st.get('collision', {}).get('grow', {}),
                collision_extra=st.get('collision', {}).get('extra', {}),
                collision_length=st.get('collision', {}).get('length', {}),
                collision_offset=st.get('collision', {}).get('offset', {}),
                collision_auto_fit=bool(st.get('collision', {}).get('auto_fit', True)),
                collision_chest=st.get('collision', {}).get('chest'), collision_skip=st.get('collision', {}).get('skip', []))
    if pieces: spec['pieces'] = pieces
    pl = st.get('planes')
    if pl and pl.get('enabled', True):
        bad = set(pl) - {'enabled', 'reach', 'margin', 'stiffness', 'bones'}
        if bad: raise SystemExit(f'unknown keys in [planes]: {sorted(bad)}')
        spec['bone_planes'] = {k: v for k, v in pl.items() if k != 'enabled'}
    if follow.get('thigh') and {'l_thigh', 'r_thigh'} <= set(bones):
        spec['thigh_follow'] = follow['thigh']; spec['front_follow'] = follow.get('front', False)
    if 'material_slot' in cloth: spec['cloth_material'] = cloth['material_slot']
    if cloth.get('texcoord15'): spec['texcoord15'] = True
    if cloth.get('no_skin_elements'): spec['no_skin_elements'] = True
    if cloth.get('render_root_skin'): spec['render_root_skin'] = True
    if cloth.get('render_backfaces'): spec['render_backfaces'] = True
    if cloth.get('oct_normals'): spec['oct_normals'] = True
    if cloth.get('strip_scene', True): spec['strip_scene'] = True        # verified in game 2026-10-18 (7.1 -> 0.68 MB)
    return spec


def murmur64(data, seed=0):
    m, r, MASK = 0xc6a4a7935bd1e995, 47, 2 ** 64 - 1
    d = bytearray(data); h = seed ^ ((m * len(d)) & MASK)
    off = len(d) // 8 * 8
    for i in range(0, off, 8):
        k = int.from_bytes(d[i:i + 8], 'little'); k = (k * m) & MASK; k ^= k >> r; k = (k * m) & MASK
        h ^= k; h = (h * m) & MASK
    rem = d[off:]
    for i in range(len(rem) - 1, -1, -1): h ^= rem[i] << (8 * i)
    if rem: h = (h * m) & MASK
    h ^= h >> r; h = (h * m) & MASK; h ^= h >> r
    return h


def h32(s): return murmur64(s.encode()) >> 32


def half(x): return struct.unpack('<H', struct.pack('<e', float(x)))[0]


# ======================================================================== mesh-side data
class Garment:
    def __init__(self, unit, spec):
        self.spec = spec
        nodes = unit['nodes']; self.node_hash = nodes['hashes']
        self.world = [np.array(w, dtype=np.float64).reshape(4, 4) for w in nodes['world']]
        idx = {h: i for i, h in enumerate(self.node_hash)}
        self.bones = list(spec['bones'])
        self.bone_nodes = [idx[h32(b)] for b in self.bones]
        me = unit['mesh']
        assert me['id'] == h32(spec['mesh_name']), f"mesh id {me['id']:#x} != murmur32({spec['mesh_name']})"
        self.P = np.array(me['positions'], dtype=np.float64)
        self.N = np.array([n[:3] for n in me['normals']], dtype=np.float64)
        self.UV = [np.array(u, dtype=np.float64) for u in me['uvs']]
        self.tris = np.array(me['triangles'], dtype=np.int64).reshape(-1, 3)
        self.nv = len(self.P)
        bi = unit['bone_info']; real = bi['RealIndices']; remap = bi['Remaps'][0]
        self.pal_real, self.pal_remap = list(real), list(remap)
        def rows4(seq, n, fill):
            """per vertex, 4 values: HD2SDK stores a vertex's weights/indices as a list OR a single value (meshes with one
            influence per vertex, e.g. parts hidden with the blank material, 2026-10-22 user report)"""
            out = []
            for k in range(n):
                r = seq[k] if k < len(seq) else []
                r = list(r) if hasattr(r, '__len__') and not isinstance(r, (str, bytes)) else [r]
                r = [float(x) for x in r][:4]
                out.append(r + [fill] * (4 - len(r)))
            return np.array(out, dtype=np.float64)
        bi_src = me['bone_indices'][0] if me['bone_indices'] else []
        bidx = rows4(bi_src, self.nv, 0).astype(np.int64)
        w = rows4(me['weights'] or [], self.nv, 0.0)
        none = w.sum(1) <= 0                     # no weights stored: the vertex is fully on its first index
        w[none, 0] = 1.0
        self.raw_bone_idx = [[int(x) for x in r] for r in bidx]; self.raw_w = [[float(x) for x in r] for r in w]
        # per vertex: list of (transform index, weight)
        node_to_t = {n: t for t, n in enumerate(self.bone_nodes)}
        self.skin = []
        for v in range(self.nv):
            acc = {}
            for j in range(4):
                if w[v][j] <= 0: continue
                node = real[remap[bidx[v][j]]]
                t = node_to_t.get(node)
                if t is None:           # weighted to a bone outside the collision set (spine3, a custom bone...): it only
                    t = len(self.bone_nodes)  # carries the skinning, so add it to the transform set (no collider)
                    self.bone_nodes.append(node); self.bones.append(f'#node{node}'); node_to_t[node] = t
                acc[t] = acc.get(t, 0) + w[v][j]
            self.skin.append(sorted(acc.items(), key=lambda x: x[1]))
        # which vertices are cloth: those used by triangles of the cloth material range
        if spec.get('cloth_positions'):            # cloth = triangles whose 3 vertices sit on given positions
            keys = {tuple(np.round(p, 4)) for p in spec['cloth_positions']}
            on = np.array([tuple(np.round(p, 4)) in keys for p in self.P])
            self.cloth_tris_disp = np.array([t for t in self.tris if on[t].all()])
        else:
            mats = me['materials']; cm = mats[spec['cloth_material']]
            first, count = cm['StartIndex'] // 3, cm['NumIndices'] // 3
            self.cloth_tris_disp = self.tris[first:first + count]
        self.cloth_verts = sorted(set(self.cloth_tris_disp.ravel().tolist()))
        # the mesh must sit on a node at the origin: the game draws the cloth through the mesh's node, but the physics
        # (pins, body colliders) runs in unit space, so a moved node leaves the cloth hanging that far off the body
        M = np.array(me.get('transform') or np.eye(4).ravel(), dtype=np.float64).reshape(4, 4)
        # (only when the cloth was found: no match = a patch exported before the cloth was marked, and the build's
        # 'matches no vertex ... export again' message is the right one, 2026-10-24 a tester (SA-7 cloak))
        if self.cloth_verts and not np.allclose(M, np.eye(4), atol=1e-5):
            raise SystemExit(f"the unit keeps the mesh '{spec['mesh_name']}' on a moved node "
                             f"({', '.join(f'{x:.2f}' for x in M[3][:3])} m), so the cloth would hang off the body. In Blender: "
                             "HD2 Dress > 2 Check & fix > Fix all (with the patch open in HD2SDK), then export the patch with "
                             "HD2SDK again and build")
        self.build_particles()
        # what the game draws: the mesh's triangles, plus (option render_backfaces, an author's idea 2026-10-23) every
        # cloth triangle again reversed on the SAME vertices, so the inside shows with no new vertices (but it is lit
        # with the outside normals). Add back side in Blender is the other route (own vertices, flipped normals).
        self.draw_tris = self.tris
        if spec.get('render_backfaces') and len(self.cloth_tris_disp):
            self.draw_tris = np.concatenate([self.tris, self.cloth_tris_disp[:, [0, 2, 1]]])

    def build_particles(self):
        """One particle per distinct cloth vertex position (front and back layers share particles)."""
        key = {}; self.vert_particle = {}; pos = []
        for v in self.cloth_verts:
            k = tuple(np.round(self.P[v], 5))
            if k not in key: key[k] = len(pos); pos.append(self.P[v])
            self.vert_particle[v] = key[k]
        self.pp = np.array(pos)
        tris, seen = [], set()
        for a, b, c in self.cloth_tris_disp:
            t = (self.vert_particle[a], self.vert_particle[b], self.vert_particle[c])
            s = tuple(sorted(t))
            if s in seen or len(set(t)) < 3: continue
            seen.add(s); tris.append(t)
        self.ptris = np.array(tris)
        # islands (strips) by connectivity
        parent = list(range(len(self.pp)))
        def f(i):
            while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
            return i
        for a, b, c in self.ptris: parent[f(a)] = f(b); parent[f(b)] = f(c)
        roots = {}
        self.island = [roots.setdefault(f(i), len(roots)) for i in range(len(self.pp))]
        self.n_islands = len(roots)
        # pinned = the author's pin vertices (spec pin_positions) where an island has any, else its top row
        tol = self.spec.get('pin_tolerance', 0.002)
        tops = {}
        for i in range(len(self.pp)): tops[self.island[i]] = max(tops.get(self.island[i], -1e9), self.pp[i, 2])
        key4 = [tuple(np.round(p, 4)) for p in self.pp]
        pins = {tuple(np.round(p, 4)) for p in self.spec.get('pin_positions') or []}
        pinned = {i for i in range(len(self.pp)) if key4[i] in pins}
        has_pins = {self.island[i] for i in pinned}
        self.fixed = sorted(pinned) + \
                     [i for i in range(len(self.pp)) if self.island[i] not in has_pins and self.pp[i, 2] >= tops[self.island[i]] - tol]
        self.fixed.sort(); self._fixed_set = set(self.fixed)
        self._free_first()
        key4 = [tuple(np.round(p, 4)) for p in self.pp]           # particle order may have changed
        self.pinned_by_group = len(has_pins)
        # named pieces (spec pieces, from vertex groups): each island takes the piece most of its points belong to
        pieces = self.spec.get('pieces')
        if pieces:
            owner = {}
            for k, pc in enumerate(pieces):
                for p in pc.get('positions', []): owner.setdefault(tuple(np.round(p, 4)), k)
            self.part_settings = []; self.island_piece = []
            for isl in range(self.n_islands):
                votes = {}
                for i in range(len(self.pp)):
                    if self.island[i] == isl and key4[i] in owner: votes[owner[key4[i]]] = votes.get(owner[key4[i]], 0) + 1
                k = max(votes, key=votes.get) if votes else 0
                c = self.pp[[i for i in range(len(self.pp)) if self.island[i] == isl]].mean(0)
                ang = math.degrees(math.atan2(-c[0], c[1])) % 360
                pc = {x: v for x, v in pieces[k].items() if x != 'positions'}
                # follow_legs pieces get the skirt treatment (thigh follow); the rest keep their own skinning
                self.part_settings.append(dict(pc, measured_angle=None if pc.get('follow_legs') else ang))
                self.island_piece.append(pc['group'])
            return
        # per island settings by its angle around the body (0 = front +Y, 90 = left -X)
        self.part_settings = []
        groups = self.spec['groups']
        for isl in range(self.n_islands):
            c = self.pp[[i for i in range(len(self.pp)) if self.island[i] == isl]].mean(0)
            ang = math.degrees(math.atan2(-c[0], c[1])) % 360
            ring = self.spec.get('ring_part')          # a closed ring (skirt): its centroid sits on the axis
            if ring and np.hypot(c[0], c[1]) < 0.05:
                self.part_settings.append(dict(ring, measured_angle=None)); continue
            g = min(groups, key=lambda g: min(abs(ang - g['angle']), 360 - abs(ang - g['angle'])))
            self.part_settings.append(dict(g, measured_angle=ang))

    def _free_first(self):
        """Engine workaround: the game's wind code (aero apply, normals branch, rva 0x8a2890) uses particle 0's mass for
        EVERY particle; a fixed particle 0 (mass 0) gives the whole cloth zero wind (2026-10-21). Swap the first free
        particle into slot 0 (the stock cape has a free particle 0)."""
        if not self.fixed or self.fixed[0] != 0: return
        k = next((i for i in range(len(self.pp)) if i not in self._fixed_set), None)
        if k is None: return
        perm = list(range(len(self.pp))); perm[0], perm[k] = k, 0          # new index -> old index
        inv = {old: new for new, old in enumerate(perm)}
        self.pp = self.pp[perm]
        self.island = [self.island[perm[n]] for n in range(len(perm))]
        self.vert_particle = {v: inv[p] for v, p in self.vert_particle.items()}
        self.ptris = np.array([[inv[int(a)] for a in t] for t in self.ptris]) if len(self.ptris) else self.ptris
        self.fixed = sorted(inv[i] for i in self.fixed); self._fixed_set = set(self.fixed)

    def wind_weights(self):
        """Per particle (cape bone transform index, weight) for pieces with wind > 0: the BACK of the piece, more toward
        the hem, follows the nearest cape bone (the game swings those in the ship's breeze)."""
        if getattr(self, '_wind', None) is not None: return self._wind
        self._wind = {}
        cape = [(t, self.world[self.bone_nodes[t]][3][:3] if abs(self.world[self.bone_nodes[t]][3][3]) == 1
                 else self.world[self.bone_nodes[t]][:3, 3]) for t, b in enumerate(self.bones) if b in CAPE_BONES]
        if not cape: return self._wind
        for isl, st in enumerate(self.part_settings):
            w0 = float(st.get('cape_follow', 0) or 0)
            if w0 <= 0: continue
            idx = [i for i in range(len(self.pp)) if self.island[i] == isl]
            ztop = max(self.pp[i, 2] for i in idx); zbot = min(self.pp[i, 2] for i in idx)
            ymin = min(self.pp[i, 1] for i in idx)
            for i in idx:
                if i in self._fixed_set: continue
                down = (ztop - self.pp[i, 2]) / max(ztop - zbot, 1e-6)
                back = (np.clip(self.pp[i, 1] / ymin, 0.0, 1.0) if ymin < 0 else 0.0) if st.get('cape_follow_back_only', True) else 1.0
                w = w0 * down * back
                if w < 0.02: continue
                t = min(cape, key=lambda c: np.linalg.norm(np.asarray(c[1]) - self.pp[i]))[0]
                self._wind[i] = (t, float(w))
        return self._wind

    # bind matrices
    def bind(self, t): return self.world[self.bone_nodes[t]]
    def inv_bind(self, t): return np.linalg.inv(self.world[self.bone_nodes[t]])


# ======================================================================== cloth data
def bits(n, on):
    words = [0] * ((n + 31) // 32)
    for b in on: words[b // 32] |= 1 << (b % 32)
    return words


def build_clothdata(m, g):
    """Edit the template hclClothData (Model m, tagfile 4) into the garment's cloth."""
    d = m.root
    S = g.spec['sim']; T = len(g.bones); NP = len(g.pp); ND = g.nv
    t_index = {b: i for i, b in enumerate(g.bones)}
    hips = t_index['hips']
    # ---------------- template objects we keep
    sim = d['simClothDatas'][0]
    bufs = d['bufferDefinitions']
    keep_bufs = [bufs.item.elems[i] for i in (0, 1, 2, 13, 19)]          # display, scratch, sim, prev, shadow
    ops = d['operators'].item.elems
    keep_ops = [ops[i] for i in (0, 1, 2, 3, 4, 39)]
    states = d['clothStateDatas'].item.elems
    keep_states = [states[0], states[6]]                                  # Simulate, Off
    trans = d['stateTransitions'].item.elems
    keep_trans = [trans[0], trans[1], trans[2]]
    BUF = {0: 0, 1: 1, 2: 2, 13: 3, 19: 4}
    d['simClothDatas'] = [Ref(d['simClothDatas'].item.elems[0].item)]
    d['bufferDefinitions'] = keep_bufs; d['operators'] = keep_ops
    d['clothStateDatas'] = keep_states; d['stateTransitions'] = keep_trans
    d['name'] = g.spec['cloth_name']
    d['transformSetDefinitions'][0]['numTransforms'] = T

    def remap_used_buffers(lst):
        if lst is None: return
        for ub in lst.item.elems:
            ub['bufferIndex'] = BUF[ub['bufferIndex']]; ub['shadowBufferIndex'] = BUF[ub['shadowBufferIndex']]

    def set_trackers(usage_sets, comp0, comp1=()):
        if usage_sets is None: return
        for us in usage_sets.item.elems:
            us['transformSetIndex'] = 0
            for k, tr in enumerate(us['transformSetUsage']['perComponentTransformTrackers']):
                on = comp0 if k == 0 else comp1
                for key in ('read', 'readBeforeWrite', 'written'):
                    st = tr[key]['storage']
                    st['words'] = bits(T, on if key != 'written' else [])
                    st['numBits'] = T

    # ---------------- buffers
    b0, b1, b2, b13, b19 = [x.value for x in keep_bufs]
    b0['name'] = g.spec['mesh_name']; b0['numVertices'] = ND; b0['numTriangles'] = len(g.draw_tris)
    dstride = 60 + (4 if g.spec.get('texcoord15') else 0) - (12 if g.spec.get('no_skin_elements') else 0)
    if dstride != 60:                             # display buffer stride must match the render copy's vertex stride
        for sl in b0['bufferLayout']['slots']:
            if sl['stride'] == 60: sl['stride'] = dstride
    b1['name'] = g.spec['mesh_name'] + '_simple'; b1['numVertices'] = NP; b1['numTriangles'] = 0
    for b, nm in ((b2, ' SimCloth SimBuffer'), (b13, ' SimCloth SimBuffer Prev')):
        b['name'] = g.spec['cloth_name'] + nm; b['numVertices'] = NP; b['numTriangles'] = len(g.ptris)
    b19['numVertices'] = ND
    for b in (b0, b1, b2, b13, b19):
        if 'triangleIndices' in b.keys(): b['triangleIndices'] = None

    # ---------------- particles, pose, constraints
    fixed = set(g.fixed)
    parts = []
    pdt = m.type_named('hclSimClothData::ParticleData')
    total = 0.0
    for i in range(NP):
        p = Struct(pdt)
        st = g.part_settings[g.island[i]]
        if i in fixed: p['mass'], p['invMass'], p['radius'], p['friction'] = 0.0, 0.0, 0.006, S['friction']
        else:
            mass = st['mass']; p['mass'], p['invMass'], p['radius'], p['friction'] = mass, 1.0 / mass, S['radius'], S['friction']
            total += mass
        parts.append(p)
    sim['particleDatas'] = parts
    sim['fixedParticles'] = sorted(fixed)
    sim['simulationInfo']['gravity'] = [0.0, 0.0, -S['gravity'], 0.0]
    sim['simulationInfo']['globalDampingPerSecond'] = S['damping']
    # totalMass is read only by the engine's wind code: wind acceleration ~ 1 / totalMass. The stock cape's 2.562 is the
    # SUM OF ITS FREE PARTICLE MASSES (854 x 0.003). Like the cape: totalMass = real free mass / wind (2026-10-24: a fixed
    # 2.562 made big cloths far too windy, a tester (SA-7 cloak)'s 2333-point cloak acted 3.6x lighter). 0 = no wind (engine skips it).
    wind = float(S.get('wind', 1.0))
    sim['totalMass'] = float(total) / wind if wind > 0 and total > 0 else 0.0
    sim['maxParticleRadius'] = S['radius']
    sim['landscapeCollisionData']['landscapeRadius'] = S.get('landscape_radius', 0.07)   # gap kept off the floor
    pose = sim['simClothPoses'][0]
    pose['name'] = 'DefaultClothPose'
    pose['positions'] = [[float(x), float(y), float(z), 1.0] for x, y, z in g.pp]
    sim['simClothPoses'] = [sim['simClothPoses'].item.elems[0]]
    sim['triangleIndices'] = [int(x) for x in g.ptris.ravel()]
    sim['triangleFlips'] = [0] * ((len(g.ptris) + 7) // 8)
    mask = sim['staticCollisionMasks'][0]
    sim['staticCollisionMasks'] = [mask] * NP
    sim['perParticlePinchDetectionEnabledFlags'] = [False] * NP
    sim['simOpIds'] = [3]
    sim['numLandscapeCollidableParticles'] = NP - len(fixed)

    inv = lambda i: 0.0 if i in fixed else 1.0 / g.part_settings[g.island[i]]['mass']
    sets = sim['staticConstraintSets'].item.elems
    std, stretch, local = sets[0], sets[1], sets[5]
    # standard links: every edge of the sheet
    edges = sorted({tuple(sorted((int(a), int(b)))) for t in g.ptris for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0]))})
    edges = [e for e in edges if not (e[0] in fixed and e[1] in fixed)]
    def batches_of(links):
        """Greedy SIMD batches of 4 with no particle twice in a batch; the rest become singles."""
        rest = list(links); out = []
        while True:
            used, batch, left = set(), [], []
            for l in rest:
                if len(batch) < 4 and l[0] not in used and l[1] not in used: batch.append(l); used.update(l[:2])
                else: left.append(l)
            if len(batch) < 4: return out, batch + left
            out.append(batch); rest = left
    sl = []
    for a, b in edges:
        k = g.part_settings[g.island[a]]['stiffness']
        wa, wb = inv(a), inv(b); s = wa + wb
        sl.append((a, b, float(np.linalg.norm(g.pp[a] - g.pp[b])), k * wa / s, -k * wb / s))
    bt, singles = batches_of(sl)
    BT = m.type_named('hclStandardLinkConstraintSetMx::Batch'); ST = m.type_named('hclStandardLinkConstraintSetMx::Single')
    std_b = []
    for bch in bt:
        x = Struct(BT); x['restLengths'] = [l[2] for l in bch]; x['stiffnessesA'] = [l[3] for l in bch]
        x['stiffnessesB'] = [l[4] for l in bch]; x['particlesA'] = [l[0] for l in bch]; x['particlesB'] = [l[1] for l in bch]
        std_b.append(x)
    std_s = []
    for l in singles:
        x = Struct(ST); x['restLength'] = l[2]; x['stiffnessA'] = l[3]; x['stiffnessB'] = l[4]; x['particleA'] = l[0]; x['particleB'] = l[1]
        std_s.append(x)
    std.value['batches'] = std_b; std.value['singles'] = std_s if std_s else None
    # stretch links: each free particle to the nearest pinned particle of its strip (max length = rest * (1 + allow))
    stl = []
    for i in range(NP):
        if i in fixed: continue
        cands = [f for f in fixed if g.island[f] == g.island[i]]
        f = min(cands, key=lambda f: np.linalg.norm(g.pp[f, :2] - g.pp[i, :2]))
        allow = g.part_settings[g.island[i]].get('stretch', 0.05)
        stl.append((f, i, float(np.linalg.norm(g.pp[f] - g.pp[i])) * (1 + allow)))
    bt, singles = batches_of(stl)
    BT = m.type_named('hclStretchLinkConstraintSetMx::Batch'); ST = m.type_named('hclStretchLinkConstraintSetMx::Single')
    sb = []
    for bch in bt:
        x = Struct(BT); x['restLengths'] = [l[2] for l in bch]; x['stiffnesses'] = [1.0] * 4
        x['particlesA'] = [l[0] for l in bch]; x['particlesB'] = [l[1] for l in bch]; sb.append(x)
    ss = []
    for l in singles:
        x = Struct(ST); x['restLength'] = l[2]; x['stiffness'] = 1.0; x['particleA'] = l[0]; x['particleB'] = l[1]; ss.append(x)
    stretch.value['batches'] = sb; stretch.value['singles'] = ss if ss else None
    # local range (leash): how far each free particle may move from where skinning would put it
    LT = m.type_named('hclLocalRangeConstraintSet::LocalConstraint')
    lc = []
    for i in range(NP):
        if i in fixed: continue
        x = Struct(LT); x['particleIndex'] = i; x['referenceVertex'] = i
        x['maximumDistance'] = g.part_settings[g.island[i]]['leash']
        if i in g.wind_weights():        # follows the swinging cape bones: hold it close enough to follow them
            x['maximumDistance'] = min(x['maximumDistance'], float(g.part_settings[g.island[i]].get('cape_follow_leash', 0.15)))
        x['maxNormalDistance'] = 3.402820018375656e+38; x['minNormalDistance'] = -3.402820018375656e+38
        inward = g.part_settings[g.island[i]].get('inward')
        if inward is not None: x['minNormalDistance'] = -float(inward)     # may not sink deeper than this behind
        lc.append(x)                                                         # its rest spot (outward normal, see sim skin)
    local.value['localConstraints'] = lc
    if any(st.get('inward') is not None for st in g.part_settings): local.value['applyNormalComponent'] = True
    # bend stiffness (as in the cape): one constraint per hinge = edge (C, D) shared by two sheet triangles
    # with opposite corners A and B. Weights = closest points between lines AB and CD; rest curvature =
    # -(height of the hinge) / (distance A-hinge * distance B-hinge); stiffness = -k / sum(w^2 invMass).
    # All three verified against the stock cape (2320 constraints; curvature fit corr 0.99996).
    bend = sets[3]
    edge_tris = {}
    for t in g.ptris:
        for a, b, c in ((t[0], t[1], t[2]), (t[1], t[2], t[0]), (t[2], t[0], t[1])):
            edge_tris.setdefault(tuple(sorted((int(a), int(b)))), []).append(int(c))
    hinges = []
    for (c_, d_), opp in edge_tris.items():
        if len(opp) != 2: continue
        a_, b_ = opp
        if all(i in fixed for i in (a_, b_, c_, d_)): continue
        A, B, C, D = g.pp[[a_, b_, c_, d_]]
        d1, d2, r = B - A, D - C, A - C
        aa, bb, cc, dd, ee = d1 @ d1, d1 @ d2, d2 @ d2, d1 @ r, d2 @ r
        den = aa * cc - bb * bb
        if abs(den) < 1e-12: continue
        s_, t_ = (bb * ee - cc * dd) / den, (aa * ee - bb * dd) / den
        w = np.array([1 - s_, s_, -(1 - t_), -t_])
        v = w @ np.array([A, B, C, D])
        e = d2 / np.linalg.norm(d2)
        dl = lambda X: np.linalg.norm((X - C) - ((X - C) @ e) * e)
        n = np.cross(B - A, D - C); n /= np.linalg.norm(n)
        curv = -(v @ n) / (dl(A) * dl(B))
        im = np.array([inv(i) for i in (a_, b_, c_, d_)])
        k = g.part_settings[g.island[c_]].get('bend', 0.8)
        effective = float((w ** 2 * im).sum())
        # Three pinned vertices can leave a negligible solve weight on the only free vertex (thebf333's guard). The first
        # threshold (1e-10) was far too loose: a tester (SA-7 cloak)'s cloak kept a hinge with free weight 0.000056 -> stiffness -303408
        # (typical -0.002) and flung that point 270 m (live memory, 2026-10-24). Skip hinges whose free part carries
        # less than ~0.1 of a free vertex's weight; the stiffness clamp below catches anything else.
        if not np.isfinite(effective) or effective <= float(im.max()) * 0.01:
            continue
        hinges.append(((a_, b_, c_, d_), w, float(curv), float(-k / effective), im))
    if hinges:                                    # clamp outliers: no hinge more than 20x the cloth's median stiffness
        cap = 20.0 * float(np.median([abs(h[3]) for h in hinges]))
        hinges = [(h[0], h[1], h[2], max(-cap, min(cap, h[3])), h[4]) for h in hinges]
    def bend_batches(items):
        rest = list(items); out = []
        while True:
            used, batch, left = set(), [], []
            for h in rest:
                if len(batch) < 4 and not (set(h[0]) & used): batch.append(h); used.update(h[0])
                else: left.append(h)
            if len(batch) < 4: return out, batch + left
            out.append(batch); rest = left
    bb_, bs_ = bend_batches(hinges)
    BT = m.type_named('hclBendStiffnessConstraintSetMx::Batch'); ST = m.type_named('hclBendStiffnessConstraintSetMx::Single')
    bl = []
    for bch in bb_:
        x = Struct(BT)
        for li, L in enumerate('ABCD'):
            x['weights' + L] = [float(h[1][li]) for h in bch]
            x['invMasses' + L] = [float(h[4][li]) for h in bch]
            x['particles' + L] = [h[0][li] for h in bch]
        x['bendStiffnesses'] = [h[3] for h in bch]; x['restCurvatures'] = [h[2] for h in bch]
        bl.append(x)
    sl_ = []
    for h in bs_:
        x = Struct(ST)
        for li, L in enumerate('ABCD'):
            x['weight' + L] = float(h[1][li]); x['invMass' + L] = float(h[4][li]); x['particle' + L] = h[0][li]
        x['bendStiffness'] = h[3]; x['restCurvature'] = h[2]
        sl_.append(x)
    bend.value['batches'] = bl; bend.value['singles'] = sl_ if sl_ else None
    g.n_hinges = len(hinges)
    for k, cs in enumerate((std, stretch, local, bend)): cs.value['constraintId']['value'] = k
    sim['staticConstraintSets'] = [std, stretch, local, bend]

    # ---------------- collidables: the cape's shapes for bones we have
    cape_names = g.spec['_template_skeleton']
    coll = sim['perInstanceCollidables'].item.elems
    ctm = sim['collidableTransformMap']
    keep_c, keep_ti, keep_off, keep_pinch = [], [], [], []
    skip = set(g.spec.get('collision_skip', []))     # bones whose colliders are left out (diagnostics / chest pieces)
    for k, c in enumerate(coll):
        bone = cape_names[ctm['transformIndices'][k]]
        if bone in t_index and bone not in skip:
            keep_c.append(c); keep_ti.append(t_index[bone]); keep_off.append(ctm['offsets'].item.elems[k])
            keep_pinch.append(sim['collidablePinchingDatas'].item.elems[k])
    grow = g.spec.get('collision_grow', {})          # per-bone capsule radius change (m): a thicker buffer
    for c, ti in zip(keep_c, keep_ti):
        sh = c.value['shape'].value
        if sh.type.name == 'hclCapsuleShape' and g.bones[ti] in grow: sh['radius'] = max(MIN_RADIUS, sh['radius'] + grow[g.bones[ti]])
    # extra short capsules on a bone (e.g. a kneecap): {bone: dict(start=-x, end=x, grow=m)} along the bone's x
    # axis, radius = that bone's own capsule radius + grow. Only the joint gets bigger; the limb keeps its size.
    from havok_model import Struct as _S
    for bone, ex in g.spec.get('collision_extra', {}).items():
        src = next(((c, ti, off, pin) for c, ti, off, pin in zip(keep_c, keep_ti, keep_off, keep_pinch)
                    if g.bones[ti] == bone and c.value['shape'].value.type.name == 'hclCapsuleShape'), None)
        if src is None: continue
        c0, ti, off, pin = src; col0 = c0.value; sh0 = col0['shape'].value
        sh = _S(sh0.type, sh0._raw); sh.update(sh0)
        a, e = ex.get('start', -0.05), ex.get('end', 0.05)
        sh['start'] = [a, sh0['start'][1], sh0['start'][2], 0.0]; sh['end'] = [e, sh0['end'][1], sh0['end'][2], 0.0]
        sh['dir'] = [1.0, 0.0, 0.0, 0.0]; sh['radius'] = sh0['radius'] + ex.get('grow', 0.02)
        sh['capLenSqrdInv'] = 1.0 / ((e - a) ** 2)
        col = _S(col0.type, col0._raw); col.update(col0); col['shape'] = sh; col['name'] = 'Collidable_' + bone + '_cap'
        keep_c.append(col); keep_ti.append(ti); keep_off.append(off); keep_pinch.append(pin)
    # chest (body fit): two mirrored capsules in front of the chest for models with a larger chest (the stock chest shape
    # is a convex hull that cannot be resized). Off unless collision.chest is given.
    chest = g.spec.get('collision_chest')
    if chest and 'chest' in t_index:
        tmpl = next(((c, ti, off, pin) for c, ti, off, pin in zip(keep_c, keep_ti, keep_off, keep_pinch)
                     if g.bones[ti] == 'spine1' and (c.value if isinstance(c, Ref) else c)['shape'].value.type.name == 'hclCapsuleShape'), None)
        if tmpl is not None:
            c0, _, off0, pin0 = tmpl; col0 = c0.value if isinstance(c0, Ref) else c0; sh0 = col0['shape'].value
            Wc = g.world[g.bone_nodes[t_index['chest']]]
            base = Wc[3][:3] if abs(Wc[3][3]) == 1 else Wc[:3, 3]
            r = max(MIN_RADIUS, 0.07 + float(chest.get('grow', 0.0))); half = 0.02 * float(chest.get('length', 1.0))
            out_, fwd_, up_ = (float(x) for x in chest.get('offset', [0.0, 0.0, 0.0]))     # [outward, forward, up]
            ident = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]
            for side in (-1.0, 1.0):
                centre = np.array([side * (0.075 + out_), base[1] + 0.11 + fwd_, base[2] - 0.06 + up_])
                pts = [centre + [0, 0, half], centre - [0, 0, half]]
                loc = [(np.append(p_, 1.0) @ np.linalg.inv(Wc))[:3] for p_ in pts]   # chest bone space (offset = identity)
                sh = _S(sh0.type, sh0._raw); sh.update(sh0)
                sh['start'] = [float(loc[0][0]), float(loc[0][1]), float(loc[0][2]), 0.0]
                sh['end'] = [float(loc[1][0]), float(loc[1][1]), float(loc[1][2]), 0.0]
                L2 = float(((loc[1] - loc[0]) ** 2).sum()); sh['capLenSqrdInv'] = 1.0 / L2 if L2 > 1e-12 else 0.0
                sh['radius'] = r
                col = _S(col0.type, col0._raw); col.update(col0); col['shape'] = sh
                col['name'] = 'Collidable_chest_' + ('l' if side < 0 else 'r') + '_cap'
                keep_c.append(col); keep_ti.append(t_index['chest']); keep_off.append(ident); keep_pinch.append(pin0)
    # body fit (2026-10-22): length scale and a move in BODY directions (+X right, +Y forward, +Z up, at rest) per bone,
    # for models shaped unlike the standard diver. A move applies to every capsule of the bone (kneecaps too); length only
    # to the body capsule. Collidable local -> world (row vectors): p_world = p_local @ Off @ W_bone_rest.
    lengths = g.spec.get('collision_length', {}); moves = g.spec.get('collision_offset', {})
    for c, ti, off in zip(keep_c, keep_ti, keep_off):
        bone = g.bones[ti]
        if bone not in lengths and bone not in moves: continue
        col = c.value if isinstance(c, Ref) else c; sh = col['shape']; sh = sh.value if isinstance(sh, Ref) else sh
        if sh.type.name != 'hclCapsuleShape': continue
        a = np.array(sh['start'][:3], dtype=np.float64); e = np.array(sh['end'][:3], dtype=np.float64)
        name = col['name'] if isinstance(col['name'], str) else ''
        if bone in lengths and not name.endswith('_cap'):
            mid = (a + e) / 2; k = float(lengths[bone]); a = mid + (a - mid) * k; e = mid + (e - mid) * k
        if bone in moves:
            R = (np.array(list(off), dtype=np.float64).reshape(4, 4) @ g.world[g.bone_nodes[ti]])[:3, :3]
            d = np.array(moves[bone], dtype=np.float64) @ np.linalg.inv(R)
            a = a + d; e = e + d
        sh['start'] = [float(a[0]), float(a[1]), float(a[2]), 0.0]; sh['end'] = [float(e[0]), float(e[1]), float(e[2]), 0.0]
        L2 = float(((e - a) ** 2).sum()); sh['capLenSqrdInv'] = 1.0 / L2 if L2 > 1e-12 else 0.0
    # auto fit (2026-10-24): cloth that STARTS deep inside a collider gets shoved out every frame (jitter, flying
    # vertices: a tester (SA-7 cloak)'s cloak had ~900 points inside the lower-back capsule). A few points just inside are normal (a skirt
    # resting on the hips: our tested B-01 skirt has ~25 inside the thighs and is fine), so only a collider with a real
    # share of the cloth truly inside it (>= 50 points and >= 3% of the free points) shrinks, to clear them, never below
    # 70% of its size. collision.auto_fit = false turns it off.
    g.auto_fit = []
    if g.spec.get('collision_auto_fit', True):
        freeP = np.array([g.pp[i] for i in range(len(g.pp)) if i not in fixed]) if len(g.pp) else np.zeros((0, 3))
        need = max(50, int(0.03 * len(freeP)))
        for c, ti, off in zip(keep_c, keep_ti, keep_off):
            col = c.value if isinstance(c, Ref) else c; sh = col['shape']; sh = sh.value if isinstance(sh, Ref) else sh
            if sh.type.name != 'hclCapsuleShape' or not len(freeP): continue
            Mw = np.array(list(off), dtype=np.float64).reshape(4, 4) @ g.world[g.bone_nodes[ti]]
            A = (np.append(sh['start'][:3], 1.0) @ Mw)[:3]; B = (np.append(sh['end'][:3], 1.0) @ Mw)[:3]
            u = B - A; L2 = max(float(u @ u), 1e-12); tt = np.clip((freeP - A) @ u / L2, 0, 1)
            d = np.linalg.norm(freeP - (A + tt[:, None] * u), axis=1); r0 = float(sh['radius'])
            inside = d < r0 - 0.005
            if int(inside.sum()) < need: continue
            r1 = max(MIN_RADIUS, r0 * 0.7, float(d[inside].min()))
            sh['radius'] = min(r0, r1)
            left = int((d < sh['radius'] - 0.005).sum())
            g.auto_fit.append((g.bones[ti], r0, float(sh['radius']), int(inside.sum()), left))
    sim['perInstanceCollidables'] = keep_c
    ctm['transformIndices'] = keep_ti; ctm['offsets'] = keep_off
    sim['collidablePinchingDatas'] = keep_pinch
    tmd = sim['transferMotionData']; tmd['transformIndex'] = hips
    for k, v in g.spec.get('transfer_motion', {}).items(): tmd[k] = v      # carry cloth with fast hip moves
    g.collidable_bones = [g.bones[t] for t in keep_ti]

    # ---------------- bone planes (Arrowhead's anti-clipping tool on the cape: 457 planes on its bone). Each loose
    # point near a leg gets ONE plane fixed to the nearest leg capsule (thigh or shin), tangent to the capsule surface
    # on the side facing the point: the point must stay on that side (verified on the cape: value = n.p + d >= 0 at
    # rest, p in bone space). The plane moves with the bone: a raised thigh keeps the cloth ON TOP of it, a shin keeps
    # the cloth in FRONT of it, so the leg can never end up on the wrong side of the fabric.
    bp_spec = g.spec.get('bone_planes')
    g.n_bone_planes = 0
    if bp_spec:
        reach = bp_spec.get('reach', 0.15); margin = bp_spec.get('margin', 0.0)
        caps = {}
        for c, ti in zip(keep_c, keep_ti):
            sh = (c.value if isinstance(c, Ref) else c)['shape']; sh = sh.value if isinstance(sh, Ref) else sh
            if sh.type.name == 'hclCapsuleShape' and g.bones[ti] in bp_spec.get('bones', ['l_thigh', 'r_thigh', 'l_knee', 'r_knee']):
                if g.bones[ti] not in caps:          # first (body) capsule of that bone, not an extra one
                    caps[g.bones[ti]] = (ti, np.array(sh['start'][:3]), np.array(sh['end'][:3]), sh['radius'])
        BPT = m.type_named('hclBonePlanesConstraintSet::BonePlane')
        planes = []
        for i in range(NP):
            if i in fixed: continue
            best = None
            for bone, (ti, a, b_, r) in caps.items():
                W = g.world[g.bone_nodes[ti]]
                pb = (np.append(g.pp[i], 1.0) @ np.linalg.inv(W))[:3]          # rest position in bone space
                ab = b_ - a; tt = np.clip(np.dot(pb - a, ab) / max(np.dot(ab, ab), 1e-12), 0, 1); c = a + tt * ab
                dist = np.linalg.norm(pb - c)
                if dist - r <= reach and (best is None or dist - r < best[0]): best = (dist - r, ti, pb, c, r, dist)
            if best is None: continue
            _, ti, pb, c, r, dist = best
            if dist < 1e-6: continue
            u = (pb - c) / dist
            rr = min(r + margin, dist - 0.002)        # never start violated: at rest the point is on the allowed side
            x = Struct(BPT); x['planeEquationBone'] = [float(u[0]), float(u[1]), float(u[2]), float(-(np.dot(u, c)) - rr)]
            x['particleIndex'] = i; x['transformIndex'] = ti; x['stiffness'] = float(bp_spec.get('stiffness', 1.0))
            planes.append(x)
        planes_set = sets[2]
        assert planes_set.value.type.name == 'hclBonePlanesConstraintSet'
        planes_set.value['bonePlanes'] = planes; planes_set.value['transformSetIndex'] = 0
        planes_set.value['constraintId']['value'] = 4
        sim['staticConstraintSets'] = [std, stretch, local, bend, planes_set]
        g.n_bone_planes = len(planes)

    # ---------------- operators
    o_disp, o_simskin, o_move, o_simulate, o_mesh, o_conv = [x.value for x in keep_ops]
    for k, o in enumerate((o_disp, o_simskin, o_move, o_simulate, o_mesh, o_conv)):
        o['operatorID'] = k if k < 5 else 5
        remap_used_buffers(o['usedBuffers'])
    # display skin: every display vertex on its mesh bones
    disp_bones = sorted({t for v in range(ND) for t, w in g.skin[v]})
    def skin_records(points, normals, skins, subset):
        local = {t: k for k, t in enumerate(subset)}
        recs = []
        for v, (p, n, sk) in enumerate(zip(points, normals, skins)):
            ws = [w for _, w in sk]; tot = sum(ws)
            q = [int(round(255 * w / tot)) for w in ws]; q[-1] += 255 - sum(q)
            recs.append(dict(vertex=v, bones=[local[t] for t, _ in sk], weights=q, pos=tuple(p), normal=tuple(n)))
        return recs
    def set_skin_op(o, recs, subset, out_buffer):
        o['transformSubset'] = subset
        o['boneFromSkinMeshTransforms'] = [[float(x) for x in g.inv_bind(t).ravel()] for t in subset]
        dfm, pns = deformer_build(recs, m, o['objectSpaceDeformer'])
        dfm['partialWrite'] = False
        o['objectSpaceDeformer'] = dfm; o['localPNs'] = pns; o['localUnpackedPNs'] = None
        o['outputBufferIndex'] = out_buffer
    set_skin_op(o_disp, skin_records(g.P, g.N, g.skin, disp_bones), disp_bones, 0)
    o_disp['name'] = 'Display Skin Op'
    # sim skin: every particle on its vertex's bones (pinned ones follow exactly)
    p_skin = [None] * NP; p_norm = [None] * NP
    for v, p in g.vert_particle.items():
        if p_skin[p] is None: p_skin[p] = g.skin[v]; p_norm[p] = g.N[v]
    # orient every reference normal AWAY from the body axis (double-sided cloth: the first vertex found may be the
    # inner layer). The leash's normal limit (part 'inward') measures along this normal.
    hx, hy = g.world[g.bone_nodes[t_index['hips']]][3][:2] if abs(g.world[g.bone_nodes[t_index['hips']]][3][3]) == 1 else (0.0, 0.0)
    for p in range(NP):
        out = np.array([g.pp[p, 0] - hx, g.pp[p, 1] - hy, 0.0])
        if np.dot(p_norm[p], out) < 0: p_norm[p] = -np.asarray(p_norm[p])
    # thigh follow (ring parts): the leash target of the lower skirt blends from hips (waist) to the thigh on
    # its side, so a raised knee pulls the fabric over it instead of through it
    follow = g.spec.get('thigh_follow')
    if follow:
        ti = {b: k for k, b in enumerate(g.bones)}
        for isl, st in enumerate(g.part_settings):
            if st.get('measured_angle') is not None: continue          # strips keep their own skinning
            idx = [i for i in range(NP) if g.island[i] == isl]
            ztop = max(g.pp[i, 2] for i in idx); zbot = min(g.pp[i, 2] for i in idx)
            rmax = max(np.hypot(g.pp[i, 0], g.pp[i, 1]) for i in idx)
            for i in idx:
                if i in fixed: continue  # author pins keep their original bone weights (thebf333, 2026-10-23)
                f = (ztop - g.pp[i, 2]) / max(ztop - zbot, 1e-6)
                wt = follow * f
                side = np.clip(g.pp[i, 0] / rmax, -1, 1)              # -1 = left (-X), +1 = right
                # only the SIDES follow their own thigh; the centre front/back stay on the hips. (Averaging both
                # thighs at the centre pulled the leash target between split legs: crotch bunching, 2026-10-18.)
                if g.spec.get('front_follow') and g.pp[i, 1] > 0:      # front half: follow the thigh on its side
                    k = 0.5 + 0.5 * abs(side)                          # even the centre front picks one side (no averaging)
                    wl, wr = (wt * k, 0.0) if side <= 0 else (0.0, wt * k)
                else:
                    wl, wr = wt * max(0.0, -side), wt * max(0.0, side)
                sk = [(ti['hips'], 1 - wt)] + [(t, w) for t, w in ((ti['l_thigh'], wl), (ti['r_thigh'], wr)) if w > 0.01]
                p_skin[i] = sorted(sk, key=lambda x: x[1])
    for i, (t, w) in g.wind_weights().items():                 # wind: blend toward the cape bone
        sk = [(tt, ww * (1 - w)) for tt, ww in p_skin[i]] + [(t, w)]
        acc = {}
        for tt, ww in sk: acc[tt] = acc.get(tt, 0) + ww
        p_skin[i] = sorted(acc.items(), key=lambda x: x[1])[-4:]
    g.n_wind = len(g.wind_weights())
    sim_bones = sorted({t for sk in p_skin for t, _ in sk})
    set_skin_op(o_simskin, skin_records(g.pp, p_norm, p_skin, sim_bones), sim_bones, 1)
    # move fixed particles from the skinned scratch buffer
    VP = m.type_named('hclMoveParticlesOperator::VertexParticlePair')
    pairs = []
    for f in sorted(fixed):
        x = Struct(VP); x['vertexIndex'] = f; x['particleIndex'] = f; pairs.append(x)
    o_move['vertexParticlePairs'] = pairs; o_move['simClothIndex'] = 0; o_move['refBufferIdx'] = 1
    # simulate
    cfg = o_simulate['simulateOpConfigs'][0]
    cfg['constraintExecution'] = ([4] if g.n_bone_planes else []) + [2] + [0] * S['link_passes'] + [3, 1, -1]
    # cape order: (bone planes), leash, links, bend, stretch
    cfg['subSteps'] = S['substeps']; cfg['numberOfSolveIterations'] = S['iterations']
    o_simulate['simulateOpConfigs'] = [o_simulate['simulateOpConfigs'].item.elems[0]]
    o_simulate['simClothIndex'] = 0
    # mesh-mesh deform: each cloth display vertex rides on one sheet triangle that uses its particle
    tri_of_particle = {}
    for k, t in enumerate(g.ptris):
        for p in t: tri_of_particle.setdefault(int(p), k)
    def tri_frame(k):
        A, B, C = g.pp[g.ptris[k]]; o = (A + B + C) / 3; n = np.cross(B - A, C - A); n /= np.linalg.norm(n)
        M = np.eye(4); M[0, :3] = A - o; M[1, :3] = B - o; M[2, :3] = n; M[3, :3] = o
        return M
    Tinv = [np.linalg.inv(tri_frame(k)) for k in range(len(g.ptris))]
    recs = []
    for v in g.cloth_verts:     # Havok stores the MESH-space position/normal; it applies triangleFromMesh itself
        k = tri_of_particle[g.vert_particle[v]]       # (verified on the cape: stored == display rest, error 0)
        recs.append(dict(vertex=v, bones=[k], weights=[255], pos=tuple(g.P[v]), normal=tuple(g.N[v])))
    dfm, pns = deformer_build(recs, m, o_mesh['objectSpaceDeformer'])
    dfm['partialWrite'] = True
    o_mesh['objectSpaceDeformer'] = dfm; o_mesh['localPNs'] = pns; o_mesh['localUnpackedPNs'] = None
    o_mesh['triangleFromMeshTransforms'] = [[float(x) for x in t.ravel()] for t in Tinv]
    o_mesh['inputTrianglesSubset'] = None; o_mesh['inputBufferIdx'] = 2; o_mesh['outputBufferIdx'] = 0
    o_conv['userBufferIndex'] = 0; o_conv['shadowBufferIndex'] = 4
    if g.spec.get('oct_normals'):                # character shaders read NORMAL as HD2's packed octahedral normal; the
        ci = o_conv['conversionInfo']             # cloth can only write plain normals -> write POSITIONS only and keep
        sc = ci['slotConversions'][0]             # the packed rest normals from the render copy
        sc['elements'] = [0, 0, 0, 0]; sc['numElements'] = 1; ci['numElementsConverted'] = 1
    # transform usage bits
    coll_t = sorted(set(keep_ti) | {hips})
    set_trackers(o_disp['usedTransformSets'], disp_bones)
    set_trackers(o_simskin['usedTransformSets'], sim_bones)
    set_trackers(o_simulate['usedTransformSets'], coll_t, [])
    # ---------------- states and transitions
    s_sim, s_off = [x.value for x in keep_states]
    s_sim['operators'] = [0, 1, 2, 3, 4, 5]; s_off['operators'] = [0, 5]
    if g.spec.get('debug_no_mesh_deform'):          # diagnostic: strips stay rigid (display skin only)
        s_sim['operators'] = [0, 1, 2, 3, 5]
        dg = s_sim['dependencyGraph']
        dg['branches'][2]['stateOperatorIndices'] = [4]
        dg['children'] = [[4], [2], [3], [4], None]; dg['parents'] = [None, None, [1], [2], [0, 3]]
    remap_used_buffers(s_sim['usedBuffers']); remap_used_buffers(s_off['usedBuffers'])
    set_trackers(s_sim['usedTransformSets'], sorted(set(disp_bones) | set(sim_bones) | set(coll_t)), [])
    set_trackers(s_off['usedTransformSets'], disp_bones)
    s_sim['usedSimCloths'] = [0]
    for tr in keep_trans:
        t = tr.value
        t['stateIds'] = [0 if i == 0 else 1 for i in t['stateIds']]
        for std_ in t['stateTransitionData'].item.elems:
            std_['simClothTransitionData'] = [std_['simClothTransitionData'].item.elems[0]]
        t['simClothTransitionConstraints'] = [None]
    return d


# ======================================================================== Stingray tail block
def build_tail(g, template_tail):
    """The engine's render copy of the display mesh, bone list and bind matrices (layout as in the cape)."""
    T = len(g.bones); ND = g.nv
    t = bytearray(template_tail[:0x310])
    # mesh list
    struct.pack_into('<I', t, 0x38, h32(g.spec['mesh_name']))
    struct.pack_into('<I', t, 0xa0, ND)
    struct.pack_into('<I', t, 0x134, len(g.draw_tris) * 3)
    # vertex layout: (format, type | index << 16) pairs from 0xa4, element count at 0x124, stride at 0x80.
    # Armour and Illuminate vertex shaders also need TEXCOORD15 (one value); the cape shader does not. Option
    # 'texcoord15' adds it (half2, 4 bytes, zero) so non-cape shaders find every input they ask for.
    stride = 0x3c
    if g.spec.get('no_skin_elements'):          # drop BLENDWEIGHTS (7) + BLENDINDICES (6): the cloth already moved the
        n_el = struct.unpack_from('<I', t, 0x124)[0]   # vertices; a skinned character shader would move them AGAIN
        pairs = [struct.unpack_from('<II', t, 0xa4 + 8 * i) for i in range(n_el)]
        keep = [pr for pr in pairs if (pr[1] & 0xffff) not in (6, 7)]
        for i in range(n_el): struct.pack_into('<II', t, 0xa4 + 8 * i, 0, 0)
        for i, pr in enumerate(keep): struct.pack_into('<II', t, 0xa4 + 8 * i, *pr)
        struct.pack_into('<I', t, 0x124, len(keep)); stride -= 12
    if g.spec.get('texcoord15'):
        n_el = struct.unpack_from('<I', t, 0x124)[0]
        struct.pack_into('<II', t, 0xa4 + 8 * n_el, 0x80000410, 0x000F0004)
        struct.pack_into('<I', t, 0x124, n_el + 1)
        stride += 4
    struct.pack_into('<I', t, 0x80, stride)
    # transform set
    struct.pack_into('<II', t, 0x144, h32('skeleton'), 1); struct.pack_into('<I', t, 0x14c, T)
    # bulk data
    # render_root_skin: the render copy already holds positions relative to the unit root (measured in game). Character
    # shaders (armour/Illuminate) skin them again; skinning everything 100% to ROOT makes that second move exactly right.
    root_pal = None
    if g.spec.get('render_root_skin'):
        root_node = g.node_hash.index(h32('root'))
        root_pal = next((k for k in range(len(g.pal_remap)) if g.pal_real[g.pal_remap[k]] == root_node), None)
        if root_pal is None: raise SystemExit("render_root_skin: 'root' is not in the mesh's bone palette (weight one vertex to root)")
    # tangents along the UVs (contributed by an author, 2026-10-23): only with a normal map, the one thing that reads
    # them; without one the build stays as it was (generic tangent around world Z)
    uv_tan = bool(g.spec.get('uv_tangents'))
    uv0 = np.asarray(g.UV[0], dtype=float)
    tan_sum = np.zeros_like(g.P); bitan_sum = np.zeros_like(g.P)
    for ia, ib, ic in (g.tris if uv_tan else []):
        e1, e2 = g.P[ib] - g.P[ia], g.P[ic] - g.P[ia]
        q1, q2 = uv0[ib] - uv0[ia], uv0[ic] - uv0[ia]
        det = q1[0] * q2[1] - q1[1] * q2[0]
        if abs(det) < 1e-12: continue
        tg_uv = (e1 * q2[1] - e2 * q1[1]) / det
        bt_uv = (e2 * q1[0] - e1 * q2[0]) / det
        area = np.linalg.norm(np.cross(e1, e2))
        for vi in (ia, ib, ic):
            tan_sum[vi] += tg_uv * area; bitan_sum[vi] += bt_uv * area
    bulk = bytearray(b'abcdefghijklmnop')
    vstart = len(bulk)
    for v in range(ND):
        p = g.P[v]; n = g.N[v]
        if not uv_tan:
            tg = np.cross(n, [0, 0, 1.0]); tg = tg / (np.linalg.norm(tg) or 1); bt = np.cross(n, tg)
        else:
          nn_basis = n / (np.linalg.norm(n) or 1.)
          tg = tan_sum[v] - nn_basis * np.dot(nn_basis, tan_sum[v])
          if np.linalg.norm(tg) < 1e-10: tg = np.cross(nn_basis, [0., 0., 1.])
          if np.linalg.norm(tg) < 1e-10: tg = np.cross(nn_basis, [0., 1., 0.])
          tg /= np.linalg.norm(tg)
          bt = np.cross(nn_basis, tg)
          if np.dot(bt, bitan_sum[v]) < 0: bt = -bt
        uv = [g.UV[k][v] if k < len(g.UV) else (0, 0) for k in range(3)]
        # the renderer still GPU-skins this copy with the mesh's own bone palette: keep the mesh's original
        # palette indices and weights here (NOT cloth transform indices; out-of-palette indices hid the mesh)
        ids = list(g.raw_bone_idx[v][:4]) + [0] * (4 - len(g.raw_bone_idx[v][:4])); ws = list(g.raw_w[v][:4]) + [0] * (4 - len(g.raw_w[v][:4]))
        if root_pal is not None: ids, ws = [root_pal, 0, 0, 0], [1.0, 0.0, 0.0, 0.0]
        bulk += struct.pack('<3f', *p)
        if g.spec.get('oct_normals'):            # HD2 armour normal: octahedral (x, y) in 0..1 (shader unpacks xy*2-1)
            nn = np.asarray(n, float) / (np.linalg.norm(n) or 1.0); l1 = abs(nn[0]) + abs(nn[1]) + abs(nn[2])
            ox, oy = nn[0] / l1, nn[1] / l1
            if nn[2] < 0: ox, oy = (1 - abs(oy)) * (1 if ox >= 0 else -1), (1 - abs(ox)) * (1 if oy >= 0 else -1)
            bulk += struct.pack('<4H', half((ox + 1) / 2), half((oy + 1) / 2), half(0.0), half(0.0))
        else:
            bulk += struct.pack('<4H', half(n[0]), half(n[1]), half(n[2]), half(1.0))
        bulk += struct.pack('<4H', half(bt[0]), half(bt[1]), half(bt[2]), half(1.0))   # channel 3 (binormal) at 20
        bulk += struct.pack('<4H', half(tg[0]), half(tg[1]), half(tg[2]), half(1.0))   # channel 2 (tangent) at 28
        for u in uv: bulk += struct.pack('<2H', half(u[0]), half(u[1]))
        if not g.spec.get('no_skin_elements'):
            bulk += struct.pack('<4H', *[half(w) for w in ws])
            bulk += bytes(ids)
        if g.spec.get('texcoord15'): bulk += b'\0\0\0\0'
    while len(bulk) % 8: bulk.append(0)
    istart = len(bulk)
    for a, b, c in g.draw_tris: bulk += struct.pack('<3H', a, b, c)
    while len(bulk) % 8: bulk.append(0)
    mA = len(bulk)
    for k in range(T): bulk += struct.pack('<16f', *g.bind(k).ravel())
    while len(bulk) % 8: bulk.append(0)
    mB = len(bulk)
    for k in range(T): bulk += struct.pack('<16f', *g.inv_bind(k).T.ravel())
    # data table (entries of 6 u32 at 0x164: vertex data, indices, matrices A, matrices B)
    struct.pack_into('<3I', t, 0x17c, stride, ND, vstart)
    struct.pack_into('<3I', t, 0x194, 2, len(g.draw_tris) * 3, istart)
    struct.pack_into('<3I', t, 0x1ac, 0x40, T, mA)
    struct.pack_into('<3I', t, 0x1c4, 0x40, T, mB)
    # bone list: count, then (index, hash) table: [root 0] + transform nodes
    bl = bytearray(struct.pack('<IIII', 1, h32('skeleton'), 0x1ec, T + 1))
    bl += struct.pack(f'<{T + 1}I', 0, *g.bone_nodes)
    bl += struct.pack(f'<{T + 1}I', 0, *[g.node_hash[n] for n in g.bone_nodes])
    t = t[:0x1e0] + bl
    while len(t) % 16: t.append(0)
    # section offsets: the bone-list section ends where the bulk data begins
    bulk_off = len(t)
    struct.pack_into('<I', t, 0x14, bulk_off)
    struct.pack_into('<I', t, 0x1e8, 0x1ec)
    return bytes(t + bulk), bulk_off


# ======================================================================== resource
def build_resource(g, unit_id):
    b = TEMPLATE_BYTES or open(TEMPLATE, 'rb').read()
    spans = spans_of(b)
    m4 = Model.load(b, 4)
    m1 = Model.load(b, 1)
    g.spec['_template_skeleton'] = [m1.text(x['name']) for x in m1.root['skeletons'][0]['bones']]
    build_clothdata(m4, g)
    g.pruned_items = m4.prune()                 # template leftovers nothing points at any more
    cloth = m4.save()
    head = bytearray(b[:spans[0][0]])
    tail_off = struct.unpack_from('<I', b, 0x90)[0]
    tail, _ = build_tail(g, b[tail_off:])
    # layout: header, tagfiles 0-3 as in the template, clothdata, tail
    out = bytearray(head)
    new_spans = []
    scene = None
    if g.spec.get('strip_scene'):               # tagfile 0 = the cape's hkxScene (authoring source, 6.2 MB): keep a valid
        m0 = Model.load(b, 0); r0 = m0.root      # but EMPTY scene object (game use unconfirmed: test before default)
        for k in ('rootNode', 'selectionSets', 'meshes', 'materials', 'externalTextures', 'skinBindings'): r0[k] = None
        m0.prune(); scene = m0.save()
    for k_, (st, sz) in enumerate(spans[:4]):
        while len(out) % 16: out.append(0)
        data = scene if (k_ == 0 and scene is not None) else b[st:st + sz]
        new_spans.append((len(out), len(data))); out += data
    while len(out) % 16: out.append(0)
    cd_off = len(out); out += cloth
    while len(out) % 16: out.append(0)
    t_off = len(out); out += tail
    for k, (st, sz) in enumerate(new_spans): struct.pack_into('<II', out, 0x50 + 16 * k, st, sz)
    struct.pack_into('<I', out, 0x90, t_off)
    struct.pack_into('<III', out, 0x110, h32(g.spec['cloth_name']), cd_off, len(cloth))
    struct.pack_into('<Q', out, 8, unit_id); struct.pack_into('<Q', out, 64, unit_id)
    struct.pack_into('<I', out, 16, len(out)); struct.pack_into('<I', out, 76, len(out) - 8)
    return bytes(out)


def validate(blob, g):
    m = Model.load(blob, 4); d = m.root; sim = d['simClothDatas'][0]
    NP, ND, T = len(g.pp), g.nv, len(g.bones)
    errs = []
    if m.text(d['bufferDefinitions'][0]['name']) != g.spec['mesh_name']: errs.append('display buffer name')
    if d['bufferDefinitions'][0]['numVertices'] != ND: errs.append('display vertex count')
    if len(sim['particleDatas']) != NP: errs.append('particle count')
    if max(sim['triangleIndices']) >= NP: errs.append('triangle index range')
    for o in d['operators']:
        if 'transformSubset' in o.keys() and max(o['transformSubset']) >= T: errs.append(f'{m.text(o["name"])} transform range')
    ctm = sim['collidableTransformMap']
    if max(ctm['transformIndices']) >= T: errs.append('collidable transform range')
    t_off = struct.unpack_from('<I', blob, 0x90)[0]
    if struct.unpack_from('<I', blob, t_off + 0x38)[0] != h32(g.spec['mesh_name']): errs.append('tail mesh hash')
    return errs


def testrig_spec():
    return dict(mesh_name='g_legs_hips_female', cloth_name='hd2dress_testrig', cloth_material=1,
                bones=['skeleton', 'root', 'hips', 'r_thigh', 'r_knee', 'r_foot', 'l_thigh', 'l_knee', 'l_foot', 'spine1'],
                groups=[dict(angle=a, mass=[0.003, 0.006, 0.003, 0.010][i % 4], stiffness=[1.0, 0.6, 0.3, 1.0][i % 4],
                             leash=[0.05, 0.15, 0.30, 0.60][i % 4], stretch=0.05, bend=0.8) for i, a in enumerate(range(0, 360, 30))],
                sim=dict(gravity=9.81, damping=0.7, substeps=1, iterations=1, link_passes=1, radius=0.02, friction=0.5))


if __name__ == '__main__':
    units = json.load(open(sys.argv[1])); uid = sys.argv[2]
    spec = json.load(open(sys.argv[3])) if not sys.argv[3].startswith('testrig') else testrig_spec()
    if sys.argv[3] == 'testrig-nodeform': spec['debug_no_mesh_deform'] = True
    if sys.argv[3] == 'testrig-native': spec['bones'] = ['skeleton', 'root', 'hips', 'r_thigh', 'l_thigh']   # only bones the hip unit has
    if sys.argv[3] == 'testrig-full':          # connected skirt + shoulder strips; upper-body bones added to the hip unit
        spec['bones'] = ['skeleton', 'root', 'hips', 'r_thigh', 'r_knee', 'r_foot', 'l_thigh', 'l_knee', 'l_foot', 'spine1',
                         'spine2', 'chest', 'neck', 'head', 'l_clavicle', 'r_clavicle', 'l_shoulder', 'r_shoulder', 'l_elbow', 'r_elbow']
        spec['ring_part'] = dict(angle=None, mass=0.004, stiffness=1.0, leash=0.30, stretch=0.05, bend=0.8)
        spec['collision_extra'] = {}   # kneecap capsules (+3 cm) made it WORSE: pushed further = stretched more = gaps
        # e.g. {'l_knee': dict(start=-0.05, end=0.05, grow=0.03), 'r_knee': ...}
        spec['collision_grow'] = {}            # body-sized capsules: the cloth lies flat on the body (user preference;
                                               # +2.5..5 cm read as "tubes around the legs"). Tunable per bone.
        spec['sim']['radius'] = 0.02; spec['sim']['friction'] = 0.97   # grippy like the cape: kneeling no longer slides it up the leg
        spec['sim']['substeps'] = 5; spec['sim']['iterations'] = 2; spec['sim']['link_passes'] = 3
        # substeps are SAFE when baked (stock capes with 3 substeps ran clean, w-NaN harmless). The earlier
        # blow-up came from a LIVE leash edit, not from substeps (2026-10-18).
        spec['ring_part'].update(leash=0.55, stretch=0.60, stiffness=1.0)    # 2026-10-18: leash measured in game (thumbs-up kneel): 0.40 and 0.45 let the knee through, 0.55 holds
        # (the leash pulls points toward their skinned spot, which sits inside the bent leg). Earlier note: loosen the leash (0.40)
        # and the stretch limit (0.60) so neither can drag the cloth back through the knee. 10 substeps = -20 fps
        # and no gain, so the fall-through is not speed.   # easy to pull (long stretch limit) but
        # neighbours keep their spacing (stiffness 1.0, was 0.7): soft neighbour links spread the points apart under
        # the knee and the knee slipped through the gaps (links are 6-8 cm, particles only 2 cm radius)
        spec['front_follow'] = True
        spec['thigh_follow'] = 0.6
        spec['transfer_motion'] = dict(minTranslationSpeed=0.5, maxTranslationSpeed=2.0, minRotationSpeed=90.0, maxRotationSpeed=360.0)
    if len(sys.argv) > 5: spec['cloth_positions'] = json.load(open(sys.argv[5]))['positions']
    if uid == '0x387a158d04848f4': spec['mesh_name'] = spec['mesh_name'].replace('female', 'male')
    g = Garment(units[uid], spec)
    print(f'particles {len(g.pp)}, pinned {len(g.fixed)}, sheet triangles {len(g.ptris)}, islands {g.n_islands}, display vertices {g.nv}, cloth vertices {len(g.cloth_verts)}')
    for k, s in enumerate(g.part_settings): print(f'  part {k}: ' + ('ring (skirt)' if s['measured_angle'] is None else f'at {s["measured_angle"]:.0f} deg') + f': mass {s["mass"]}, stiffness {s["stiffness"]}, leash {s["leash"]}')
    blob = build_resource(g, int(uid, 16))
    errs = validate(blob, g)
    print('collidables on', g.collidable_bones)
    if errs: raise SystemExit('VALIDATION FAILED: ' + ', '.join(errs))
    open(sys.argv[4], 'wb').write(blob); print('wrote', sys.argv[4], len(blob), 'bytes, validation OK')
