"""Motion preview: the Helldiver's own animations (from the game files) play in the viewport, the armour follows them,
and the cloth pieces are simulated live with the same rules the build writes into the game cloth (links, stretch limit
to the pins, leash to the skinned shape, bending, gravity, damping, wind, the stock cape's body capsules, kneecaps,
friction, floor gap). An approximation of the game's Havok solver, close enough to judge the feel.

Nothing of the author's data is changed: the armour is skinned here from the Helldiver's pose (not through the
author's rig), and the result is drawn on a separate preview object while the original is hidden."""
import bpy, os, json, math, time, mathutils
import numpy as np

CACHE = os.path.join(os.path.expanduser('~'), '.cache', 'hd2-dress', 'viewer')
AVATAR = 'hd2dress_avatar'
COLL = 'HD2 Dress preview'
ANIMS = [('JOG', 'Jog', 3.5), ('RUN', 'Run', 5.0), ('CROUCH', 'Crouch walk', 1.5), ('STAND', 'Stand', 0.0),
         ('DIVE', 'Dive', 0.0), ('CRAWL', 'Prone crawl', 0.0), ('GETUP', 'Get up', 0.0), ('HIT', 'Hit reaction', 0.0)]
SPEED = {k: s for k, _, s in ANIMS}
WIND_SHIP = 8.4            # m/s, the Super Destroyer's breeze (measured live, 2026-10-21)
STATE = {'sims': {}, 'prev': None, 't': 0.0, 'hidden': [], 'ms': 0.0}


def assets_ready(): return os.path.exists(os.path.join(CACHE, 'helldiver.blend')) and os.path.exists(os.path.join(CACHE, 'colliders.json'))


def avatar(): return bpy.data.objects.get(AVATAR)


def collection(scene):
    c = bpy.data.collections.get(COLL)
    if c is None:
        c = bpy.data.collections.new(COLL); scene.collection.children.link(c)
    return c


def load_avatar(scene):
    """Append the cached Helldiver skeleton and animations (made once by tools/viewer_assets.py)."""
    av = avatar()
    if av is not None and all(bpy.data.actions.get('hd2dress_' + k) for k, _, _ in ANIMS): return av
    path = os.path.join(CACHE, 'helldiver.blend')
    body = json.load(open(os.path.join(CACHE, 'body.json'))) if os.path.exists(os.path.join(CACHE, 'body.json')) else []
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = ([AVATAR] if av is None else []) + [b for b in body if not bpy.data.objects.get(b)]
        dst.actions = [a for a in src.actions if a.startswith('hd2dress_') and not bpy.data.actions.get(a)]
    for a in dst.actions:
        if a: a.use_fake_user = True
    new = [o for o in dst.objects if o]
    for o in new:
        collection(scene).objects.link(o); o.hide_select = True
    if av is None: av = bpy.data.objects.get(AVATAR)
    for o in new:
        if o.type == 'MESH':
            o.display_type = 'SOLID'; o.color = (0.35, 0.37, 0.42, 1.0)
            for md in o.modifiers:
                if md.type == 'ARMATURE': md.object = av
    if av.animation_data is None: av.animation_data_create()
    return av


def tidy_avatar(av):
    """the skeleton drives the body mesh but is not drawn (HD2SDK bones are loose sticks with names)"""
    av.data.show_names = False; av.data.show_axes = False; av.show_in_front = False
    for b in av.data.bones: b.hide = True


def use_anim(scene, key):
    av = avatar(); act = bpy.data.actions.get('hd2dress_' + key)
    if not (av and act): return
    av.animation_data.action = act
    if hasattr(av.animation_data, 'action_slot') and act.slots: av.animation_data.action_slot = act.slots[0]
    f0, f1 = act.frame_range
    scene.frame_start, scene.frame_end = int(f0), int(f0) + 120 if f1 - f0 < 2 else int(f1) - 1
    # (a one-frame pose like Stand holds for 4 s so the cloth has time to settle and the breeze to build up)
    scene.frame_set(int(f0)); reset()


def reset():
    STATE['sims'].clear(); STATE['prev'] = None; STATE['t'] = 0.0


# ======================================================================== skinning (numpy, from the Helldiver's pose)
class Skin:
    def __init__(self, obj):
        self.obj = obj; me = obj.data
        rig = next((md.object for md in obj.modifiers if md.type == 'ARMATURE' and md.object), None)
        self.rig = rig
        n = len(me.vertices)
        co = np.empty(n * 3, np.float32); me.vertices.foreach_get('co', co); co = co.reshape(n, 3)
        W = np.array(obj.matrix_world, dtype=np.float64)
        self.rest = (np.c_[co, np.ones(n)] @ W.T)[:, :3]                      # rest positions, world
        bones = [g.name for g in obj.vertex_groups if rig is not None and g.name in rig.data.bones]
        gi = {obj.vertex_groups[b].index: k for k, b in enumerate(bones)}
        idx = np.zeros((n, 4), np.int32); wt = np.zeros((n, 4), np.float64)
        for v in me.vertices:
            ws = sorted(((gi[g.group], g.weight) for g in v.groups if g.group in gi and g.weight > 0), key=lambda x: -x[1])[:4]
            s = sum(w for _, w in ws)
            for k, (b, w) in enumerate(ws): idx[v.index, k] = b; wt[v.index, k] = w / s if s else 0
        self.bones, self.idx, self.wt = bones, idx, wt
        self.unweighted = wt.sum(1) < 1e-6
        Rw = np.array(rig.matrix_world, dtype=np.float64) if rig else np.eye(4)
        self.inv_rest = np.array([np.linalg.inv(Rw @ np.array(rig.data.bones[b].matrix_local, dtype=np.float64)) for b in bones]) \
            if bones else np.zeros((0, 4, 4))

    def pose(self, avw):
        """World positions of every vertex for the Helldiver's current pose. avw: {bone: 4x4 world matrix}."""
        if not self.bones: return self.rest.copy()
        M = np.array([avw.get(b, np.eye(4)) @ self.inv_rest[k] if b in avw else np.eye(4) for k, b in enumerate(self.bones)])
        h = np.c_[self.rest, np.ones(len(self.rest))]
        out = np.zeros((len(self.rest), 3))
        for k in range(4):
            Mk = M[self.idx[:, k]]                                            # n x 4 x 4
            out += self.wt[:, k:k + 1] * np.einsum('nij,nj->ni', Mk, h)[:, :3]
        out[self.unweighted] = self.rest[self.unweighted]
        return out


def scatter(n, idx, vals):
    """sum of vals (k x 3) into n rows by idx; much faster than np.add.at"""
    return np.stack([np.bincount(idx, weights=vals[:, j], minlength=n) for j in range(3)], 1)


# ======================================================================== the cloth (one per armour object)
class Cloth:
    def __init__(self, obj, props, prep):
        self.skin = Skin(obj); me = obj.data
        groups = {g.index: g.name for g in obj.vertex_groups if prep.is_cloth_group(g.name)}
        pin_gi = obj.vertex_groups['pin'].index if 'pin' in obj.vertex_groups else None
        vgroup, pinned_v = {}, set()
        for v in me.vertices:
            for g in v.groups:
                if g.weight > 0.5 and g.group in groups: vgroup[v.index] = groups[g.group]
                if g.weight > 0.5 and g.group == pin_gi: pinned_v.add(v.index)
        cv = set(vgroup)
        faces = [list(f.vertices) for f in me.polygons if all(i in cv for i in f.vertices)]
        cv = sorted({i for f in faces for i in f})
        key, self.vp, rep = {}, {}, []
        for v in cv:                                                          # one particle per position (as the build)
            k = tuple(np.round(self.skin.rest[v], 5))
            if k not in key: key[k] = len(rep); rep.append(v)
            self.vp[v] = key[k]
        self.rep = np.array(rep); N = len(rep); self.N = N
        self.cloth_v = np.array(cv); self.cloth_p = np.array([self.vp[v] for v in cv])
        tris = set()
        for f in faces:
            ps = [self.vp[i] for i in f]
            for a in range(1, len(ps) - 1):
                t = (ps[0], ps[a], ps[a + 1])
                if len(set(t)) == 3: tris.add(tuple(t))
        tris = np.array(sorted(tris)) if tris else np.zeros((0, 3), int)
        X0 = self.skin.rest[self.rep]
        # islands
        par = list(range(N))
        def f_(i):
            while par[i] != i: par[i] = par[par[i]]; i = par[i]
            return i
        for a, b, c in tris: par[f_(a)] = f_(b); par[f_(b)] = f_(c)
        isl = np.array([f_(i) for i in range(N)])
        # pins: the author's pin group where an island has any, else the island's top row
        pin = np.zeros(N, bool)
        for v in pinned_v:
            if v in self.vp: pin[self.vp[v]] = True
        for r in set(isl.tolist()):
            m = isl == r
            if not pin[m].any(): pin[m & (X0[:, 2] >= X0[m, 2].max() - 0.002)] = True
        self.pin = pin
        # per particle piece settings
        pieces = {p.name: p for p in props.pieces}
        pg = [vgroup.get(v) for v in rep]
        def val(attr, default): return np.array([getattr(pieces[g], attr) if g in pieces else default for g in pg], np.float64)
        self.leash = val('leash', 1.0); self.stretch = val('stretch', 0.6); self.bend = val('bend', 0.24)
        follow = np.array([bool(pieces[g].follow_legs) if g in pieces else False for g in pg])
        # thigh follow (build: gen_engine_cloth sim skin): the lower part of a follow-legs piece follows the thigh on
        # its side, more toward the hem; the front half picks its own side (front_follow)
        fw = np.zeros(N); side = np.zeros(N)
        for r in set(isl.tolist()):
            m = (isl == r) & follow
            if not m.any(): continue
            zt, zb = X0[m, 2].max(), X0[m, 2].min(); rmax = max(np.abs(X0[m, 0]).max(), 1e-6)
            fw[m] = (zt - X0[m, 2]) / max(zt - zb, 1e-6)
            side[m] = np.clip(X0[m, 0] / rmax, -1, 1)
        self.fw, self.side, self.front = fw, side, X0[:, 1] > 0
        self.X0 = X0
        self.stiff = val('stiffness', 1.0); mass = val('mass', 0.004)
        self.inv = np.where(pin, 0.0, 1.0 / np.maximum(mass, 1e-6))
        # links (edges) and bending (the two far corners of every pair of triangles sharing an edge)
        edges, opp = {}, {}
        for t in tris:
            for a, b, c in ((t[0], t[1], t[2]), (t[1], t[2], t[0]), (t[2], t[0], t[1])):
                e = (min(a, b), max(a, b)); edges[e] = 1; opp.setdefault(e, []).append(c)
        E = np.array(sorted(edges)) if edges else np.zeros((0, 2), int)
        E = E[~(pin[E[:, 0]] & pin[E[:, 1]])] if len(E) else E
        self.E, self.EL = E, np.linalg.norm(X0[E[:, 0]] - X0[E[:, 1]], axis=1) if len(E) else np.zeros(0)
        H = np.array([o for o in opp.values() if len(o) == 2]) if opp else np.zeros((0, 2), int)
        self.H, self.HL = H, np.linalg.norm(X0[H[:, 0]] - X0[H[:, 1]], axis=1) if len(H) else np.zeros(0)
        # stretch: each free particle to the nearest pin of its island
        sp, sl = [], []
        for i in np.nonzero(~pin)[0]:
            cand = np.nonzero(pin & (isl == isl[i]))[0]
            if not len(cand): sp.append(i); sl.append(1e9); continue
            j = cand[np.argmin(np.linalg.norm(X0[cand, :2] - X0[i, :2], axis=1))]
            sp.append(j); sl.append(np.linalg.norm(X0[j] - X0[i]) * (1 + self.stretch[i]))
        self.free = np.nonzero(~pin)[0]; self.spin = np.array(sp, int); self.slen = np.array(sl)
        self.x = None
        self.n_faces = len(tris)
        deg = np.bincount(np.r_[E[:, 0], E[:, 1]], minlength=N) if len(E) else np.ones(N)
        self.relax = 1.0 / max(1.0, float(np.median(deg[deg > 0])) * 0.5) if len(E) else 1.0

    def follow_targets(self, target, avw, avrest, P):
        """blend each follow-legs particle's target from the skinned (hips) position toward the thigh on its side"""
        if P['follow'] <= 0 or not self.fw.any(): return target
        out = target.copy()
        for name, sgn in (('l_thigh', -1), ('r_thigh', 1)):
            if name not in avw or name not in avrest: continue
            D = avw[name] @ np.linalg.inv(avrest[name])
            moved = (np.c_[self.X0, np.ones(self.N)] @ D.T)[:, :3]
            if P['front_follow']:
                k = np.where(self.front, (0.5 + 0.5 * np.abs(self.side)) * ((self.side * sgn) >= 0), np.maximum(0, self.side * sgn))
            else:
                k = np.maximum(0, self.side * sgn)
            w = (P['follow'] * self.fw * k)[:, None]
            out = out + w * (moved - target)
        return out

    def step(self, target, caps, P, dt, wind_vec, frame_shift):
        """One solver step. target: N x 3 skinned positions (moving frame). caps: [(a, b, r)]."""
        if self.x is None:
            self.x = target.copy(); self.xp = target.copy()
        x, xp, pin = self.x, self.xp, self.pin
        if getattr(self, 'last_shift', None) is not None:
            move = frame_shift - self.last_shift; spd = np.linalg.norm(move) / dt
            f = np.clip((spd - P['carry_min']) / max(P['carry_max'] - P['carry_min'], 1e-6), 0, 1)
            x += move * f; xp += move * f                       # the game's transferMotion (translation part)
        self.last_shift = frame_shift.copy()
        damp = max(0.0, 1.0 - P['damping'] * dt)
        v = (x - xp) * damp
        acc = np.array([0.0, 0.0, -P['gravity']])
        new = x + v + acc * dt * dt
        if wind_vec is not None:                     # drag toward the moving air (stand-in for the engine's aero)
            rel = wind_vec[None, :] * dt - (x - xp)
            new += P['wind_k'] * rel * dt
        new[pin] = target[pin]
        self.xp = x.copy()
        x = new; inv = self.inv; E, EL = self.E, self.EL; N = self.N
        r_p = P['radius']
        lo, hi = x.min(0) - 0.3, x.max(0) + 0.3                                  # only colliders near the cloth
        caps = [(a, b, rc) for a, b, rc in caps if (np.minimum(a, b) - rc < hi).all() and (np.maximum(a, b) + rc > lo).all()]
        for it in range(P['iterations']):
            for _ in range(1 + P['link_passes']):                                     # links
                if len(E):
                    d = x[E[:, 1]] - x[E[:, 0]]; L = np.linalg.norm(d, axis=1) + 1e-9
                    wa, wb = inv[E[:, 0]], inv[E[:, 1]]; ws = wa + wb + 1e-12
                    c = ((L - EL) / L * self.stiff[E[:, 0]])[:, None] * d
                    x += (scatter(N, E[:, 0], c * (wa / ws)[:, None]) - scatter(N, E[:, 1], c * (wb / ws)[:, None])) * self.relax
            if len(self.H):                                                           # bending
                H = self.H; d = x[H[:, 1]] - x[H[:, 0]]; L = np.linalg.norm(d, axis=1) + 1e-9
                wa, wb = inv[H[:, 0]], inv[H[:, 1]]; ws = wa + wb + 1e-12
                c = ((L - self.HL) / L * self.bend[H[:, 0]] * 0.5)[:, None] * d
                x += (scatter(N, H[:, 0], c * (wa / ws)[:, None]) - scatter(N, H[:, 1], c * (wb / ws)[:, None])) * self.relax
            f = self.free                                                             # stretch limit to the pin
            d = x[f] - x[self.spin]; L = np.linalg.norm(d, axis=1) + 1e-9
            over = L > self.slen
            x[f[over]] = x[self.spin[over]] + d[over] / L[over, None] * self.slen[over, None]
            d = x - target; L = np.linalg.norm(d, axis=1) + 1e-9                        # leash
            over = (L > self.leash) & ~pin
            x[over] = target[over] + d[over] / L[over, None] * self.leash[over, None]
            for a, b, rc in caps:                                                     # body capsules
                ab = b - a; t = np.clip(((x - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
                cpt = a + t[:, None] * ab; d = x - cpt; L = np.linalg.norm(d, axis=1) + 1e-9
                hit = (L < rc + r_p) & ~pin
                if hit.any():
                    x[hit] = cpt[hit] + d[hit] / L[hit, None] * (rc + r_p)
                    mv = x[hit] - self.xp[hit]                                        # friction: keep less sideways slide
                    self.xp[hit] += mv * P['friction'] * 0.1
            low = x[:, 2] < P['floor'] + r_p                                          # floor
            x[low & ~pin, 2] = P['floor'] + r_p
        x[pin] = target[pin]
        self.x = x
        return x


# ======================================================================== per frame
_COLS = {}


def colliders(av, P):
    if 'c' not in _COLS: _COLS['c'] = json.load(open(os.path.join(CACHE, 'colliders.json')))
    cols = _COLS['c']
    out = []
    for c in cols:
        pb = av.pose.bones.get(c['bone'])
        if pb is None: continue
        W = np.array(av.matrix_world @ pb.matrix, dtype=np.float64) @ np.array(c['offset'])
        a = (W @ np.r_[c['start'], 1.0])[:3]; b = (W @ np.r_[c['end'], 1.0])[:3]
        out.append((c['bone'], a, b, c['radius']))
        if P['kneecaps'] and c['bone'] in ('l_knee', 'r_knee'):                          # the build's kneecaps
            ka = (W @ np.array([-0.05, c['start'][1], c['start'][2], 1.0]))[:3]
            kb = (W @ np.array([0.05, c['start'][1], c['start'][2], 1.0]))[:3]
            out.append((c['bone'] + '_cap', ka, kb, c['radius'] + P['kneecap_grow']))
    return out


def params(props):
    return dict(gravity=props.gravity, damping=props.damping, iterations=max(1, props.iterations), link_passes=props.link_passes,
                radius=props.radius, friction=props.friction, floor=props.floor_gap, wind_k=3.0 * props.wind,
                kneecaps=props.kneecaps, kneecap_grow=props.kneecap_grow, follow=props.follow_thigh,
                front_follow=props.follow_front, carry_min=props.motion_min, carry_max=props.motion_max)


def drive(scene, depsgraph):
    props = scene.hd2dress; ui = bpy.context.window_manager.hd2dress_ui
    if not ui.preview_playing: return
    av = avatar()
    if av is None: return
    from . import prep_mod
    f = scene.frame_current
    prev = STATE['prev']
    looped = prev is not None and f == scene.frame_start and prev >= scene.frame_end - 1
    if prev is not None and not (f == prev + 1 or looped): reset()          # a jump by the user: start fresh
    STATE['prev'] = f
    t0 = time.perf_counter()
    dt_frame = 1.0 / max(1, scene.render.fps); sub = 2; dt = dt_frame / sub
    STATE['t'] += dt_frame
    av_e = av.evaluated_get(depsgraph)
    avw = {pb.name: np.array(av.matrix_world @ pb.matrix, dtype=np.float64) for pb in av_e.pose.bones}
    if 'avrest' not in STATE:
        STATE['avrest'] = {b.name: np.array(av.matrix_world @ b.matrix_local, dtype=np.float64) for b in av.data.bones}
    speed = SPEED.get(props.preview_anim, 0.0) * props.preview_speed
    shift = np.array([0.0, speed * STATE['t'], 0.0])                      # the moving frame: the body runs forward (+Y)
    P = params(props)
    caps = [(a + shift, b + shift, r) for _, a, b, r in colliders(av_e, P)]
    wind = None
    if props.preview_breeze and props.wind > 0:
        ang = math.radians(props.preview_wind_dir)
        wind = np.array([math.sin(ang), -math.cos(ang), 0.0]) * WIND_SHIP * (0.75 + 0.25 * math.sin(STATE['t'] * 1.7) * math.sin(STATE['t'] * 0.6))
    P_ = prep_mod()
    for o in P_.cloth_objects():
        prev = bpy.data.objects.get('hd2dress_preview_' + o.name)
        if prev is None: continue
        c = STATE['sims'].get(o.name)
        if c is None:
            c = STATE['sims'][o.name] = Cloth(o, props, P_)
        allv = c.skin.pose(avw)
        tgt = c.follow_targets(allv[c.rep], avw, STATE['avrest'], P) + shift
        for _ in range(sub): x = c.step(tgt, caps, P, dt, wind, shift)
        allv[c.cloth_v] = x[c.cloth_p] - shift
        prev.data.vertices.foreach_set('co', allv.astype(np.float32).ravel()); prev.data.update()
    STATE['ms'] = (time.perf_counter() - t0) * 1000
    ui.preview_ms = STATE['ms']
    if props.preview_colliders: show_colliders(scene, [(n, a, b, r) for n, a, b, r in colliders(av_e, P)])


# ======================================================================== start / stop
def start(context):
    scene = context.scene; props = scene.hd2dress
    from . import prep_mod
    av = load_avatar(scene); tidy_avatar(av)
    use_anim(scene, props.preview_anim)
    coll = collection(scene); STATE['hidden'] = []
    objs = [o for o in prep_mod().cloth_objects() if o.visible_get()] or prep_mod().cloth_objects()[:1]
    for o in objs:
        name = 'hd2dress_preview_' + o.name
        p = bpy.data.objects.get(name)
        if p is None:
            me = o.data.copy(); me.name = name
            p = bpy.data.objects.new(name, me); coll.objects.link(p)
        p.matrix_world = mathutils.Matrix.Identity(4)
        p.hide_select = True
        if not o.hide_get(): o.hide_set(True); STATE['hidden'].append(o.name)
    scene.render.fps = 30
    reset()
    return av


def stop(context):
    scene = context.scene
    for n in STATE.get('hidden', []):
        o = bpy.data.objects.get(n)
        if o: o.hide_set(False)
    STATE['hidden'] = []
    for o in [o for o in bpy.data.objects if o.name.startswith('hd2dress_preview_') or o.name.startswith('hd2dress_col_')]:
        me = o.data; bpy.data.objects.remove(o)
        if me and me.users == 0: bpy.data.meshes.remove(me)
    av = avatar()
    if av and av.animation_data: av.animation_data.action = None
    if av:
        for pb in av.pose.bones: pb.matrix_basis.identity()
    reset()


# ======================================================================== collider view
SEG, RINGS = 12, 3


def _capsule(a, b, r):
    a, b = mathutils.Vector(a), mathutils.Vector(b); ax = b - a
    ax = ax.normalized() if ax.length > 1e-6 else mathutils.Vector((0, 0, 1))
    u = ax.orthogonal().normalized(); v = ax.cross(u); out = []
    rings = [(a, -1, k) for k in range(RINGS + 1)] + [(b, 1, k) for k in range(RINGS, -1, -1)]
    for centre, sign, k in rings:
        t = k / RINGS * math.pi / 2; c = centre + ax * (sign * r * math.cos(t))
        for i in range(SEG):
            ph = 2 * math.pi * i / SEG; out.append(c + (u * math.cos(ph) + v * math.sin(ph)) * (r * math.sin(t)))
    return out


def _faces():
    n = 2 * (RINGS + 1)
    return [(j * SEG + i, j * SEG + (i + 1) % SEG, (j + 1) * SEG + (i + 1) % SEG, (j + 1) * SEG + i) for j in range(n - 1) for i in range(SEG)]


def show_colliders(scene, caps):
    coll = collection(scene)
    for name, a, b, r in caps:
        on = 'hd2dress_col_' + name; o = bpy.data.objects.get(on); vs = _capsule(a, b, r)
        if o is None:
            me = bpy.data.meshes.new(on); me.from_pydata([tuple(p) for p in vs], [], _faces())
            o = bpy.data.objects.new(on, me); coll.objects.link(o)
            o.display_type = 'WIRE'; o.hide_select = True; o.hide_render = True
        else:
            o.data.vertices.foreach_set('co', [c for p in vs for c in p]); o.data.update()


def hide_colliders():
    for o in [o for o in bpy.data.objects if o.name.startswith('hd2dress_col_')]:
        me = o.data; bpy.data.objects.remove(o)
        if me and me.users == 0: bpy.data.meshes.remove(me)
